"""Playwright-backed browser automation for Corvus.

One managed Chromium session per app run: the page persists across actions so a
multi-step task (navigate → read → click → read) keeps its context and cookies.
The engine is injected into the FastAPI app like the voice pipeline, and lazily
launches the browser on first use so startup stays fast.

Web element targeting uses Playwright's DOM/accessibility locators (click by
visible text or role), which is far more reliable than pixel matching for web
pages; screenshot-based coordinate clicking (vision.py) covers native windows.

Security: per the product spec, Corvus never types stored site passwords. The
`open_login` flow navigates to a site's sign-in page and hands off to the
browser's own credential manager after explicit per-site confirmation.
"""

import asyncio
import contextlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import structlog

log = structlog.get_logger("corvus")

DEFAULT_TITLE = "about:blank"


ALLOWED_SCHEMES = {"http", "https"}


def normalize_url(url: str) -> str:
    url = url.strip()
    if urlparse(url).scheme.lower() in ALLOWED_SCHEMES or "://" in url:
        return url
    # "example.com", "localhost:3000/x" (parses as scheme "localhost").
    return "https://" + url


def check_web_url(url: str) -> str:
    """Normalize and allow only web pages: file://, chrome://, view-source:,
    javascript: etc. could read local files and send them to a website."""
    url = normalize_url(url)
    if urlparse(url).scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError("Corvus's browser only opens http:// and https:// web pages.")
    return url


def _is_internal_ip(ip: str) -> bool:
    import ipaddress

    addr = ipaddress.ip_address(ip.split("%")[0])
    return not addr.is_global or addr.is_multicast


async def is_internal_host(url: str) -> bool:
    """True when the URL's host resolves to loopback/private/link-local space.

    The agent's browser is steerable by page content (prompt injection), so it
    must not reach the local Ollama API, router admin pages or LAN services.
    # ponytail: checked at navigation time only; DNS rebinding between this
    # lookup and Chromium's own is out of scope.
    """
    import socket

    host = urlparse(url).hostname
    if not host:
        return False
    try:
        return _is_internal_ip(host)  # an IP literal
    except ValueError:
        pass
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return True
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False  # unresolvable: Chromium will fail it on its own
    return any(_is_internal_ip(info[4][0]) for info in infos)


def _install_chromium(browsers_dir: Path) -> None:
    """Install Playwright's Chromium via its bundled driver.

    Uses the driver's node + cli.js directly rather than `sys.executable -m
    playwright`: in the frozen (PyInstaller) build sys.executable is the Corvus
    backend itself, which would just start a second server.
    """
    import os
    import subprocess

    from playwright._impl._driver import compute_driver_executable, get_driver_env

    node, cli = compute_driver_executable()
    env = {**get_driver_env(), "PLAYWRIGHT_BROWSERS_PATH": str(browsers_dir)}
    subprocess.run([node, cli, "install", "chromium"], check=True, env=env, timeout=600,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)


def site_of(url: str) -> str:
    return urlparse(normalize_url(url)).netloc or url


@dataclass
class InteractiveElement:
    tag: str
    role: str
    text: str
    # Center coordinates within the viewport, for coordinate-targeted clicks.
    x: int
    y: int


@dataclass
class DownloadRecord:
    filename: str
    path: str
    url: str
    created_at: str


@dataclass
class PageView:
    url: str
    title: str
    text: str
    links: list[dict] = field(default_factory=list)


class BrowserEngine:
    def __init__(self, downloads_dir: Path, headless: bool = False):
        self.downloads_dir = downloads_dir
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._lock = asyncio.Lock()
        self.consented_sites: set[str] = set()
        self.downloads: list[DownloadRecord] = []

    @property
    def is_open(self) -> bool:
        return self._page is not None and not self._page.is_closed()

    async def _teardown(self) -> None:
        for closer in (self._context, self._browser):
            if closer is not None:
                with contextlib.suppress(Exception):
                    await closer.close()
        if self._pw is not None:
            with contextlib.suppress(Exception):
                await self._pw.stop()
        self._pw = self._browser = self._context = self._page = None

    async def _ensure_page(self):
        async with self._lock:
            if self._page is not None and self._page.is_closed():
                # The user closed the Chromium window: start a fresh session.
                await self._teardown()
            if self._page is None:
                try:
                    await self._launch()
                except Exception:
                    await self._teardown()  # don't leak the Playwright driver
                    raise
        return self._page

    async def _launch(self) -> None:
        import os

        from playwright.async_api import async_playwright

        # Redirect Playwright's browser cache to a persistent, user-writable
        # location so the bundled (PyInstaller) app doesn't look for Chromium
        # inside its read-only _internal/ tree. Must be set before launching.
        from ..config import data_dir

        # An explicit PLAYWRIGHT_BROWSERS_PATH wins (dev machines, tests reuse their cache).
        browsers_dir = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or data_dir() / "playwright-browsers")
        browsers_dir.mkdir(parents=True, exist_ok=True)
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)

        self._pw = await async_playwright().start()
        try:
            self._browser = await self._pw.chromium.launch(headless=self.headless)
        except Exception as first_err:
            # Chromium binary is missing - install it (off the event loop).
            log.info("browser_install_start", reason=str(first_err), dest=str(browsers_dir))
            try:
                await asyncio.to_thread(_install_chromium, browsers_dir)
                log.info("browser_install_done")
            except Exception as install_err:
                raise RuntimeError(f"Failed to install Chromium: {install_err}") from first_err
            self._browser = await self._pw.chromium.launch(headless=self.headless)

        self._context = await self._browser.new_context(accept_downloads=True)
        # Redirects and in-page links get the same internal-host check as
        # browser_navigate; sub-resources load normally.
        await self._context.route("**/*", self._guard_navigation)
        self._page = await self._context.new_page()
        self._page.on("download", self._handle_download)
        log.info("browser_launched", headless=self.headless)

    async def _guard_navigation(self, route) -> None:
        request = route.request
        if (request.is_navigation_request() and request.url.startswith(("http://", "https://"))
                and await is_internal_host(request.url)):
            log.warning("browser_internal_navigation_blocked", url=request.url)
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    def _handle_download(self, download) -> None:
        async def save():
            # The site picks the name: keep only the final component.
            name = Path(download.suggested_filename.replace("\\", "/")).name.strip(" .") or "download"
            dest = self.downloads_dir / name
            with contextlib.suppress(Exception):
                await download.save_as(str(dest))
                self.downloads.append(
                    DownloadRecord(
                        filename=dest.name,
                        path=str(dest),
                        url=download.url,
                        created_at=datetime.now().isoformat(timespec="seconds"),
                    )
                )
                log.info("browser_download", filename=dest.name)

        asyncio.create_task(save())

    # -- consent --------------------------------------------------------------

    def grant_consent(self, site: str) -> None:
        self.consented_sites.add(site)

    # -- navigation & reading -------------------------------------------------

    async def navigate(self, url: str) -> PageView:
        url = check_web_url(url)
        if await is_internal_host(url):
            raise PermissionError(
                "Corvus's browser doesn't open local or private-network addresses."
            )
        page = await self._ensure_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return await self.read()

    async def read(self, max_chars: int = 6000) -> PageView:
        page = await self._ensure_page()
        title = await page.title()
        try:
            text = await page.inner_text("body", timeout=5000)
        except Exception:
            text = ""
        text = " ".join(text.split())[:max_chars]
        links = await self._links()
        return PageView(url=page.url, title=title or DEFAULT_TITLE, text=text, links=links[:40])

    async def _links(self) -> list[dict]:
        page = await self._ensure_page()
        raw = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({text: (e.innerText||'').trim().slice(0,80), href: e.href}))"
            ".filter(l => l.text && l.href)",
        )
        # De-dupe by href, keep first label.
        seen: dict[str, dict] = {}
        for link in raw:
            seen.setdefault(link["href"], link)
        return list(seen.values())

    async def click_text(self, text: str) -> str:
        page = await self._ensure_page()
        locator = page.get_by_text(text, exact=False).first
        await locator.click(timeout=8000)
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        return page.url

    async def fill_field(self, label: str, value: str) -> None:
        page = await self._ensure_page()
        # Try common ways a field is identified, most specific first.
        for locator in (
            page.get_by_label(label),
            page.get_by_placeholder(label),
            page.locator(f"input[name='{label}']"),
            page.locator(f"textarea[name='{label}']"),
        ):
            target = locator.first
            try:
                kind = (await target.get_attribute("type", timeout=3000) or "").lower()
                autocomplete = (await target.get_attribute("autocomplete") or "").lower()
            except Exception:
                continue
            if kind == "password" or "password" in autocomplete:
                # Product rule: Corvus never types passwords (browser_open_login
                # hands sign-in to the browser's own credential manager).
                raise PermissionError("Corvus doesn't type passwords. Use the browser's saved-password fill instead.")
            try:
                await target.fill(value, timeout=3000)
                return
            except Exception:
                continue
        raise RuntimeError(f"No field matching '{label}' was found on the page.")

    async def interactive_elements(self, limit: int = 40) -> list[InteractiveElement]:
        page = await self._ensure_page()
        raw = await page.eval_on_selector_all(
            "a[href], button, input, [role=button], [role=link], select, textarea",
            """els => els.slice(0, 200).map(e => {
                const r = e.getBoundingClientRect();
                return {
                    tag: e.tagName.toLowerCase(),
                    role: e.getAttribute('role') || e.type || '',
                    text: (e.innerText || e.value || e.placeholder ||
                           e.getAttribute('aria-label') || '').trim().slice(0, 80),
                    x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                    visible: r.width > 0 && r.height > 0
                };
            }).filter(e => e.visible && e.text)""",
        )
        return [
            InteractiveElement(tag=e["tag"], role=e["role"], text=e["text"], x=e["x"], y=e["y"])
            for e in raw[:limit]
        ]

    async def screenshot(self, dest: Path) -> Path:
        page = await self._ensure_page()
        dest.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(dest), full_page=False)
        return dest

    async def close(self) -> None:
        async with self._lock:
            await self._teardown()
            log.info("browser_closed")

    def download_list(self) -> list[dict]:
        return [asdict(d) for d in reversed(self.downloads)]

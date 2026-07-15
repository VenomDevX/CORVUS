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


def normalize_url(url: str) -> str:
    if not urlparse(url).scheme:
        return "https://" + url
    return url


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
        return self._page is not None

    async def _ensure_page(self):
        async with self._lock:
            if self._page is None:
                from playwright.async_api import async_playwright

                self._pw = await async_playwright().start()
                self._browser = await self._pw.chromium.launch(headless=self.headless)
                self._context = await self._browser.new_context(accept_downloads=True)
                self._page = await self._context.new_page()
                self._page.on("download", self._handle_download)
                log.info("browser_launched", headless=self.headless)
        return self._page

    def _handle_download(self, download) -> None:
        async def save():
            dest = self.downloads_dir / download.suggested_filename
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

    def has_consent(self, site: str) -> bool:
        return site in self.consented_sites

    # -- navigation & reading -------------------------------------------------

    async def navigate(self, url: str) -> PageView:
        page = await self._ensure_page()
        await page.goto(normalize_url(url), wait_until="domcontentloaded", timeout=30000)
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
            try:
                await locator.first.fill(value, timeout=3000)
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
            for closer in (self._context, self._browser):
                if closer is not None:
                    with contextlib.suppress(Exception):
                        await closer.close()
            if self._pw is not None:
                with contextlib.suppress(Exception):
                    await self._pw.stop()
            self._pw = self._browser = self._context = self._page = None
            log.info("browser_closed")

    def download_list(self) -> list[dict]:
        return [asdict(d) for d in reversed(self.downloads)]

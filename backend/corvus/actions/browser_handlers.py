"""Browser automation and computer-vision actions (Milestone 7).

These are registered only when a browser engine is available (i.e. in the real
app), because they close over the shared engine and the LLM provider. Web
targeting uses Playwright locators; on-screen (native window) targeting uses
OCR coordinates plus PyAutoGUI.
"""

from datetime import datetime
from pathlib import Path

from ..automation import vision
from ..automation.browser import BrowserEngine, site_of
from ..config import data_dir
from ..llm.base import Message
from ..untrusted import UNTRUSTED_RULE, wrap_untrusted
from .registry import ActionResult, ActionSpec, Registry, Risk

_STR = lambda name, desc, req=True: {  # noqa: E731 - tiny schema builder
    "type": "object",
    "properties": {name: {"type": "string", "description": desc}},
    **({"required": [name]} if req else {}),
}


async def _summarize(provider, model: str, title: str, text: str, instruction: str) -> str:
    prompt = (
        f"{instruction}\n\nPage title: {title}\n\nPage content:\n{wrap_untrusted(text[:5000])}"
    )
    parts: list[str] = []
    async for delta in provider.stream_chat(
        [Message("system", "You summarize web pages concisely and accurately. " + UNTRUSTED_RULE),
         Message("user", prompt)],
        model,
    ):
        parts.append(delta.content)
    return "".join(parts).strip()


def register_browser_actions(reg: Registry, browser: BrowserEngine, provider, get_model) -> None:
    def _model() -> str:
        return get_model()

    async def navigate(url: str) -> ActionResult:
        view = await browser.navigate(url)
        return ActionResult(True, f"Opened {view.title} ({view.url}).",
                            {"url": view.url, "title": view.title})

    reg.register(ActionSpec(
        "browser_navigate", "Open a URL in Corvus's browser and load the page.",
        _STR("url", "The URL or address to open"),
        Risk.LOW, navigate, category="browser",
    ))

    async def read_page() -> ActionResult:
        view = await browser.read()
        return ActionResult(True, f"Read “{view.title}” ({len(view.text)} chars).",
                            {"title": view.title, "url": view.url,
                             "text": wrap_untrusted(view.text),
                             "links": view.links})

    reg.register(ActionSpec(
        "browser_read_page", "Read the text and links of the page currently open in the browser.",
        {"type": "object", "properties": {}}, Risk.SAFE, read_page, category="browser",
    ))

    async def summarize_page() -> ActionResult:
        view = await browser.read()
        summary = await _summarize(provider, _model(), view.title, view.text,
                                   "Summarize this web page in a few sentences.")
        return ActionResult(True, summary or "The page had no readable text.",
                            {"title": view.title, "url": view.url})

    reg.register(ActionSpec(
        "browser_summarize_page", "Summarize the page currently open in the browser.",
        {"type": "object", "properties": {}}, Risk.SAFE, summarize_page, category="browser",
    ))

    async def click(text: str) -> ActionResult:
        url = await browser.click_text(text)
        return ActionResult(True, f"Clicked “{text}”. Now on {url}.", {"url": url})

    reg.register(ActionSpec(
        "browser_click", "Click a link or button in the browser by its visible text.",
        _STR("text", "The visible text of the link or button to click"),
        Risk.MEDIUM, click,
        confirm_prompt=lambda a: f"Click “{a.get('text')}” in the browser?",
        category="browser",
    ))

    async def fill(field: str, value: str) -> ActionResult:
        await browser.fill_field(field, value)
        return ActionResult(True, f"Filled “{field}”.")

    reg.register(ActionSpec(
        "browser_fill_field", "Type a value into a form field (by its label, placeholder, or name). "
        "Do not use for passwords - use browser_open_login instead.",
        {"type": "object", "properties": {
            "field": {"type": "string", "description": "Field label, placeholder, or name"},
            "value": {"type": "string", "description": "The value to type"},
        }, "required": ["field", "value"]},
        Risk.MEDIUM, fill,
        confirm_prompt=lambda a: f"Type “{a.get('value')}” into the “{a.get('field')}” field?",
        category="browser",
    ))

    async def screenshot_page() -> ActionResult:
        dest = data_dir() / "screenshots" / f"page-{datetime.now():%Y%m%d-%H%M%S}.png"
        await browser.screenshot(dest)
        return ActionResult(True, f"Saved a screenshot of the page to {dest}.", {"path": str(dest)})

    reg.register(ActionSpec(
        "browser_screenshot", "Capture a screenshot of the current browser page.",
        {"type": "object", "properties": {}}, Risk.SAFE, screenshot_page, category="browser",
    ))

    async def research(topic: str) -> ActionResult:
        # Multi-step: search, open the top few results, read and synthesize.
        from urllib.parse import quote_plus

        await browser.navigate(f"https://duckduckgo.com/html/?q={quote_plus(topic)}")
        results = await browser.read()
        result_links = [l for l in results.links
                        if "duckduckgo.com" not in l["href"] and l["href"].startswith("http")][:3]
        gathered = []
        for link in result_links:
            try:
                view = await browser.navigate(link["href"])
                gathered.append(f"Source: {view.title} ({view.url})\n{view.text[:1500]}")
            except Exception:
                continue
        if not gathered:
            return ActionResult(False, f"Couldn't gather sources on “{topic}”.")
        summary = await _summarize(
            provider, _model(), topic, "\n\n".join(gathered),
            f"Research the topic “{topic}” from these sources and give a concise, cited answer.",
        )
        return ActionResult(True, summary, {"sources": [l["href"] for l in result_links]})

    reg.register(ActionSpec(
        "browser_research", "Research a topic on the web: search, read the top results, and "
        "summarize an answer with sources.",
        _STR("topic", "The topic or question to research"),
        Risk.LOW, research, category="browser",
    ))

    async def open_login(site: str) -> ActionResult:
        # Corvus never types stored passwords; it opens the sign-in page and
        # hands off to the browser's own credential manager. The confirmation
        # is the per-site consent the spec requires.
        host = site_of(site)
        browser.grant_consent(host)
        view = await browser.navigate(site)
        return ActionResult(
            True,
            f"Opened the sign-in page for {host}. Please complete the login in the browser window - "
            "Corvus won't type your password.",
            {"url": view.url},
        )

    reg.register(ActionSpec(
        "browser_open_login", "Open a website's sign-in page so the user can log in. Corvus never "
        "types stored passwords; the browser's own credential manager handles it.",
        _STR("site", "The site to sign in to (URL or domain)"),
        Risk.HIGH, open_login,
        confirm_prompt=lambda a: f"Open the sign-in page for {site_of(a.get('site',''))} so you can log "
        "in? Corvus won't enter your password itself.",
        category="browser",
    ))

    async def close_browser() -> ActionResult:
        await browser.close()
        return ActionResult(True, "Closed the browser.")

    reg.register(ActionSpec(
        "browser_close", "Close Corvus's browser session.",
        {"type": "object", "properties": {}}, Risk.LOW, close_browser, category="browser",
    ))


def register_vision_actions(reg: Registry, provider) -> None:
    from . import win

    async def describe_image(path: str) -> ActionResult:
        p = Path(path).expanduser()
        if not p.exists():
            return ActionResult(False, f"No image at {path}.")
        result = await vision.describe_image(provider, str(p))
        # OCR text and model descriptions are outside-world content: wrap them
        # so downstream turns treat them as data, not instructions.
        if result.get("text"):
            result["text"] = wrap_untrusted(result["text"])
        if result.get("description"):
            result["description"] = wrap_untrusted(result["description"])
        msg = result.get("description") or (
            f"Text found in the image:\n{result['text']}" if result["has_text"]
            else "No text detected in the image."
        )
        return ActionResult(True, msg, result)

    reg.register(ActionSpec(
        "describe_image", "Understand an image or screenshot file: read its text and, if a vision "
        "model is installed, describe it.",
        _STR("path", "Path to the image file"),
        Risk.SAFE, describe_image, category="vision",
    ))

    async def read_screen() -> ActionResult:
        from ..config import data_dir

        shot = data_dir() / "screenshots" / f"screen-{datetime.now():%Y%m%d-%H%M%S}.png"
        win.screenshot(shot)
        text = vision.extract_text(str(shot))
        return ActionResult(True, f"Read {len(text.splitlines())} lines of text from the screen.",
                            {"text": wrap_untrusted(text), "screenshot": str(shot)})

    reg.register(ActionSpec(
        "read_screen_text", "Take a screenshot of the screen and read the text on it (OCR).",
        {"type": "object", "properties": {}}, Risk.SAFE, read_screen, category="vision",
    ))

    async def click_on_screen(target: str) -> ActionResult:
        import pyautogui

        from ..config import data_dir

        shot = data_dir() / "screenshots" / f"screen-{datetime.now():%Y%m%d-%H%M%S}.png"
        win.screenshot(shot)
        box = vision.locate_text(str(shot), target)
        if box is None:
            return ActionResult(False, f"Couldn't find “{target}” on the screen.")
        pyautogui.click(box.x, box.y)
        return ActionResult(True, f"Clicked “{box.text}” on the screen at ({box.x}, {box.y}).")

    reg.register(ActionSpec(
        "click_on_screen", "Find an on-screen element by its label (OCR) and click it. Works on any "
        "app, not just the browser.",
        _STR("target", "The visible text/label of the element to click"),
        Risk.HIGH, click_on_screen,
        confirm_prompt=lambda a: f"Find “{a.get('target')}” on screen and click it?",
        category="vision",
    ))

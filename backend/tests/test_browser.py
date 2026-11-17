"""Browser engine tests against local fixture pages (no network).

Playwright drives a real headless Chromium over data: URLs and set_content, so
these exercise the actual engine without depending on any website.
"""

import pytest

from corvus.automation.browser import BrowserEngine, normalize_url, site_of

FIXTURE = """
<html><head><title>Corvus Fixture</title></head><body>
<h1>Welcome</h1>
<p>This is a test page for Corvus browser automation.</p>
<a href="https://example.com/one">First link</a>
<a href="https://example.com/two">Second link</a>
<form><input name="q" placeholder="Search"><button>Go</button></form>
</body></html>
"""


@pytest.fixture
async def engine(tmp_path):
    eng = BrowserEngine(tmp_path / "downloads", headless=True)
    yield eng
    await eng.close()


def test_url_normalization():
    assert normalize_url("example.com") == "https://example.com"
    assert normalize_url("http://x.dev") == "http://x.dev"
    assert site_of("https://mail.google.com/inbox") == "mail.google.com"
    assert site_of("github.com") == "github.com"


async def test_read_extracts_title_text_and_links(engine):
    page = await engine._ensure_page()
    await page.set_content(FIXTURE)
    view = await engine.read()
    assert view.title == "Corvus Fixture"
    assert "test page for Corvus" in view.text
    hrefs = {l["href"] for l in view.links}
    assert "https://example.com/one" in hrefs
    assert "https://example.com/two" in hrefs


async def test_click_by_visible_text(engine):
    page = await engine._ensure_page()
    await page.set_content(
        '<button onclick="document.title=\'Clicked\'">Go to page</button>'
    )
    await engine.click_text("Go to page")
    assert await page.title() == "Clicked"


async def test_fill_field_by_placeholder(engine):
    page = await engine._ensure_page()
    await page.set_content(FIXTURE)
    await engine.fill_field("Search", "corvus raven")
    assert await page.input_value("input[name=q]") == "corvus raven"


def test_only_web_schemes_allowed():
    from corvus.automation.browser import check_web_url

    assert check_web_url("localhost:3000/x") == "https://localhost:3000/x"
    for bad in ("file:///C:/Windows/win.ini", "chrome://settings", "view-source:https://a.com"):
        with pytest.raises(ValueError):
            check_web_url(bad)


async def test_fill_field_refuses_password(engine):
    page = await engine._ensure_page()
    await page.set_content('<label>Pass <input type="password" name="p"></label>')
    with pytest.raises(PermissionError):
        await engine.fill_field("Pass", "hunter2")
    assert await page.input_value("input[name=p]") == ""


async def test_relaunches_after_user_closes_window(engine):
    page = await engine._ensure_page()
    await page.close()
    assert not engine.is_open
    assert not (await engine._ensure_page()).is_closed()


async def test_fill_field_missing_raises(engine):
    page = await engine._ensure_page()
    await page.set_content("<p>no fields here</p>")
    with pytest.raises(RuntimeError, match="No field"):
        await engine.fill_field("nonexistent", "x")


async def test_interactive_elements_have_coordinates(engine):
    page = await engine._ensure_page()
    await page.set_content(FIXTURE)
    elements = await engine.interactive_elements()
    texts = {e.text for e in elements}
    assert any("link" in t.lower() for t in texts)
    for e in elements:
        assert e.x >= 0 and e.y >= 0


async def test_consent_tracking(engine):
    engine.grant_consent("github.com")
    assert "github.com" in engine.consented_sites


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:11434/api/tags", "http://localhost:8765/logs", "http://10.0.0.1/",
    "http://192.168.1.1/admin", "http://169.254.169.254/latest", "http://[::1]/",
    "http://printer.local/",
])
async def test_internal_hosts_blocked(url):
    from corvus.automation.browser import is_internal_host

    assert await is_internal_host(url)


async def test_public_ip_allowed():
    from corvus.automation.browser import is_internal_host

    assert not await is_internal_host("https://1.1.1.1/")


async def test_navigate_refuses_internal_host(engine):
    with pytest.raises(PermissionError):
        await engine.navigate("http://127.0.0.1:11434/")


async def test_screenshot_written(engine, tmp_path):
    page = await engine._ensure_page()
    await page.set_content(FIXTURE)
    dest = tmp_path / "shot.png"
    await engine.screenshot(dest)
    assert dest.exists() and dest.stat().st_size > 0


async def test_guard_blocks_internal_subresource_requests(tmp_path):
    """Not only navigations: a page's fetch/img to a LAN host is aborted too."""
    eng = BrowserEngine(tmp_path / "dl", headless=True)

    class Route:
        def __init__(self, url):
            self.request = type("R", (), {"url": url, "is_navigation_request": lambda s: False})()
            self.result = None

        async def abort(self, _reason):
            self.result = "aborted"

        async def continue_(self):
            self.result = "continued"

    internal, external = Route("http://192.168.1.1/admin"), Route("https://1.1.1.1/x.png")
    await eng._guard_navigation(internal)
    await eng._guard_navigation(external)
    assert (internal.result, external.result) == ("aborted", "continued")

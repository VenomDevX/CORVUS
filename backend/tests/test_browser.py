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
    assert not engine.has_consent("github.com")
    engine.grant_consent("github.com")
    assert engine.has_consent("github.com")


async def test_screenshot_written(engine, tmp_path):
    page = await engine._ensure_page()
    await page.set_content(FIXTURE)
    dest = tmp_path / "shot.png"
    await engine.screenshot(dest)
    assert dest.exists() and dest.stat().st_size > 0

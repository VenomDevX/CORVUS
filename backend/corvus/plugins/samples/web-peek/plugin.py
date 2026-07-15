"""Web Peek — a sample plugin that needs the 'network' permission.

Corvus only loads this plugin (and therefore only exposes its action) once the
user grants network access, illustrating the permission model: the capability
literally isn't available until consent is given.
"""

import re

import httpx

from corvus.plugins.sdk import ActionResult, PluginContext


def register(ctx: PluginContext) -> None:
    # Loading only happens when 'network' was granted, but guard anyway.
    ctx.require("network")

    def page_title(url: str) -> ActionResult:
        if not re.match(r"^https?://", url):
            url = "https://" + url
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
        title = match.group(1).strip() if match else "(no title)"
        return ActionResult(True, f"“{title}”", {"title": title, "status": resp.status_code})

    ctx.action(
        "page_title", "Fetch the title of a web page by URL.",
        {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
        page_title,
    )

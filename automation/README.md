# automation/

The browser-automation and computer-vision engines (Milestone 7) live inside
the backend package at `backend/corvus/automation/` so they import cleanly with
the rest of `corvus` — see `browser.py` (Playwright Chromium) and `vision.py`
(rapidocr OCR). Their agent actions are registered from
`backend/corvus/actions/browser_handlers.py`.

This top-level directory is kept as a reserved placeholder; nothing imports from
it. Native input automation beyond screenshot-OCR clicking (arbitrary macro
recording, Windows UI Automation trees) is not yet built.

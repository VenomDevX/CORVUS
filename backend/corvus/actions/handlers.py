"""Registration of all built-in Corvus actions.

Each ActionSpec maps a model-callable tool to a handler, tagged with a risk
tier and (for confirmable actions) a function that renders the exact
consequence in a sentence - never a generic "Are you sure?". Grouped by the
categories in the product spec's agent section.

Milestone 6 ships app/window control, power/state, audio/display, media,
search, file management, software (winget), and system monitoring. Browser
automation and computer vision are Milestone 7; input automation of arbitrary
coordinates is deferred with them.
"""

from pathlib import Path

from . import files, monitor, win
from .registry import ActionResult, ActionSpec, Registry, Risk

_NO_PARAMS = {"type": "object", "properties": {}, "required": []}


def _str_param(name: str, desc: str, required: bool = True) -> dict:
    schema = {"type": "object", "properties": {name: {"type": "string", "description": desc}}}
    if required:
        schema["required"] = [name]
    return schema


def register_all(reg: Registry) -> None:
    # -- App & window control -------------------------------------------------
    def open_app(app: str) -> ActionResult:
        target = win.APP_TARGETS.get(app.lower().strip(), app)
        win.launch_app(target)
        return ActionResult(True, f"Opening {app}…")

    reg.register(ActionSpec(
        "open_app", "Open or launch a desktop application by name (e.g. Chrome, VS Code, Spotify).",
        _str_param("app", "Application name to open"),
        Risk.LOW, open_app, category="apps",
    ))

    def close_app(app: str) -> ActionResult:
        target = win.APP_TARGETS.get(app.lower().strip(), app)
        win.close_app(target)
        return ActionResult(True, f"Closed {app}.")

    reg.register(ActionSpec(
        "close_app", "Close a running application by name.",
        _str_param("app", "Application name to close"),
        Risk.LOW, close_app, category="apps",
    ))

    def open_folder(folder: str) -> ActionResult:
        known = win.KNOWN_FOLDERS.get(folder.lower().strip())
        path = known or files.safe_path(folder)
        win.open_path(path)
        return ActionResult(True, f"Opening {folder} folder…")

    reg.register(ActionSpec(
        "open_folder", "Open a folder in File Explorer (downloads, documents, desktop, or a path).",
        _str_param("folder", "Folder name or path"),
        Risk.LOW, open_folder, category="apps",
    ))

    # -- System power/state ---------------------------------------------------
    for kind, verb in [("lock", "lock"), ("sleep", "put to sleep")]:
        def make(kind=kind, verb=verb):
            def handler() -> ActionResult:
                win.power_command(kind)
                return ActionResult(True, f"{verb.capitalize()}ing Windows…")
            return handler
        reg.register(ActionSpec(
            f"{kind}_windows", f"{verb.capitalize()} the Windows session.",
            _NO_PARAMS, Risk.LOW, make(), category="power",
        ))

    def shutdown() -> ActionResult:
        win.power_command("shutdown")
        return ActionResult(True, "Shutting down in 5 seconds…")

    reg.register(ActionSpec(
        "shutdown_windows", "Shut down the computer.", _NO_PARAMS, Risk.HIGH, shutdown,
        confirm_prompt=lambda _a: "This will shut down your computer in 5 seconds. Continue?",
        category="power",
    ))

    def restart() -> ActionResult:
        win.power_command("restart")
        return ActionResult(True, "Restarting in 5 seconds…")

    reg.register(ActionSpec(
        "restart_windows", "Restart the computer.", _NO_PARAMS, Risk.HIGH, restart,
        confirm_prompt=lambda _a: "This will restart your computer in 5 seconds. Continue?",
        category="power",
    ))

    # -- Audio / display ------------------------------------------------------
    def volume(direction: str, steps: int = 5) -> ActionResult:
        if direction == "up":
            win.volume_up(steps)
            return ActionResult(True, "Turned the volume up.")
        win.volume_down(steps)
        return ActionResult(True, "Turned the volume down.")

    reg.register(ActionSpec(
        "change_volume", "Turn the system volume up or down.",
        {"type": "object", "properties": {
            "direction": {"type": "string", "enum": ["up", "down"]},
            "steps": {"type": "integer", "description": "Number of 2%% steps", "default": 5},
        }, "required": ["direction"]},
        Risk.LOW, volume, category="audio",
    ))

    def mute() -> ActionResult:
        win.toggle_mute()
        return ActionResult(True, "Toggled mute.")

    reg.register(ActionSpec(
        "toggle_mute", "Mute or unmute the system audio.", _NO_PARAMS, Risk.LOW, mute,
        category="audio",
    ))

    def brightness(percent: int) -> ActionResult:
        win.set_brightness(percent)
        return ActionResult(True, f"Set brightness to {percent}%.")

    reg.register(ActionSpec(
        "set_brightness", "Set the display brightness to a percentage (laptop displays).",
        {"type": "object", "properties": {"percent": {"type": "integer", "minimum": 0, "maximum": 100}},
         "required": ["percent"]},
        Risk.LOW, brightness, category="display",
    ))

    def take_screenshot() -> ActionResult:
        from ..config import data_dir
        from datetime import datetime

        dest = data_dir() / "screenshots" / f"corvus-{datetime.now():%Y%m%d-%H%M%S}.png"
        win.screenshot(dest)
        return ActionResult(True, f"Saved a screenshot to {dest}.", {"path": str(dest)})

    reg.register(ActionSpec(
        "take_screenshot", "Capture a screenshot of the primary display.",
        _NO_PARAMS, Risk.SAFE, take_screenshot, category="display",
    ))

    # -- Media ----------------------------------------------------------------
    for name, fn, desc in [
        ("media_play_pause", win.media_play_pause, "Play or pause the current media."),
        ("media_next", win.media_next, "Skip to the next track."),
        ("media_previous", win.media_prev, "Go to the previous track."),
    ]:
        def make(fn=fn, desc=desc):
            def handler() -> ActionResult:
                fn()
                return ActionResult(True, desc.rstrip("."))
            return handler
        reg.register(ActionSpec(name, desc, _NO_PARAMS, Risk.LOW, make(), category="media"))

    def play_media(query: str, app: str = "youtube") -> ActionResult:
        from urllib.parse import quote_plus
        app_lower = app.lower()
        if "spotify" in app_lower:
            win.open_url(f"spotify:search:{quote_plus(query)}")
            return ActionResult(True, f"Searching Spotify for “{query}”…")
        else:
            win.open_url(f"https://www.youtube.com/results?search_query={quote_plus(query)}")
            return ActionResult(True, f"Searching YouTube for “{query}”…")

    reg.register(ActionSpec(
        "play_media", "Search for music, videos or media to play on a specific app (like Spotify, YouTube).",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What song, artist, or video to search for"},
                "app": {"type": "string", "description": "App to search on (e.g. spotify, youtube)"}
            },
            "required": ["query"]
        },
        Risk.LOW, play_media, category="media",
    ))

    # -- Search ---------------------------------------------------------------
    def web_search(query: str, engine: str = "google", browser: str = "") -> ActionResult:
        from urllib.parse import quote_plus
        base = {"google": "https://www.google.com/search?q=",
                "bing": "https://www.bing.com/search?q="}.get(engine.lower(), "https://www.google.com/search?q=")
        win.open_url(base + quote_plus(query), browser or None)
        b_text = f" in {browser.title()}" if browser else ""
        return ActionResult(True, f"Searching {engine.capitalize()} for “{query}”{b_text}…")

    reg.register(ActionSpec(
        "web_search", "Search the web (Google or Bing) optionally in a specific browser.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for"},
                "engine": {"type": "string", "description": "Search engine to use (google, bing)"},
                "browser": {"type": "string", "description": "Specific browser to use (e.g. chrome, edge, firefox)."}
            },
            "required": ["query"]
        },
        Risk.LOW, web_search, category="search",
    ))

    def search_files(query: str, folder: str = "documents") -> ActionResult:
        root = win.KNOWN_FOLDERS.get(folder.lower(), files.safe_path(folder))
        matches = [str(p) for p in Path(root).rglob(f"*{query}*")][:25]
        msg = f"Found {len(matches)} match(es) for “{query}” in {folder}."
        return ActionResult(True, msg, {"matches": matches})

    reg.register(ActionSpec(
        "search_files", "Search for files by name within a user folder.",
        {"type": "object", "properties": {
            "query": {"type": "string"},
            "folder": {"type": "string", "description": "downloads/documents/desktop or a path", "default": "documents"},
        }, "required": ["query"]},
        Risk.SAFE, search_files, category="search",
    ))

    # -- File management ------------------------------------------------------
    def list_folder(path: str) -> ActionResult:
        entries = files.list_dir(path)
        return ActionResult(True, f"{len(entries)} item(s) in {path}.", {"entries": entries})

    reg.register(ActionSpec(
        "list_folder", "List the contents of a folder.",
        _str_param("path", "Folder path or name"),
        Risk.SAFE, list_folder, category="files",
    ))

    def create_folder(path: str) -> ActionResult:
        target = files.make_dir(path)
        return ActionResult(True, f"Created folder {target}.")

    reg.register(ActionSpec(
        "create_folder", "Create a new folder.",
        _str_param("path", "New folder path"),
        Risk.MEDIUM, create_folder,
        confirm_prompt=lambda a: f"Create a new folder at {a.get('path')}?",
        category="files",
    ))

    def move_item(src: str, dest: str) -> ActionResult:
        result = files.move(src, dest)
        return ActionResult(True, f"Moved to {result}.")

    reg.register(ActionSpec(
        "move_item", "Move a file or folder to a new location.",
        {"type": "object", "properties": {"src": {"type": "string"}, "dest": {"type": "string"}},
         "required": ["src", "dest"]},
        Risk.MEDIUM, move_item,
        confirm_prompt=lambda a: f"Move “{a.get('src')}” to “{a.get('dest')}”?",
        category="files",
    ))

    def copy_item(src: str, dest: str) -> ActionResult:
        result = files.copy(src, dest)
        return ActionResult(True, f"Copied to {result}.")

    reg.register(ActionSpec(
        "copy_item", "Copy a file or folder to a new location.",
        {"type": "object", "properties": {"src": {"type": "string"}, "dest": {"type": "string"}},
         "required": ["src", "dest"]},
        Risk.MEDIUM, copy_item,
        confirm_prompt=lambda a: f"Copy “{a.get('src')}” to “{a.get('dest')}”?",
        category="files",
    ))

    def rename_item(src: str, new_name: str) -> ActionResult:
        result = files.rename(src, new_name)
        return ActionResult(True, f"Renamed to {result.name}.")

    reg.register(ActionSpec(
        "rename_item", "Rename a file or folder.",
        {"type": "object", "properties": {"src": {"type": "string"}, "new_name": {"type": "string"}},
         "required": ["src", "new_name"]},
        Risk.MEDIUM, rename_item,
        confirm_prompt=lambda a: f"Rename “{a.get('src')}” to “{a.get('new_name')}”?",
        category="files",
    ))

    def delete_item(path: str) -> ActionResult:
        what = files.delete(path)
        return ActionResult(True, f"Deleted {what}.")

    reg.register(ActionSpec(
        "delete_item", "Permanently delete a file or folder.",
        _str_param("path", "Path to delete"),
        Risk.HIGH, delete_item,
        confirm_prompt=lambda a: f"This will permanently delete “{a.get('path')}”. Continue?",
        category="files",
    ))

    def zip_folder(src: str, dest: str) -> ActionResult:
        win.zip_dir(files.safe_path(src), files.safe_path(dest))
        return ActionResult(True, f"Created archive {dest}.")

    reg.register(ActionSpec(
        "zip_folder", "Compress a folder into a .zip archive.",
        {"type": "object", "properties": {"src": {"type": "string"}, "dest": {"type": "string"}},
         "required": ["src", "dest"]},
        Risk.MEDIUM, zip_folder,
        confirm_prompt=lambda a: f"Create a zip of “{a.get('src')}” at “{a.get('dest')}”?",
        category="files",
    ))

    def extract_zip(src: str, dest: str) -> ActionResult:
        win.unzip(files.safe_path(src), files.make_dir(dest))
        return ActionResult(True, f"Extracted {src} to {dest}.")

    reg.register(ActionSpec(
        "extract_zip", "Extract a .zip archive into a folder.",
        {"type": "object", "properties": {"src": {"type": "string"}, "dest": {"type": "string"}},
         "required": ["src", "dest"]},
        Risk.MEDIUM, extract_zip,
        confirm_prompt=lambda a: f"Extract “{a.get('src')}” into “{a.get('dest')}”?",
        category="files",
    ))

    def clean_temp_files() -> ActionResult:
        result = files.clean_temp()
        return ActionResult(True, f"Deleted {result['deleted']} temp files ({result['freed_mb']} MB freed).", result)

    reg.register(ActionSpec(
        "clean_temp_files", "Delete temporary files from the user temp folder.",
        _NO_PARAMS, Risk.HIGH, clean_temp_files,
        confirm_prompt=lambda _a: "This will delete deletable files from your Windows temp folder. Continue?",
        category="files",
    ))

    # -- Software (winget) ----------------------------------------------------
    def install_software(package_id: str) -> ActionResult:
        result = win.winget_install(package_id)
        ok = result.returncode == 0
        return ActionResult(ok, ("Installed " if ok else "Install failed for ") + package_id,
                            {"stdout": result.stdout[-500:]})

    reg.register(ActionSpec(
        "install_software", "Install software via winget by its exact package ID (e.g. Mozilla.Firefox).",
        _str_param("package_id", "Exact winget package ID"),
        Risk.HIGH, install_software,
        confirm_prompt=lambda a: f"Install “{a.get('package_id')}” via winget? This downloads and runs an installer.",
        category="software",
    ))

    def uninstall_software(package_id: str) -> ActionResult:
        result = win.winget_uninstall(package_id)
        ok = result.returncode == 0
        return ActionResult(ok, ("Uninstalled " if ok else "Uninstall failed for ") + package_id)

    reg.register(ActionSpec(
        "uninstall_software", "Uninstall software via winget by its exact package ID.",
        _str_param("package_id", "Exact winget package ID"),
        Risk.HIGH, uninstall_software,
        confirm_prompt=lambda a: f"Uninstall “{a.get('package_id')}”? This removes the app.",
        category="software",
    ))

    # -- Clipboard ------------------------------------------------------------
    def get_clipboard() -> ActionResult:
        text = win.read_clipboard()
        return ActionResult(True, f"Clipboard has {len(text)} characters.", {"text": text})

    reg.register(ActionSpec(
        "read_clipboard", (
            "Read the current text on the clipboard. ONLY use when the user EXPLICITLY asks "
            "you to read or paste what they copied. NEVER use for greetings or general questions."
        ),
        _NO_PARAMS, Risk.SAFE, get_clipboard, category="clipboard",
    ))

    def set_clipboard(text: str) -> ActionResult:
        win.write_clipboard(text)
        return ActionResult(True, "Copied text to the clipboard.")

    reg.register(ActionSpec(
        "write_clipboard", (
            "Copy text to the clipboard. ONLY use when the user EXPLICITLY asks you to copy "
            "something. NEVER use for greetings or general questions."
        ),
        _str_param("text", "Text to copy"),
        Risk.LOW, set_clipboard, category="clipboard",
    ))

    # -- System monitoring ----------------------------------------------------
    def system_status() -> ActionResult:
        data = {
            "battery": monitor.battery(),
            "cpu_percent": monitor.cpu_percent(),
            "ram": monitor.ram(),
            "disk": monitor.disk(),
            "gpu": monitor.gpu_temperature(),
        }
        bat = data["battery"]
        bat_txt = f"{bat['percent']}%{' charging' if bat.get('charging') else ''}" if bat["present"] else "no battery"
        summary = (
            f"CPU {data['cpu_percent']:.0f}%, RAM {data['ram']['used_percent']}% used, "
            f"disk {data['disk']['used_percent']}% used, battery {bat_txt}."
        )
        return ActionResult(True, summary, data)

    reg.register(ActionSpec(
        "system_status", (
            "Report CPU, RAM, disk, battery, and GPU status. ONLY use when the user EXPLICITLY "
            "asks about system performance, battery, or specs. NEVER use for greetings."
        ),
        _NO_PARAMS, Risk.SAFE, system_status, category="monitoring",
    ))

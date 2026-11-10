"""Low-level Windows helpers used by action handlers.

Isolated here so handlers stay declarative and this file holds the OS-specific
subprocess/ctypes/winget calls that are awkward to unit test. Everything is
best-effort and raises on failure so the registry reports it to the user.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

# Friendly app name -> launch target. winget/Start handles resolution; we keep
# a curated map for commonly requested apps. Values can be:
#   - A plain executable name (resolved via PATH / App Paths)
#   - A shell: URI for UWP/Store apps
#   - A full path for apps in non-standard locations
APP_TARGETS: dict[str, str] = {
    # Browsers
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "firefox": "firefox",
    "brave": "brave",
    "opera": "opera",
    "vivaldi": "vivaldi",
    # Dev tools
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "visual studio": "devenv",
    "terminal": "wt",
    "windows terminal": "wt",
    "cmd": "cmd",
    "powershell": "powershell",
    "git bash": "git-bash",
    "postman": "postman",
    "docker": "docker",
    "docker desktop": "docker",
    # System
    "notepad": "notepad",
    "explorer": "explorer",
    "file explorer": "explorer",
    "calculator": "calc",
    "task manager": "taskmgr",
    "control panel": "control",
    "settings": "ms-settings:",
    "paint": "mspaint",
    "snipping tool": "snippingtool",
    "wordpad": "write",
    "device manager": "devmgmt.msc",
    "disk management": "diskmgmt.msc",
    # Media / Creative
    "spotify": "spotify",
    "vlc": "vlc",
    "obs": "obs64",
    "obs studio": "obs64",
    "audacity": "audacity",
    # Gaming
    "steam": "steam",
    "epic games": "com.epicgames.launcher:",
    "epic games launcher": "com.epicgames.launcher:",
    "discord": "discord",
    # Productivity
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "outlook": "outlook",
    "teams": "ms-teams:",
    "microsoft teams": "ms-teams:",
    "onenote": "onenote",
    "notion": "notion",
    "slack": "slack",
    "zoom": "zoom",
    "telegram": "telegram",
    "whatsapp": "whatsapp:",
    # Creative
    "photoshop": "photoshop",
    "blender": "blender",
    "figma": "figma",
    "gimp": "gimp",
    # Utilities
    "7-zip": "7zFM",
    "7zip": "7zFM",
    "winrar": "winrar",
}

KNOWN_FOLDERS = {
    "downloads": Path.home() / "Downloads",
    "documents": Path.home() / "Documents",
    "desktop": Path.home() / "Desktop",
    "pictures": Path.home() / "Pictures",
    "music": Path.home() / "Music",
    "videos": Path.home() / "Videos",
}


def _find_start_menu_shortcut(name: str) -> Path | None:
    """Search Start Menu folders for a .lnk matching the app name."""
    search_dirs = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]
    name_lower = name.lower()
    for d in search_dirs:
        if not d.exists():
            continue
        for lnk in d.rglob("*.lnk"):
            if name_lower in lnk.stem.lower():
                return lnk
    return None


def _run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=30, **kw)


# A free-form app name: letters, digits, spaces and . + - _ only. No paths,
# URI schemes, wildcards or shell metacharacters - those can launch arbitrary
# files or inject commands, and these actions run without a confirmation.
_PLAIN_NAME = re.compile(r"[\w][\w .+\-]{0,63}")
_TRUSTED_TARGETS = set(APP_TARGETS.values())


def _check_plain_name(name: str) -> str:
    name = name.strip()
    if not _PLAIN_NAME.fullmatch(name) or ".." in name:
        raise ValueError(f"“{name}” isn't an app name Corvus can open or close.")
    return name


def launch_app(target: str) -> None:
    """Start an app by curated target, Start Menu shortcut, or App Paths name.

    Uses ShellExecute (os.startfile), never `cmd /c start`, so no command
    parser ever sees the target.
    """
    if target in _TRUSTED_TARGETS:
        if ":" in target:  # curated URI scheme (ms-settings:, ms-teams:, …)
            os.startfile(target)
            return
    else:
        target = _check_plain_name(target)

    shortcut = _find_start_menu_shortcut(target)
    if shortcut:
        os.startfile(str(shortcut))
        return
    try:
        os.startfile(target)  # resolves PATH and App Paths entries
    except OSError as exc:
        raise RuntimeError(f"Couldn't find an app called “{target}”.") from exc


def close_app(image: str) -> int:
    """Terminate processes by image name; returns how many were asked to close."""
    image = _check_plain_name(image)
    exe = image if image.lower().endswith(".exe") else f"{image}.exe"
    result = _run(["taskkill", "/IM", exe, "/F"])
    return 0 if "not found" in (result.stderr + result.stdout).lower() else 1


def open_path(path: Path) -> None:
    os.startfile(str(path))  # noqa: S606 - opening a user folder/file by design


def set_volume_mute(mute: bool) -> None:
    _nircmd_or_key("mute" if mute else "unmute")


def _send_media_key(vk: int) -> None:
    import ctypes

    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)


def volume_up(steps: int = 5) -> None:
    for _ in range(steps):
        _send_media_key(0xAF)  # VK_VOLUME_UP


def volume_down(steps: int = 5) -> None:
    for _ in range(steps):
        _send_media_key(0xAE)  # VK_VOLUME_DOWN


def toggle_mute() -> None:
    _send_media_key(0xAD)  # VK_VOLUME_MUTE


def media_play_pause() -> None:
    _send_media_key(0xB3)  # VK_MEDIA_PLAY_PAUSE


def media_next() -> None:
    _send_media_key(0xB0)


def media_prev() -> None:
    _send_media_key(0xB1)


def _nircmd_or_key(_action: str) -> None:
    toggle_mute()


def set_brightness(percent: int) -> None:
    """Set display brightness via WMI (laptop panels)."""
    percent = max(0, min(100, percent))
    ps = (
        "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
        f".WmiSetBrightness(1,{percent})"
    )
    _run(["powershell", "-NoProfile", "-Command", ps])


def screenshot(dest: Path) -> Path:
    """Capture the primary screen to a PNG, in-process.

    Uses Pillow's ImageGrab rather than shelling out to PowerShell: under a
    Microsoft Store Python the data dir is filesystem-virtualized, so a file an
    external process writes lands at a different physical path than the backend
    reads back. Keeping capture and read in the same process avoids that split.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    from PIL import ImageGrab

    image = ImageGrab.grab()
    image.save(str(dest), "PNG")
    return dest


def power_command(kind: str) -> None:
    mapping = {
        "shutdown": ["shutdown", "/s", "/t", "5"],
        "restart": ["shutdown", "/r", "/t", "5"],
        "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
        "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
    }
    subprocess.Popen(mapping[kind])


def open_url(url: str, browser: str | None = None) -> None:
    if browser:
        target = APP_TARGETS.get(browser.lower().strip()) or _check_plain_name(browser)
        # ShellExecute with the URL as a quoted argument - no cmd parsing.
        arg = '"' + url.replace('"', "%22") + '"'
        try:
            os.startfile(target, "open", arg)
            return
        except OSError:
            shortcut = _find_start_menu_shortcut(target)
            if shortcut:
                os.startfile(str(shortcut), "open", arg)
                return

    os.startfile(url)  # noqa: S606


def winget_install(package_id: str) -> subprocess.CompletedProcess:
    return _run(
        ["winget", "install", "--id", package_id, "-e", "--accept-package-agreements",
         "--accept-source-agreements", "--silent"],
        timeout=600,
    )


def winget_uninstall(package_id: str) -> subprocess.CompletedProcess:
    return _run(["winget", "uninstall", "--id", package_id, "-e", "--silent"], timeout=300)


def read_clipboard() -> str:
    result = _run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"])
    return result.stdout.rstrip("\n")


def write_clipboard(text: str) -> None:
    proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
    proc.communicate(text.encode("utf-16-le"))


def zip_dir(src: Path, dest: Path) -> None:
    base = dest.with_suffix("") if dest.suffix == ".zip" else dest
    shutil.make_archive(str(base), "zip", str(src))


def unzip(src: Path, dest: Path) -> None:
    import tarfile
    import zipfile

    dest = dest.resolve()
    
    # Inspect the archive to prevent ZipSlip/TarSlip vulnerabilities
    if zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as zf:
            for member in zf.namelist():
                if not (dest / member).resolve().is_relative_to(dest):
                    raise ValueError(f"Security error: '{member}' attempts to extract outside destination.")
            zf.extractall(dest)
    elif tarfile.is_tarfile(src):
        with tarfile.open(src) as tf:
            for member in tf.getmembers():
                if not (dest / member.name).resolve().is_relative_to(dest):
                    raise ValueError(f"Security error: '{member.name}' attempts to extract outside destination.")
            if hasattr(tarfile, "data_filter"):
                tf.extractall(dest, filter="data")
            else:
                tf.extractall(dest)
    else:
        shutil.unpack_archive(str(src), str(dest))

"""Low-level Windows helpers used by action handlers.

Isolated here so handlers stay declarative and this file holds the OS-specific
subprocess/ctypes/winget calls that are awkward to unit test. Everything is
best-effort and raises on failure so the registry reports it to the user.
"""

import os
import shutil
import subprocess
from pathlib import Path

# Friendly app name -> launch target. winget/Start handles resolution; we keep
# a small curated map for the apps named in the product spec.
APP_TARGETS: dict[str, str] = {
    "chrome": "chrome",
    "edge": "msedge",
    "vscode": "code",
    "vs code": "code",
    "notepad": "notepad",
    "explorer": "explorer",
    "spotify": "spotify",
    "steam": "steam",
    "photoshop": "photoshop",
    "blender": "blender",
    "obs": "obs64",
    "calculator": "calc",
}

KNOWN_FOLDERS = {
    "downloads": Path.home() / "Downloads",
    "documents": Path.home() / "Documents",
    "desktop": Path.home() / "Desktop",
    "pictures": Path.home() / "Pictures",
    "music": Path.home() / "Music",
    "videos": Path.home() / "Videos",
}


def _run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=30, **kw)


def launch_app(target: str) -> None:
    """Start an app by executable/alias via the shell 'start' verb."""
    # 'start' resolves PATH apps and registered App Paths without a full path.
    subprocess.Popen(["cmd", "/c", "start", "", target], shell=False)


def close_app(image: str) -> int:
    """Terminate processes by image name; returns how many were asked to close."""
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
    dest.parent.mkdir(parents=True, exist_ok=True)
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
        "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
        "$g=[System.Drawing.Graphics]::FromImage($bmp);"
        "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
        f"$bmp.Save('{dest.as_posix()}');$g.Dispose();$bmp.Dispose()"
    )
    _run(["powershell", "-NoProfile", "-Command", ps])
    return dest


def power_command(kind: str) -> None:
    mapping = {
        "shutdown": ["shutdown", "/s", "/t", "5"],
        "restart": ["shutdown", "/r", "/t", "5"],
        "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
        "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
    }
    subprocess.Popen(mapping[kind])


def open_url(url: str) -> None:
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
    shutil.unpack_archive(str(src), str(dest))

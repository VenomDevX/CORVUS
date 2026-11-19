"""File-management helpers with a safety guard.

All paths are resolved and constrained to the user profile tree - Corvus
won't touch system directories even if the model asks. Destructive ops are
still gated by confirmation at the registry level; this is defense in depth.
"""

import re
import shutil
from pathlib import Path

USER_ROOT = Path.home().resolve()


class PathNotAllowed(Exception):
    pass


# "C:\Users\<name>\rest" or "/Users/<name>/rest" (also /home/<name>).
_HOME_ALIAS = re.compile(r"^(?:[a-zA-Z]:)?[\\/]+(?:users|home)[\\/]+([^\\/]+)(?:[\\/]+(.*))?$", re.IGNORECASE)


def _unalias_home(raw: str) -> str:
    r"""Local models invent home folders ("C:\Users\YourUsername\Desktop",
    "/Users/your-username/..."). A home folder that doesn't exist on this PC
    means the user's own, so map it there; real paths are left alone."""
    raw = raw.strip()
    m = _HOME_ALIAS.match(raw)
    try:
        real_user = bool(m) and Path(raw[: m.end(1)]).exists()
    except OSError:  # e.g. "<" in a made-up name
        real_user = False
    if not m or real_user:
        return raw
    return str(USER_ROOT / (m.group(2) or ""))


def safe_path(raw: str) -> Path:
    """Resolve a path and ensure it stays within the user profile."""
    try:
        p = Path(_unalias_home(raw)).expanduser()
    except RuntimeError as exc:  # "~other" names another user's home: never ours
        raise PathNotAllowed(f"{raw} is outside your user folder; Corvus won't touch it.") from exc
    if not p.is_absolute():
        p = USER_ROOT / p
    resolved = p.resolve()
    if USER_ROOT not in resolved.parents and resolved != USER_ROOT:
        raise PathNotAllowed(f"{resolved} is outside your user folder; Corvus won't touch it.")
    return resolved


def shown(raw: object) -> str:
    """The path a confirmation card should show: where the action really lands."""
    try:
        return str(safe_path(str(raw)))
    except (PathNotAllowed, OSError, ValueError):
        return str(raw)


def list_dir(path: str) -> list[dict]:
    target = safe_path(path)
    if not target.is_dir():
        raise NotADirectoryError(f"{target} is not a folder")
    entries = []
    for child in sorted(target.iterdir()):
        entries.append({
            "name": child.name,
            "is_dir": child.is_dir(),
            "size": child.stat().st_size if child.is_file() else None,
        })
    return entries


def make_dir(path: str) -> Path:
    target = safe_path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def move(src: str, dest: str) -> Path:
    s, d = safe_path(src), safe_path(dest)
    return Path(shutil.move(str(s), str(d)))


def copy(src: str, dest: str) -> Path:
    s, d = safe_path(src), safe_path(dest)
    if s.is_dir():
        shutil.copytree(s, d)
        return d
    return Path(shutil.copy2(s, d))


def rename(src: str, new_name: str) -> Path:
    s = safe_path(src)
    dest = s.with_name(new_name)
    safe_path(str(dest))  # ensure target is allowed too
    s.rename(dest)
    return dest


def recycle(target: Path) -> None:
    """Move a file or folder to the Windows Recycle Bin (undoable delete)."""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 0x4, 0x10, 0x40, 0x400
    op = SHFILEOPSTRUCTW(
        wFunc=FO_DELETE,
        pFrom=str(target) + "\0",  # double-NUL-terminated list (ctypes adds the second)
        fFlags=FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI,
    )
    code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if code != 0 or op.fAnyOperationsAborted:
        raise OSError(f"couldn't move {target.name} to the Recycle Bin (error {code})")


def delete(path: str) -> str:
    target = safe_path(path)
    if not target.exists():
        raise FileNotFoundError(f"{target} doesn't exist")
    kind = "folder" if target.is_dir() else "file"
    recycle(target)
    return f"{kind} {target.name}"


def clean_temp() -> dict:
    """Delete files in the user temp dir; returns count and bytes freed."""
    import tempfile

    temp = Path(tempfile.gettempdir())
    count = 0
    freed = 0
    for child in temp.iterdir():
        try:
            if child.is_file():
                freed += child.stat().st_size
                child.unlink()
                count += 1
        except (PermissionError, OSError):
            continue  # in-use temp files are expected; skip them
    return {"deleted": count, "freed_mb": round(freed / 1e6, 1), "dir": str(temp)}

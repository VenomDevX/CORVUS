"""File-management helpers with a safety guard.

All paths are resolved and constrained to the user profile tree - Corvus
won't touch system directories even if the model asks. Destructive ops are
still gated by confirmation at the registry level; this is defense in depth.
"""

import shutil
from pathlib import Path

USER_ROOT = Path.home().resolve()


class PathNotAllowed(Exception):
    pass


def safe_path(raw: str) -> Path:
    """Resolve a path and ensure it stays within the user profile."""
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = USER_ROOT / p
    resolved = p.resolve()
    if USER_ROOT not in resolved.parents and resolved != USER_ROOT:
        raise PathNotAllowed(f"{resolved} is outside your user folder; Corvus won't touch it.")
    return resolved


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


def delete(path: str) -> str:
    target = safe_path(path)
    if target.is_dir():
        shutil.rmtree(target)
        return f"folder {target.name}"
    target.unlink()
    return f"file {target.name}"


def clean_temp() -> dict:
    """Delete files in the user temp dir; returns count and bytes freed."""
    import os
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

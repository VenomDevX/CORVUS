"""Retention: age out screenshots, uploads and downloads Corvus created.

Every read_screen_text / screenshot leaves a full-screen PNG behind, and
attachments pile up in uploads/. Each folder has a per-user setting
`retention_days:<folder>`; 0 means keep forever.
"""

from __future__ import annotations

import asyncio
import time

import structlog

from .config import data_dir

log = structlog.get_logger("corvus")

DEFAULT_DAYS = {"screenshots": 30, "uploads": 30, "downloads": 0}


def retention_days(repo) -> dict[str, int]:
    out = {}
    for folder, default in DEFAULT_DAYS.items():
        raw = repo.get_setting(f"retention_days:{folder}")
        out[folder] = int(raw) if raw is not None and raw.isdigit() else default
    return out


def set_retention_days(repo, values: dict[str, int]) -> None:
    for folder, days in values.items():
        if folder not in DEFAULT_DAYS:
            raise ValueError(f"unknown folder: {folder}")
        if not isinstance(days, int) or isinstance(days, bool) or not 0 <= days <= 3650:
            raise ValueError("retention must be 0-3650 days")
        repo.set_setting(f"retention_days:{folder}", str(days))


def sweep(repo, now: float | None = None) -> int:
    """Delete files older than each folder's retention; returns how many."""
    now = now or time.time()
    removed = 0
    for folder, days in retention_days(repo).items():
        root = data_dir() / folder
        if days == 0 or not root.is_dir():
            continue
        cutoff = now - days * 86400
        for f in root.rglob("*"):
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink()
                    removed += 1
            except OSError:
                continue  # in use: try again next sweep
    if removed:
        log.info("retention_swept", removed=removed)
    return removed


async def retention_loop(repo) -> None:
    """Sweep at startup, then every 6 hours, off the event loop."""
    while True:
        try:
            await asyncio.to_thread(sweep, repo)
        except Exception as exc:  # noqa: BLE001 - a sweep failure must never stop the app
            log.warning("retention_sweep_failed", error=str(exc))
        await asyncio.sleep(6 * 3600)

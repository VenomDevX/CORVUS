"""Structured logging for Corvus: JSON lines to disk, pretty console in dev.

The on-disk format is one JSON object per line with at least
timestamp/level/event keys - the Logs sidebar view renders these directly.
"""

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog

from . import __version__
from .config import log_path

_configured = False

# Cap the log so it never grows without bound: 2 MB per file, 3 rotations kept.
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUPS = 3


def setup_logging() -> structlog.stdlib.BoundLogger:
    global _configured
    logger = structlog.get_logger("corvus")
    if _configured:
        return logger

    handler = RotatingFileHandler(
        log_path(), maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger("corvus")
    root.setLevel(logging.INFO)
    root.handlers = [handler, console]
    root.propagate = False

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    _configured = True
    logger.info("corvus_start", version=__version__, app="Corvus")
    return logger


def tail_log(limit: int = 200, path: Path | None = None) -> list[dict]:
    """Return the last `limit` structured entries from the log file."""
    target = path or log_path()
    if not target.exists():
        return []
    lines = target.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    entries: list[dict] = []
    for line in lines[-limit:]:
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                entries.append(parsed)
        except json.JSONDecodeError:
            continue
    return entries

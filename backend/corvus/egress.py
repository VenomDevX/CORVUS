"""What Corvus sent off this machine during this session.

Every request to a cloud LLM (and to Microsoft's Edge TTS) is recorded here -
size and what kind of local content it carried, never the content itself - so
the Privacy view can show the user exactly what left the computer. In-memory
by design: the session is the app run, and a durable log of it would itself be
sensitive.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime

from .untrusted import UNTRUSTED_BEGIN

MAX_ENTRIES = 500
_entries: deque[dict] = deque(maxlen=MAX_ENTRIES)
_lock = threading.Lock()

# Tool result -> what local content it put into the conversation.
_TOOL_CONTENT = {
    "read_screen_text": "screen",
    "describe_image": "image",
    "search_documents": "documents",
    "read_clipboard": "clipboard",
    "list_folder": "files",
    "search_files": "files",
}


def classify(messages) -> list[str]:
    """Kinds of local/outside content present in an outgoing conversation."""
    kinds: set[str] = set()
    for m in messages:
        tool = getattr(m, "tool_name", None)
        if tool:
            kinds.add("web" if tool.startswith("browser_") else _TOOL_CONTENT.get(tool, "tool result"))
        elif UNTRUSTED_BEGIN in (getattr(m, "content", "") or ""):
            kinds.add("outside content")
    return sorted(kinds)


def record(destination: str, kind: str, chars: int, contains: list[str] | None = None,
           model: str = "") -> None:
    with _lock:
        _entries.append({
            "time": datetime.now().isoformat(timespec="seconds"),
            "destination": destination,
            "model": model,
            "kind": kind,
            "chars": chars,
            "contains": contains or [],
        })


def record_messages(destination: str, kind: str, messages, model: str) -> None:
    chars = sum(len(getattr(m, "content", "") or "") for m in messages)
    record(destination, kind, chars, classify(messages), model)


def entries() -> list[dict]:
    with _lock:
        return list(reversed(_entries))


def clear() -> None:
    with _lock:
        _entries.clear()

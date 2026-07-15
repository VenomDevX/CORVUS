"""Repository layer over the Corvus SQLite database.

Thin, explicit SQL - no ORM. One Repository instance owns one connection;
FastAPI keeps a single instance on app.state (SQLite serializes writes).
"""

import sqlite3
from pathlib import Path
from typing import Any

from .db import connect

MEMORY_CATEGORIES = ("preference", "project", "person", "app")


def _rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


class Repository:
    def __init__(self, path: Path):
        self.conn = connect(path)

    def close(self) -> None:
        self.conn.close()

    # -- conversations -----------------------------------------------------

    def create_conversation(self, title: str) -> dict[str, Any]:
        cur = self.conn.execute(
            "INSERT INTO conversations (title) VALUES (?) RETURNING *", (title.strip() or "New chat",)
        )
        row = dict(cur.fetchone())
        self.conn.commit()
        return row

    def list_conversations(self) -> list[dict[str, Any]]:
        return _rows(self.conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC"))

    def get_conversation(self, conversation_id: int) -> dict[str, Any] | None:
        cur = self.conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def delete_conversation(self, conversation_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def touch_conversation(self, conversation_id: int) -> None:
        self.conn.execute(
            "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?", (conversation_id,)
        )
        self.conn.commit()

    # -- messages ----------------------------------------------------------

    def add_message(self, conversation_id: int, role: str, content: str) -> dict[str, Any]:
        cur = self.conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?) RETURNING *",
            (conversation_id, role, content),
        )
        row = dict(cur.fetchone())
        self.conn.commit()
        self.touch_conversation(conversation_id)
        return row

    def list_messages(self, conversation_id: int) -> list[dict[str, Any]]:
        return _rows(
            self.conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
            )
        )

    # -- memories ----------------------------------------------------------

    def add_memory(
        self, category: str, content: str, source_conversation: int | None = None
    ) -> dict[str, Any]:
        if category not in MEMORY_CATEGORIES:
            raise ValueError(f"invalid memory category: {category}")
        cur = self.conn.execute(
            "INSERT INTO memories (category, content, source_conversation) VALUES (?, ?, ?) RETURNING *",
            (category, content, source_conversation),
        )
        row = dict(cur.fetchone())
        self.conn.commit()
        return row

    def list_memories(self) -> list[dict[str, Any]]:
        return _rows(self.conn.execute("SELECT * FROM memories ORDER BY created_at DESC, id DESC"))

    def delete_memory(self, memory_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def memory_exists(self, content: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM memories WHERE lower(content) = lower(?) LIMIT 1", (content,)
        )
        return cur.fetchone() is not None

    # -- action log --------------------------------------------------------

    def log_action(
        self, conversation_id: int | None, action: str, arguments: dict,
        outcome: str, message: str,
    ) -> dict[str, Any]:
        import json

        cur = self.conn.execute(
            "INSERT INTO action_log (conversation_id, action, arguments, outcome, message) "
            "VALUES (?, ?, ?, ?, ?) RETURNING *",
            (conversation_id, action, json.dumps(arguments), outcome, message),
        )
        row = dict(cur.fetchone())
        self.conn.commit()
        return row

    def list_actions(self, limit: int = 100) -> list[dict[str, Any]]:
        return _rows(
            self.conn.execute("SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (limit,))
        )

    # -- reminders ---------------------------------------------------------

    def add_reminder(self, text: str, kind: str, fire_at: str) -> dict[str, Any]:
        cur = self.conn.execute(
            "INSERT INTO reminders (text, kind, fire_at) VALUES (?, ?, ?) RETURNING *",
            (text, kind, fire_at),
        )
        row = dict(cur.fetchone())
        self.conn.commit()
        return row

    def pending_reminders(self) -> list[dict[str, Any]]:
        return _rows(
            self.conn.execute("SELECT * FROM reminders WHERE fired = 0 ORDER BY fire_at")
        )

    def mark_reminder_fired(self, reminder_id: int) -> None:
        self.conn.execute("UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,))
        self.conn.commit()

    def delete_reminder(self, reminder_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # -- settings ----------------------------------------------------------

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        cur = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

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

    def get_message(self, message_id: int) -> dict[str, Any] | None:
        cur = self.conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def update_message(self, message_id: int, content: str) -> None:
        self.conn.execute("UPDATE messages SET content = ? WHERE id = ?", (content, message_id))
        self.conn.commit()

    def delete_messages_after(self, conversation_id: int, message_id: int) -> None:
        self.conn.execute(
            "DELETE FROM messages WHERE conversation_id = ? AND id > ?", (conversation_id, message_id)
        )
        self.conn.commit()

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

    # -- voiceovers (Voice Studio) -------------------------------------------

    def add_voiceover(
        self, text: str, engine: str, voice: str,
        rate: int, pitch: int, volume: int, filename: str,
    ) -> dict[str, Any]:
        cur = self.conn.execute(
            "INSERT INTO voiceovers (text, engine, voice, rate, pitch, volume, filename)"
            " VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING *",
            (text, engine, voice, rate, pitch, volume, filename),
        )
        row = dict(cur.fetchone())
        self.conn.commit()
        return row

    def list_voiceovers(self) -> list[dict[str, Any]]:
        return _rows(self.conn.execute("SELECT * FROM voiceovers ORDER BY id DESC"))

    def get_voiceover(self, voiceover_id: int) -> dict[str, Any] | None:
        cur = self.conn.execute("SELECT * FROM voiceovers WHERE id = ?", (voiceover_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def delete_voiceover(self, voiceover_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM voiceovers WHERE id = ?", (voiceover_id,))
        self.conn.commit()
        return cur.rowcount > 0

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

    # -- workflows ---------------------------------------------------------

    def create_workflow(self, name: str, steps: list, trigger_type: str = "manual",
                        trigger_config: dict | None = None) -> dict[str, Any]:
        import json

        cur = self.conn.execute(
            "INSERT INTO workflows (name, steps, trigger_type, trigger_config) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET steps=excluded.steps, "
            "trigger_type=excluded.trigger_type, trigger_config=excluded.trigger_config "
            "RETURNING *",
            (name, json.dumps(steps), trigger_type, json.dumps(trigger_config or {})),
        )
        row = dict(cur.fetchone())
        self.conn.commit()
        return row

    def list_workflows(self) -> list[dict[str, Any]]:
        return _rows(self.conn.execute("SELECT * FROM workflows ORDER BY name"))

    def get_workflow(self, name: str) -> dict[str, Any] | None:
        cur = self.conn.execute("SELECT * FROM workflows WHERE name = ?", (name,))
        row = cur.fetchone()
        return dict(row) if row else None

    def delete_workflow(self, name: str) -> bool:
        cur = self.conn.execute("DELETE FROM workflows WHERE name = ?", (name,))
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

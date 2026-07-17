"""Persistence for generated media: rows in SQLite + files on disk."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..config import data_dir

KINDS = ("image", "video", "sfx")
_EXT = {"image": "png", "video": "gif", "sfx": "wav"}


class MediaStore:
    def __init__(self, database: Path | None = None):
        self._db_path = database or (data_dir() / "corvus-media.db")
        self.conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS media_generations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              kind TEXT NOT NULL,
              prompt TEXT NOT NULL,
              params TEXT NOT NULL DEFAULT '{}',
              filename TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self.conn.commit()

    def media_dir(self) -> Path:
        d = data_dir() / "media"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def add(self, kind: str, prompt: str, params: dict, content: bytes) -> dict:
        if kind not in KINDS:
            raise ValueError(f"invalid media kind: {kind}")
        cur = self.conn.execute(
            "INSERT INTO media_generations (kind, prompt, params, filename) VALUES (?, ?, ?, '')"
            " RETURNING id",
            (kind, prompt, json.dumps(params)),
        )
        row_id = cur.fetchone()["id"]
        filename = f"{kind}-{row_id}.{_EXT[kind]}"
        (self.media_dir() / filename).write_bytes(content)
        self.conn.execute(
            "UPDATE media_generations SET filename = ? WHERE id = ?", (filename, row_id)
        )
        self.conn.commit()
        return self.get(row_id)

    def get(self, row_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM media_generations WHERE id = ?", (row_id,)
        ).fetchone()
        return self._out(row) if row else None

    def list(self, kind: str | None = None) -> list[dict]:
        if kind:
            rows = self.conn.execute(
                "SELECT * FROM media_generations WHERE kind = ? ORDER BY id DESC", (kind,)
            )
        else:
            rows = self.conn.execute("SELECT * FROM media_generations ORDER BY id DESC")
        return [self._out(r) for r in rows]

    def file_path(self, row_id: int) -> Path | None:
        row = self.get(row_id)
        if row is None:
            return None
        # Filenames are generated internally, but resolve defensively anyway.
        path = (self.media_dir() / row["filename"]).resolve()
        if self.media_dir().resolve() not in path.parents:
            return None
        return path if path.exists() else None

    def delete(self, row_id: int) -> bool:
        path = self.file_path(row_id)
        cur = self.conn.execute("DELETE FROM media_generations WHERE id = ?", (row_id,))
        self.conn.commit()
        if path is not None:
            path.unlink(missing_ok=True)
        return cur.rowcount > 0

    def _out(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d["params"] = json.loads(d.get("params") or "{}")
        return d

    def close(self) -> None:
        self.conn.close()

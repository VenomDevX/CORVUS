"""Local documents index (RAG) — fully offline.

SQLite FTS5 keyword search is the always-available baseline. When an Ollama
embedding model (nomic-embed-text) is installed, FTS candidates are reranked
by cosine similarity for semantic quality. Nothing ever leaves the machine:
files are read, chunked, and stored in the Corvus SQLite database.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import httpx
import numpy as np
import structlog

from ..config import OLLAMA_URL

log = structlog.get_logger("corvus")

EMBED_MODEL = "nomic-embed-text"
TEXT_EXTS = {".txt", ".md", ".py", ".js", ".ts", ".tsx", ".json", ".csv", ".yml", ".yaml", ".html"}
PDF_EXT = ".pdf"
SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__", "dist", "build"}
CHUNK_CHARS = 1000
CHUNK_OVERLAP = 150
MAX_FILE_BYTES = 20 * 1024 * 1024
FTS_CANDIDATES = 24


def _chunk(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_CHARS
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return [c.strip() for c in chunks if c.strip()]


def _extract_text(path: Path) -> str | None:
    if path.stat().st_size > MAX_FILE_BYTES:
        return None
    if path.suffix.lower() in TEXT_EXTS:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    if path.suffix.lower() == PDF_EXT:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:  # noqa: BLE001 - one bad PDF must not stop the index
            log.warning("rag_pdf_failed", file=str(path), error=str(exc))
            return None
    return None


def _fts_query(query: str) -> str:
    """Sanitize free text into an FTS5 OR-query of bare terms."""
    terms = ["".join(ch for ch in t if ch.isalnum()) for t in query.split()]
    terms = [t for t in terms if t]
    return " OR ".join(f'"{t}"' for t in terms[:12])


class DocsIndex:
    """Owns its own SQLite connection (separate from the main repo) so long
    indexing runs never block chat queries."""

    def __init__(self, database: Path):
        self._db_path = database
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(database, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS rag_files (
              path TEXT PRIMARY KEY, mtime REAL NOT NULL, size INTEGER NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks USING fts5(
              content, path UNINDEXED, chunk_no UNINDEXED
            );
            CREATE TABLE IF NOT EXISTS rag_embeddings (
              path TEXT NOT NULL, chunk_no INTEGER NOT NULL, vector BLOB NOT NULL,
              PRIMARY KEY (path, chunk_no)
            );
            """
        )
        self.conn.commit()
        # Progress state read by /rag/status while an index run is active.
        self.indexing = False
        self.progress = {"done": 0, "total": 0}
        self.embeddings_available: bool | None = None

    # -- embeddings (optional) --------------------------------------------------

    def _check_embeddings(self) -> bool:
        try:
            r = httpx.post(
                f"{OLLAMA_URL}/api/embed",
                json={"model": EMBED_MODEL, "input": "ping"},
                timeout=10,
            )
            ok = r.status_code == 200
        except httpx.HTTPError:
            ok = False
        self.embeddings_available = ok
        return ok

    def _embed(self, texts: list[str]) -> np.ndarray | None:
        try:
            r = httpx.post(
                f"{OLLAMA_URL}/api/embed",
                json={"model": EMBED_MODEL, "input": texts},
                timeout=120,
            )
            if r.status_code != 200:
                return None
            vecs = np.asarray(r.json()["embeddings"], dtype=np.float32)
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            return vecs / norms
        except (httpx.HTTPError, KeyError, ValueError):
            return None

    # -- indexing ---------------------------------------------------------------

    def index_folder(self, folder: Path) -> dict:
        """Incremental index: only changed/new files are re-chunked; rows for
        files that vanished are dropped. Blocking — run via asyncio.to_thread."""
        with self._lock:
            self.indexing = True
            try:
                return self._index_folder(folder)
            finally:
                self.indexing = False

    def _index_folder(self, folder: Path) -> dict:
        use_embeddings = self._check_embeddings()
        files = [
            p
            for p in folder.rglob("*")
            if p.is_file()
            and (p.suffix.lower() in TEXT_EXTS or p.suffix.lower() == PDF_EXT)
            and not any(part.startswith(".") or part in SKIP_DIRS for part in p.parts)
        ]
        self.progress = {"done": 0, "total": len(files)}

        known = {
            row["path"]: (row["mtime"], row["size"])
            for row in self.conn.execute("SELECT * FROM rag_files")
        }
        seen: set[str] = set()
        added = skipped = 0

        for path in files:
            key = str(path)
            seen.add(key)
            stat = path.stat()
            if known.get(key) == (stat.st_mtime, stat.st_size):
                skipped += 1
                self.progress["done"] += 1
                continue
            text = _extract_text(path)
            self._delete_file_rows(key)
            if text:
                chunks = _chunk(text)
                for i, chunk in enumerate(chunks):
                    self.conn.execute(
                        "INSERT INTO rag_chunks (content, path, chunk_no) VALUES (?, ?, ?)",
                        (chunk, key, i),
                    )
                if use_embeddings and chunks:
                    vecs = self._embed(chunks)
                    if vecs is not None:
                        for i, v in enumerate(vecs):
                            self.conn.execute(
                                "INSERT OR REPLACE INTO rag_embeddings (path, chunk_no, vector)"
                                " VALUES (?, ?, ?)",
                                (key, i, v.tobytes()),
                            )
                self.conn.execute(
                    "INSERT OR REPLACE INTO rag_files (path, mtime, size) VALUES (?, ?, ?)",
                    (key, stat.st_mtime, stat.st_size),
                )
                added += 1
            self.progress["done"] += 1
            self.conn.commit()

        # Drop rows for files that no longer exist under the folder.
        removed = 0
        for key in set(known) - seen:
            if Path(key).is_relative_to(folder):
                self._delete_file_rows(key)
                self.conn.execute("DELETE FROM rag_files WHERE path = ?", (key,))
                removed += 1
        self.conn.commit()
        log.info(
            "rag_indexed", folder=str(folder), added=added, skipped=skipped, removed=removed,
            embeddings=use_embeddings,
        )
        return {"files": len(files), "added": added, "skipped": skipped, "removed": removed}

    def _delete_file_rows(self, key: str) -> None:
        self.conn.execute("DELETE FROM rag_chunks WHERE path = ?", (key,))
        self.conn.execute("DELETE FROM rag_embeddings WHERE path = ?", (key,))

    # -- search -----------------------------------------------------------------

    def search(self, query: str, k: int = 6) -> list[dict]:
        fts = _fts_query(query)
        if not fts:
            return []
        rows = self.conn.execute(
            "SELECT content, path, chunk_no, rank FROM rag_chunks"
            " WHERE rag_chunks MATCH ? ORDER BY rank LIMIT ?",
            (fts, FTS_CANDIDATES),
        ).fetchall()
        results = [
            {"content": r["content"], "path": r["path"], "chunk_no": r["chunk_no"]} for r in rows
        ]
        if not results:
            return []

        # Semantic rerank when the embedding model is around.
        if self.embeddings_available is None:
            self._check_embeddings()
        if self.embeddings_available:
            qv = self._embed([query])
            if qv is not None:
                scored = []
                for item in results:
                    row = self.conn.execute(
                        "SELECT vector FROM rag_embeddings WHERE path = ? AND chunk_no = ?",
                        (item["path"], item["chunk_no"]),
                    ).fetchone()
                    if row is None:
                        vec = self._embed([item["content"]])
                        if vec is None:
                            continue
                        v = vec[0]
                    else:
                        v = np.frombuffer(row["vector"], dtype=np.float32)
                    scored.append((float(np.dot(qv[0], v)), item))
                if scored:
                    scored.sort(key=lambda s: s[0], reverse=True)
                    results = [dict(item, score=round(score, 4)) for score, item in scored]

        return results[:k]

    def status(self) -> dict:
        files = self.conn.execute("SELECT COUNT(*) AS n FROM rag_files").fetchone()["n"]
        chunks = self.conn.execute("SELECT COUNT(*) AS n FROM rag_chunks").fetchone()["n"]
        return {
            "files": files,
            "chunks": chunks,
            "indexing": self.indexing,
            "progress": dict(self.progress),
            "embeddings": bool(self.embeddings_available),
        }

    def close(self) -> None:
        self.conn.close()


def register_rag_actions(registry, index: DocsIndex) -> None:
    """Expose document search to the agent as a safe, read-only action."""
    from ..actions.registry import ActionResult, ActionSpec, Risk
    from ..untrusted import wrap_untrusted

    def search_documents(query: str, max_results: int = 5):
        hits = index.search(query, k=max(1, min(int(max_results), 10)))
        if not hits:
            return ActionResult(True, "No matching passages in the indexed documents.")
        body = "\n\n".join(
            f"[{Path(h['path']).name} · chunk {h['chunk_no']}] {h['content'][:600]}" for h in hits
        )
        files = sorted({Path(h["path"]).name for h in hits})
        return ActionResult(
            True,
            f"Found {len(hits)} passages in {', '.join(files)}:\n" + wrap_untrusted(body),
            data={"results": hits},
        )

    registry.register(
        ActionSpec(
            name="search_documents",
            description=(
                "Search the user's locally indexed documents (PDFs, notes, text files) for passages "
                "relevant to a query. ONLY use when the user EXPLICITLY asks about their own files, "
                "notes, or documents — e.g. 'search my files for X', 'what does my PDF say about Y'. "
                "NEVER use for general knowledge questions, greetings, coding help, or explanations."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look for"},
                    "max_results": {"type": "integer", "description": "1-10, default 5"},
                },
                "required": ["query"],
            },
            risk=Risk.SAFE,
            handler=search_documents,
            category="documents",
        )
    )

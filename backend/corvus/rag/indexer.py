"""Local documents index (RAG) — fully offline.

SQLite FTS5 keyword search is the always-available baseline. When an Ollama
embedding model (nomic-embed-text) is installed, chunks are also embedded into
a ChromaDB store and searched semantically. Nothing ever leaves the machine.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import httpx
import numpy as np
import structlog

from ..config import OLLAMA_URL
from ..memory.vector_db import ChromaManager

log = structlog.get_logger("corvus")

EMBED_MODEL = "nomic-embed-text"
TEXT_EXTS = {".txt", ".md", ".py", ".js", ".ts", ".tsx", ".json", ".csv", ".yml", ".yaml", ".html"}
PDF_EXT = ".pdf"
DOCX_EXT = ".docx"
SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__", "dist", "build"}
CHUNK_CHARS = 1000
CHUNK_OVERLAP = 150
MAX_FILE_BYTES = 20 * 1024 * 1024


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
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTS:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    if suffix == PDF_EXT:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:  # noqa: BLE001 - one bad PDF must not stop the index
            log.warning("rag_pdf_failed", file=str(path), error=str(exc))
            return None
    if suffix == DOCX_EXT:
        try:
            import zipfile

            import docx

            # .docx is a zip: cap the *uncompressed* size so a zip bomb can't
            # exhaust memory under the on-disk size check above.
            with zipfile.ZipFile(path) as zf:
                if sum(info.file_size for info in zf.infolist()) > MAX_FILE_BYTES * 5:
                    log.warning("rag_docx_too_large", file=str(path))
                    return None
            doc = docx.Document(str(path))
            return "\n".join(para.text for para in doc.paragraphs)
        except Exception as exc:  # noqa: BLE001 - one bad .docx must not stop the index
            log.warning("rag_docx_failed", file=str(path), error=str(exc))
            return None
    return None


def _fts_query(query: str) -> str:
    """Sanitize free text into an FTS5 OR-query of bare terms."""
    terms = ["".join(ch for ch in t if ch.isalnum()) for t in query.split()]
    terms = [t for t in terms if t]
    return " OR ".join(f'"{t}"' for t in terms[:12])


class DocsIndex:
    """Owns its own SQLite connection (separate from the main repo) and, once
    embeddings are available, a ChromaDB store beside it — so long indexing
    runs never block chat queries."""

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
            DROP TABLE IF EXISTS rag_embeddings;
            """
        )
        self.conn.commit()
        # Progress state read by /rag/status while an index run is active.
        self.indexing = False
        self.progress = {"done": 0, "total": 0}
        self.embeddings_available: bool | None = None
        self._chroma: ChromaManager | None = None

    def _vectors_dir(self) -> Path:
        return self._db_path.with_name(self._db_path.stem + "-vectors")

    def _vectors(self) -> ChromaManager | None:
        """The Chroma store, opened lazily so keyword-only use never loads it."""
        if self._chroma is None:
            try:
                self._chroma = ChromaManager(self._vectors_dir())
            except Exception as exc:  # noqa: BLE001 - vectors are optional; FTS still works
                log.warning("rag_chroma_unavailable", error=str(exc))
        return self._chroma

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
        vectors = self._vectors() if self._check_embeddings() else None
        files = [
            p
            for p in folder.rglob("*")
            if p.is_file()
            and (p.suffix.lower() in TEXT_EXTS or p.suffix.lower() in (PDF_EXT, DOCX_EXT))
            # Relative parts only: "C:\Users\u\.notes\docs" or "F:\build\handbook"
            # as the chosen folder must not skip every file in it.
            and not any(
                part.startswith(".") or part in SKIP_DIRS for part in p.relative_to(folder).parts
            )
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
            try:
                stat = path.stat()
                if known.get(key) == (stat.st_mtime, stat.st_size):
                    skipped += 1
                    self.progress["done"] += 1
                    continue
                text = _extract_text(path)
            except OSError as exc:
                # Deleted mid-run or locked by another app: skip it, keep indexing.
                log.warning("rag_file_unreadable", path=key, error=str(exc))
                self.progress["done"] += 1
                continue
            self._delete_file_rows(key)
            if text:
                chunks = _chunk(text)
                self.conn.executemany(
                    "INSERT INTO rag_chunks (content, path, chunk_no) VALUES (?, ?, ?)",
                    [(chunk, key, i) for i, chunk in enumerate(chunks)],
                )
                if vectors is not None and chunks:
                    vecs = self._embed(chunks)
                    if vecs is not None:
                        vectors.add_documents(
                            ids=[f"{key}#{i}" for i in range(len(chunks))],
                            documents=chunks,
                            embeddings=vecs.tolist(),
                            metadatas=[{"path": key, "chunk_no": i} for i in range(len(chunks))],
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
            embeddings=vectors is not None,
        )
        return {"files": len(files), "added": added, "skipped": skipped, "removed": removed}

    def _delete_file_rows(self, key: str) -> None:
        self.conn.execute("DELETE FROM rag_chunks WHERE path = ?", (key,))
        vectors = self._vectors() if self._vectors_dir().exists() else None
        if vectors is not None:
            try:
                vectors.delete_path(key)
            except Exception as exc:  # noqa: BLE001 - stale vectors are filtered at search time
                log.warning("rag_chroma_delete_failed", file=key, error=str(exc))

    # -- search -----------------------------------------------------------------

    def search(self, query: str, k: int = 6) -> list[dict]:
        if not query.strip():
            return []
        if self.embeddings_available is None:
            self._check_embeddings()
        if self.embeddings_available:
            hits = self._semantic_search(query, k)
            if hits:
                return hits
        return self._keyword_search(query, k)

    def _semantic_search(self, query: str, k: int) -> list[dict]:
        vectors = self._vectors()
        if vectors is None or vectors.count() == 0:
            return []
        qv = self._embed([query])
        if qv is None:
            return []
        try:
            res = vectors.query(query_embeddings=qv.tolist(), n_results=k)
        except Exception as exc:  # noqa: BLE001 - fall back to keyword search
            log.warning("rag_semantic_search_failed", error=str(exc))
            return []
        indexed = {r["path"] for r in self.conn.execute("SELECT path FROM rag_files")}
        return [
            {
                "content": doc,
                "path": meta["path"],
                "chunk_no": meta["chunk_no"],
                "score": round(1.0 - dist, 4),
            }
            for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
            if meta["path"] in indexed
        ]

    def _keyword_search(self, query: str, k: int) -> list[dict]:
        fts = _fts_query(query)
        if not fts:
            return []
        rows = self.conn.execute(
            "SELECT content, path, chunk_no FROM rag_chunks"
            " WHERE rag_chunks MATCH ? ORDER BY rank LIMIT ?",
            (fts, k),
        ).fetchall()
        return [{"content": r["content"], "path": r["path"], "chunk_no": r["chunk_no"]} for r in rows]

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
            blocking=True,  # sync httpx embedding call, up to 120s on a cold model
        )
    )

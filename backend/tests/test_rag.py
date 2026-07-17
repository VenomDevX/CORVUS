from pathlib import Path

import pytest

from corvus.actions.registry import Registry
from corvus.rag.indexer import DocsIndex, _chunk, _fts_query, register_rag_actions


@pytest.fixture
def index(tmp_path, monkeypatch):
    # Force keyword-only mode so tests never touch a live Ollama.
    idx = DocsIndex(tmp_path / "rag.db")
    monkeypatch.setattr(idx, "_check_embeddings", lambda: False)
    yield idx
    idx.close()


@pytest.fixture
def docs(tmp_path) -> Path:
    d = tmp_path / "docs"
    d.mkdir()
    (d / "notes.md").write_text("Corvus is a local assistant. The wake word is Hey Corvus.")
    (d / "recipe.txt").write_text("Pasta needs tomatoes, garlic, and fresh basil leaves.")
    (d / "skip.exe").write_bytes(b"\x00\x01")
    return d


def test_index_and_search(index, docs):
    result = index.index_folder(docs)
    assert result["added"] == 2
    hits = index.search("basil pasta")
    assert hits and "basil" in hits[0]["content"]
    assert hits[0]["path"].endswith("recipe.txt")


def test_incremental_reindex_skips_unchanged(index, docs):
    index.index_folder(docs)
    second = index.index_folder(docs)
    assert second["added"] == 0
    assert second["skipped"] == 2


def test_removed_file_leaves_index(index, docs):
    index.index_folder(docs)
    (docs / "recipe.txt").unlink()
    index.index_folder(docs)
    assert index.search("basil") == []
    assert index.status()["files"] == 1


def test_fts_query_sanitized(index, docs):
    index.index_folder(docs)
    # Quotes/operators in free text must not crash FTS5.
    assert index.search('pasta" OR 1=1 -- NEAR( AND NOT') is not None
    assert _fts_query("!!! ???") == ""
    assert index.search("!!!") == []


def test_chunking_overlaps():
    chunks = _chunk("x" * 2500)
    assert len(chunks) == 3
    assert all(len(c) <= 1000 for c in chunks)


def test_search_documents_action(index, docs):
    index.index_folder(docs)
    registry = Registry()
    register_rag_actions(registry, index)
    spec = registry.get("search_documents")
    assert spec is not None and spec.risk.value == "safe"
    result = spec.handler(query="pasta ingredients")
    assert result.ok
    assert "recipe.txt" in result.message
    assert "<<<UNTRUSTED_CONTENT>>>" in result.message

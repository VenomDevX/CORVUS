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


def _fake_embed(texts):
    """Deterministic bag-of-words vectors, so Chroma ranking is testable offline."""
    import numpy as np

    vecs = np.zeros((len(texts), 64), dtype=np.float32)
    for row, text in enumerate(texts):
        for word in text.lower().split():
            vecs[row, hash(word.strip(".,")) % 64] += 1
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


def test_semantic_search_uses_chroma_beside_db(tmp_path, docs, monkeypatch):
    idx = DocsIndex(tmp_path / "rag.db")
    monkeypatch.setattr(idx, "_check_embeddings", lambda: setattr(idx, "embeddings_available", True) or True)
    monkeypatch.setattr(idx, "_embed", _fake_embed)
    idx.index_folder(docs)
    assert (tmp_path / "rag-vectors").is_dir()

    hits = idx.search("basil pasta")
    assert hits[0]["path"].endswith("recipe.txt") and "score" in hits[0]

    # A removed file must disappear from vector results too.
    (docs / "recipe.txt").unlink()
    idx.index_folder(docs)
    assert all(not h["path"].endswith("recipe.txt") for h in idx.search("basil pasta"))
    idx.close()


def test_docx_extracted(index, tmp_path):
    import docx

    d = tmp_path / "word"
    d.mkdir()
    doc = docx.Document()
    doc.add_paragraph("Quarterly budget for the falcon project.")
    doc.save(d / "plan.docx")
    assert index.index_folder(d)["added"] == 1
    assert index.search("falcon")[0]["path"].endswith("plan.docx")


def test_docx_zip_bomb_rejected(index, tmp_path, monkeypatch):
    import zipfile

    from corvus.rag import indexer

    monkeypatch.setattr(indexer, "MAX_FILE_BYTES", 1000)  # uncompressed cap = 5000
    bomb = tmp_path / "bomb.docx"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", "a" * 100_000)  # tiny on disk, large expanded
    assert bomb.stat().st_size < 1000
    assert indexer._extract_text(bomb) is None

"""Property tests for the input sanitizers at trust boundaries (hypothesis)."""

import sqlite3
from pathlib import Path, PurePosixPath

from hypothesis import given, settings
from hypothesis import strategies as st

from corvus.actions import files
from corvus.api.routes import safe_upload_name
from corvus.rag.indexer import _fts_query

# Path-ish text: separators, dots, drive letters, UNC prefixes, unicode.
path_text = st.lists(
    st.sampled_from(list("ab.\\/:~ $%*?<>|\"'\x00") + ["..", "C:", "\\\\host\\", "é", "😀"]),
    max_size=40,
).map("".join)


@settings(max_examples=300, deadline=None)
@given(path_text)
def test_safe_path_never_escapes_home(raw):
    try:
        resolved = files.safe_path(raw)
    except (files.PathNotAllowed, ValueError, OSError):
        return
    assert resolved == files.USER_ROOT or files.USER_ROOT in resolved.parents


@settings(max_examples=500, deadline=None)
@given(st.one_of(st.none(), st.text(max_size=80), path_text))
def test_upload_name_is_a_plain_filename(raw):
    name = safe_upload_name(raw)
    assert name and "/" not in name and "\\" not in name and ":" not in name
    assert ".." not in name and not name.startswith(".") and not name.endswith((" ", "."))
    assert Path(name).name == name


@settings(max_examples=300, deadline=None)
@given(st.text(max_size=60))
def test_fts_query_never_breaks_sqlite(query):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
    conn.execute("INSERT INTO t VALUES ('hello corvus world')")
    fts = _fts_query(query)
    if fts:
        conn.execute("SELECT * FROM t WHERE t MATCH ?", (fts,)).fetchall()  # must not raise
    conn.close()


@settings(max_examples=300, deadline=None)
@given(path_text)
def test_plugin_zip_path_check_rejects_escapes(name):
    """Mirror of PluginManager.install_zip's per-entry check: anything that
    passes it must stay inside the staging directory."""
    p = PurePosixPath(name.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or any(":" in s or "\x00" in s for s in p.parts):
        return  # rejected by install_zip
    staging = Path("C:/staging").resolve()
    target = (staging / Path(*p.parts)).resolve() if p.parts else staging
    assert target == staging or staging in target.parents

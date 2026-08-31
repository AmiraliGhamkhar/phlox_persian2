"""
Tests for the sqlite-vec backend: per-collection vector isolation (including
non-Latin collection names), chunk-id uniqueness across collections, rename,
re-commit upsert, and the legacy schema migration.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from server.rag.backends.sqlite_vec import (
    ChunkData,
    SqliteVecBackend,
    _legacy_table_name,
    _safe_table_name,
)


def _make_chunk(doc_id: int, collection: str, idx: int, text: str, filename: str, emb):
    return ChunkData(
        id=f"{doc_id}:{idx}",
        collection_name=collection,
        source_document_id=doc_id,
        chunk_index=idx,
        text=text,
        disease_name=collection,
        focus_area="x",
        source="s",
        filename=filename,
        embedding=list(emb),
    )


@pytest.fixture()
def backend():
    with tempfile.TemporaryDirectory() as tmp:
        yield SqliteVecBackend(str(Path(tmp) / "vectors.sqlite"))


def test_persian_collection_names_get_distinct_tables():
    """Regression: every non-ASCII name used to sanitize to the same vec_ table."""
    assert _safe_table_name("ملاونوم") != _safe_table_name("سلولیت")
    # Deterministic (create/search must agree) and distinct from ASCII names.
    assert _safe_table_name("ملاونوم") == _safe_table_name("ملاونوم")
    assert _safe_table_name("melanoma") != _safe_table_name("ملاونوم")
    # Legacy naming collapsed all Persian names — must no longer be used.
    assert _legacy_table_name("ملاونوم") == _legacy_table_name("سلولیت")


def test_search_isolated_across_persian_collections(backend):
    backend.create_collection("ملاونوم", "m", 4)
    backend.create_collection("سلولیت", "m", 4)
    d1 = backend.store_source_document("ملاونوم", "a.pdf", "MELANOMA", None)
    backend.insert_chunks([_make_chunk(d1, "ملاونوم", 0, "MELANOMA", "a.pdf", [1.0, 0, 0, 0])])
    d2 = backend.store_source_document("سلولیت", "b.pdf", "CELLULITIS", None)
    backend.insert_chunks([_make_chunk(d2, "سلولیت", 0, "CELLULITIS", "b.pdf", [0, 1.0, 0, 0])])

    results = backend.search("ملاونوم", [1.0, 0, 0, 0], n_results=5)
    assert [r.metadata["disease_name"] for r in results] == ["ملاونوم"]


def test_same_filename_in_two_collections(backend):
    """Regression: '{filename}_{idx}' chunk ids collided in the global PK."""
    backend.create_collection("disease_a", "m", 2)
    backend.create_collection("disease_b", "m", 2)
    da = backend.store_source_document("disease_a", "notes.pdf", "A", None)
    backend.insert_chunks([_make_chunk(da, "disease_a", 0, "A", "notes.pdf", [1.0, 0.0])])
    db_ = backend.store_source_document("disease_b", "notes.pdf", "B", None)
    # Must not raise a UNIQUE constraint violation.
    backend.insert_chunks([_make_chunk(db_, "disease_b", 0, "B", "notes.pdf", [0.0, 1.0])])

    assert backend.get_files_for_collection("disease_a") == ["notes.pdf"]
    assert backend.get_files_for_collection("disease_b") == ["notes.pdf"]
    assert [r.text for r in backend.search("disease_b", [0.0, 1.0], 5)] == ["B"]


def test_reject_mixed_collection_batch(backend):
    backend.create_collection("a", "m", 2)
    backend.create_collection("b", "m", 2)
    with pytest.raises(ValueError):
        backend.insert_chunks(
            [
                _make_chunk(1, "a", 0, "A", "a.pdf", [1.0, 0.0]),
                _make_chunk(2, "b", 0, "B", "b.pdf", [0.0, 1.0]),
            ]
        )


def test_rename_ascii_collection_preserves_data(backend):
    """Regression: FKs without ON UPDATE CASCADE made every rename fail."""
    backend.create_collection("oldname", "m", 2)
    d = backend.store_source_document("oldname", "f.pdf", "content", None)
    backend.insert_chunks([_make_chunk(d, "oldname", 0, "content", "f.pdf", [1.0, 0.0])])

    assert backend.rename_collection("oldname", "newname", display_name="New Name")
    results = backend.search("newname", [1.0, 0.0], 5)
    assert len(results) == 1
    assert results[0].metadata["disease_name"] == "New Name"
    assert backend.get_files_for_collection("newname") == ["f.pdf"]
    assert backend.get_files_for_collection("oldname") == []


def test_rename_persian_collection_preserves_data(backend):
    backend.create_collection("ملاونوم", "m", 2)
    d = backend.store_source_document("ملاونوم", "g.pdf", "c", None)
    backend.insert_chunks([_make_chunk(d, "ملاونوم", 0, "c", "g.pdf", [1.0, 0.0])])

    assert backend.rename_collection("ملاونوم", "سلولیت", display_name="سلولیت")
    results = backend.search("سلولیت", [1.0, 0.0], 5)
    assert [r.metadata["disease_name"] for r in results] == ["سلولیت"]


def test_delete_one_persian_collection_keeps_the_other(backend):
    """Regression: shared vec_ table meant deleting one collection destroyed
    the vector rows of every other Persian collection."""
    backend.create_collection("ملاونوم", "m", 2)
    backend.create_collection("سلولیت", "m", 2)
    d1 = backend.store_source_document("ملاونوم", "a.pdf", "MEL", None)
    backend.insert_chunks([_make_chunk(d1, "ملاونوم", 0, "MEL", "a.pdf", [1.0, 0.0])])
    d2 = backend.store_source_document("سلولیت", "b.pdf", "CEL", None)
    backend.insert_chunks([_make_chunk(d2, "سلولیت", 0, "CEL", "b.pdf", [0.0, 1.0])])

    backend.delete_collection("ملاونوم")

    results = backend.search("سلولیت", [0.0, 1.0], 5)
    assert [r.text for r in results] == ["CEL"]
    assert backend.list_collections() == ["سلولیت"]


def test_delete_file_updates_vec_rows_and_allows_recommit(backend):
    backend.create_collection("col", "m", 2)
    d1 = backend.store_source_document("col", "f.pdf", "OLD", None)
    backend.insert_chunks([_make_chunk(d1, "col", 0, "OLD", "f.pdf", [1.0, 0.0])])

    assert backend.delete_file_from_collection("col", "f.pdf")
    # Re-commit the same filename: no UNIQUE violation, fresh content wins.
    d2 = backend.store_source_document("col", "f.pdf", "NEW", None)
    backend.insert_chunks([_make_chunk(d2, "col", 0, "NEW", "f.pdf", [0.0, 1.0])])

    assert [r.text for r in backend.search("col", [0.0, 1.0], 5)] == ["NEW"]
    assert backend.get_files_for_collection("col") == ["f.pdf"]


def _build_legacy_db(path: Path) -> None:
    """Build a pre-fix database: shared vec_ for Persian names, old ids."""
    import sqlite_vec

    db = sqlite3.connect(path)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.executescript(
        """
        CREATE TABLE collections (
            name TEXT PRIMARY KEY, embedding_model TEXT NOT NULL,
            embedding_dim INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, display_name TEXT
        );
        CREATE TABLE source_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_name TEXT NOT NULL REFERENCES collections(name) ON DELETE CASCADE,
            filename TEXT NOT NULL, full_text TEXT NOT NULL, pdf_blob BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, title TEXT,
            UNIQUE(collection_name, filename)
        );
        CREATE TABLE chunks (
            id TEXT PRIMARY KEY,
            collection_name TEXT NOT NULL REFERENCES collections(name) ON DELETE CASCADE,
            source_document_id INTEGER NOT NULL
                REFERENCES source_documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL, text TEXT NOT NULL,
            disease_name TEXT, focus_area TEXT, source TEXT, filename TEXT
        );
        """
    )
    db.execute(
        "INSERT INTO collections (name, embedding_model, embedding_dim, display_name) "
        "VALUES ('ملاونوم','m',4,'ملاونوم')"
    )
    db.execute(
        "INSERT INTO collections (name, embedding_model, embedding_dim, display_name) "
        "VALUES ('سلولیت','m',4,'سلولیت')"
    )
    db.execute(
        "CREATE VIRTUAL TABLE vec_ USING vec0("
        "chunk_id TEXT PRIMARY KEY, embedding float[4] distance_metric=cosine)"
    )

    def add(col, fn, text, emb):
        cur = db.execute(
            "INSERT INTO source_documents (collection_name, filename, full_text) VALUES (?,?,?)",
            (col, fn, text),
        )
        doc_id = cur.lastrowid
        db.execute(
            "INSERT INTO chunks (id, collection_name, source_document_id, chunk_index, "
            "text, disease_name, focus_area, source, filename) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (f"{fn}_0", col, doc_id, 0, text, col, "x", "s", fn),
        )
        db.execute(
            "INSERT INTO vec_ (chunk_id, embedding) VALUES (?,?)",
            (f"{fn}_0", sqlite_vec.serialize_float32(emb)),
        )

    add("ملاونوم", "mel.pdf", "MELANOMA", [1.0, 0, 0, 0])
    add("سلولیت", "cel.pdf", "CELLULITIS", [0, 1.0, 0, 0])
    db.commit()
    db.close()


def test_legacy_schema_migration_rebuilds_tables_and_ids():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "legacy.sqlite"
        _build_legacy_db(db_path)

        # Opening with the new backend runs the one-time migration.
        be = SqliteVecBackend(str(db_path))

        db = sqlite3.connect(db_path)
        try:
            # Old shared vec_ table is gone; hash-named tables exist.
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert "vec_" not in tables
            assert _safe_table_name("ملاونوم") in tables
            assert _safe_table_name("سلولیت") in tables
            # Chunk ids were re-keyed to "{source_doc_id}:{chunk_index}".
            ids = {r[0] for r in db.execute("SELECT id FROM chunks")}
            assert ids == {"1:0", "2:0"}
            # Migration flag is set (idempotency).
            assert db.execute(
                "SELECT value FROM schema_flags WHERE key='vector_migration_v2'"
            ).fetchone() == ("1",)
        finally:
            db.close()

        # Search still works and stays isolated after migration.
        assert [r.text for r in be.search("ملاونوم", [1.0, 0, 0, 0], 5)] == ["MELANOMA"]
        assert [r.text for r in be.search("سلولیت", [0, 1.0, 0, 0], 5)] == ["CELLULITIS"]

        # Re-opening must not double-migrate or corrupt data.
        be2 = SqliteVecBackend(str(db_path))
        assert [r.text for r in be2.search("ملاونوم", [1.0, 0, 0, 0], 5)] == ["MELANOMA"]

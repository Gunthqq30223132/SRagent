"""Unit tests for tools.fulltext_fetch (D38 Full-Text Acquisition Ladder).

Verifies 4-rung ladder behavior, EuropePMC XML parsing, warehouse lookup (read_doc.py),
inbox PDF extraction, fail-closed handling, idempotency, and TTL preservation.
"""

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import httpx
import pytest
import respx

from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from tools.fulltext_fetch import (
    fetch_fulltext_batch,
    fetch_arxiv_fulltext_batch,
    parse_jats_xml_body,
    MIN_FULLTEXT_LENGTH,
)
from tools.warehouse.read_doc import get_document_text


@pytest.fixture
def temp_db():
    temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
    db_path = Path(temp_path)
    yield db_path
    os.close(temp_fd)
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def temp_warehouse_db():
    temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
    db_path = Path(temp_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute("""
    CREATE TABLE chunks (
        chunk_id TEXT PRIMARY KEY,
        file_path TEXT NOT NULL,
        specialty TEXT NOT NULL,
        page INTEGER NOT NULL,
        char_span TEXT NOT NULL,
        text TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        authority_tier TEXT NOT NULL
    );
    """)
    conn.commit()
    conn.close()

    yield db_path
    os.close(temp_fd)
    if db_path.exists():
        db_path.unlink()


def create_dummy_doc(
    uid: str,
    source: str = "arxiv",
    full_text: str | None = None,
    status: str = "queued",
    is_open_access: bool = False,
    title: str | None = None,
) -> Document:
    source_id = uid.split(":", 1)[1] if ":" in uid else uid
    if source in ("arxiv", "europepmc"):
        source_id = uid
    doc_title = title or f"Test Document {uid}"
    doc_data = {
        "uid": uid,
        "source": source,
        "source_id": source_id,
        "authority_tier": 1,
        "title": doc_title,
        "abstract": "Abstract text for test document.",
        "full_text": full_text,
        "status": status,
        "is_open_access": is_open_access,
        "fetched_at": "2026-07-19T12:00:00Z",
    }
    return Document.model_validate(doc_data)


def test_select_right_doc(temp_db):
    """Test that only queued docs with SCREEN_INCLUDED and missing full_text are selected."""
    with StagingStore(temp_db) as store:
        doc1 = create_dummy_doc("arxiv:2412.00001")
        store.upsert(doc1)
        store.log_event(doc1.uid, "SCREEN_INCLUDED", "passed screening")

        doc2 = create_dummy_doc("arxiv:2412.00002")
        store.upsert(doc2)

        doc3 = create_dummy_doc("arxiv:2412.00003", full_text="A" * 3000)
        store.upsert(doc3)
        store.log_event(doc3.uid, "SCREEN_INCLUDED", "passed screening")

        doc5 = create_dummy_doc("arxiv:2412.00005", status="rejected")
        store.upsert(doc5)
        store.log_event(doc5.uid, "SCREEN_INCLUDED", "passed screening")

        with respx.mock(base_url="https://arxiv.org") as respx_mock:
            route = respx_mock.get("/pdf/2412.00001.pdf").respond(200, content=b"%PDF-fake-content")
            with patch("tools.fulltext_fetch.extract_text_from_pdf", return_value="Sample Text " * 200):
                count = fetch_fulltext_batch(store, limit=10, rungs=[1])

                assert count == 1
                assert route.called
                doc1_updated = store.get("arxiv:2412.00001")
                assert doc1_updated is not None
                assert doc1_updated.full_text is not None
                assert len(doc1_updated.full_text) >= MIN_FULLTEXT_LENGTH

                events_doc1 = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (doc1.uid,)).fetchall()]
                assert "FULLTEXT_FETCHED" in events_doc1


def test_fetch_fail(temp_db):
    """Test that HTTP 404/500 errors log FULLTEXT_FETCH_FAILED without crashing the batch."""
    with StagingStore(temp_db) as store:
        doc1 = create_dummy_doc("arxiv:2412.10001")
        doc2 = create_dummy_doc("arxiv:2412.10002")
        store.upsert(doc1)
        store.upsert(doc2)
        store.log_event(doc1.uid, "SCREEN_INCLUDED", "passed screening")
        store.log_event(doc2.uid, "SCREEN_INCLUDED", "passed screening")

        with respx.mock(base_url="https://arxiv.org") as respx_mock:
            respx_mock.get("/pdf/2412.10001.pdf").respond(404, text="Not Found")
            respx_mock.get("/pdf/2412.10002.pdf").respond(500, text="Server Error")

            count = fetch_fulltext_batch(store, limit=10, rungs=[1])

            assert count == 2
            events_doc1 = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (doc1.uid,)).fetchall()]
            events_doc2 = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (doc2.uid,)).fetchall()]
            assert "FULLTEXT_FETCH_FAILED" in events_doc1
            assert "FULLTEXT_FETCH_FAILED" in events_doc2
            assert store.get("arxiv:2412.10001").full_text is None
            assert store.get("arxiv:2412.10002").full_text is None


def test_text_too_short(temp_db):
    """Test that text extracted < 2000 chars logs FULLTEXT_TOO_SHORT and is not saved."""
    with StagingStore(temp_db) as store:
        doc = create_dummy_doc("arxiv:2412.20001")
        store.upsert(doc)
        store.log_event(doc.uid, "SCREEN_INCLUDED", "passed screening")

        with respx.mock(base_url="https://arxiv.org") as respx_mock:
            respx_mock.get("/pdf/2412.20001.pdf").respond(200, content=b"%PDF-short")
            with patch("tools.fulltext_fetch.extract_text_from_pdf", return_value="Short text less than 2000 chars"):
                count = fetch_fulltext_batch(store, limit=10, rungs=[1])

                assert count == 1
                events = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (doc.uid,)).fetchall()]
                assert "FULLTEXT_TOO_SHORT" in events
                assert "FULLTEXT_FETCHED" not in events
                doc_after = store.get("arxiv:2412.20001")
                assert doc_after.full_text is None


def test_success(temp_db):
    """Test successful full-text download and extraction (>= 2000 chars)."""
    with StagingStore(temp_db) as store:
        doc = create_dummy_doc("arxiv:2412.30001")
        store.upsert(doc)
        store.log_event(doc.uid, "SCREEN_INCLUDED", "passed screening")

        extracted_text = "Detailed Academic Text Content. " * 100
        with respx.mock(base_url="https://arxiv.org") as respx_mock:
            respx_mock.get("/pdf/2412.30001.pdf").respond(200, content=b"%PDF-full-content")
            with patch("tools.fulltext_fetch.extract_text_from_pdf", return_value=extracted_text):
                count = fetch_fulltext_batch(store, limit=10, rungs=[1])

                assert count == 1
                events = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (doc.uid,)).fetchall()]
                assert "FULLTEXT_FETCHED" in events
                doc_after = store.get("arxiv:2412.30001")
                assert doc_after.full_text == extracted_text
                assert len(doc_after.full_text) >= 2000


def test_idempotency(temp_db):
    """Test that running fetch_fulltext_batch twice does not re-fetch already fetched docs."""
    with StagingStore(temp_db) as store:
        doc = create_dummy_doc("arxiv:2412.40001")
        store.upsert(doc)
        store.log_event(doc.uid, "SCREEN_INCLUDED", "passed screening")

        extracted_text = "Full text content here. " * 150
        with respx.mock(base_url="https://arxiv.org") as respx_mock:
            route = respx_mock.get("/pdf/2412.40001.pdf").respond(200, content=b"%PDF-content")
            with patch("tools.fulltext_fetch.extract_text_from_pdf", return_value=extracted_text):
                count1 = fetch_fulltext_batch(store, limit=10, rungs=[1])
                assert count1 == 1
                assert route.call_count == 1

                count2 = fetch_fulltext_batch(store, limit=10, rungs=[1])
                assert count2 == 0
                assert route.call_count == 1

                events = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (doc.uid,)).fetchall()]
                assert events.count("FULLTEXT_FETCHED") == 1
                assert store.get("arxiv:2412.40001").full_text == extracted_text


def test_ttl_clock_not_reset_on_fetch(temp_db):
    """D38 §4(g): fetch full_text KHÔNG được reset đồng hồ TTL triage (touch=False)."""
    with StagingStore(temp_db) as store:
        doc = create_dummy_doc("arxiv:2412.50001")
        store.upsert(doc)
        store.log_event(doc.uid, "SCREEN_INCLUDED", "passed screening")

        old_ts = "2026-01-01T00:00:00+00:00"
        store.conn.execute(
            "UPDATE documents SET last_interaction_at = ? WHERE uid = ?",
            (old_ts, doc.uid),
        )
        store.conn.commit()

        with respx.mock(base_url="https://arxiv.org") as respx_mock:
            respx_mock.get("/pdf/2412.50001.pdf").respond(200, content=b"%PDF-x")
            with patch("tools.fulltext_fetch.extract_text_from_pdf", return_value="Long text. " * 300):
                fetch_fulltext_batch(store, limit=10, rungs=[1])

        row = store.conn.execute(
            "SELECT last_interaction_at FROM documents WHERE uid = ?", (doc.uid,)
        ).fetchone()
        assert row["last_interaction_at"] == old_ts
        assert store.get(doc.uid).full_text is not None


def test_extractor_raises_is_fail_closed(temp_db):
    """extract raise ⇒ FULLTEXT_FETCH_FAILED, KHÔNG ghi full_text."""
    with StagingStore(temp_db) as store:
        doc1 = create_dummy_doc("arxiv:2412.60001")
        doc2 = create_dummy_doc("arxiv:2412.60002")
        for d in (doc1, doc2):
            store.upsert(d)
            store.log_event(d.uid, "SCREEN_INCLUDED", "passed screening")

        with respx.mock(base_url="https://arxiv.org") as respx_mock:
            respx_mock.get("/pdf/2412.60001.pdf").respond(200, content=b"%PDF-a")
            respx_mock.get("/pdf/2412.60002.pdf").respond(200, content=b"%PDF-b")
            with patch(
                "tools.fulltext_fetch.extract_text_from_pdf",
                side_effect=[RuntimeError("pdftotext not found"), "Good text. " * 300],
            ):
                count = fetch_fulltext_batch(store, limit=10, rungs=[1])

        assert count == 2
        events1 = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (doc1.uid,)).fetchall()]
        assert "FULLTEXT_FETCH_FAILED" in events1
        assert "FULLTEXT_FETCHED" not in events1
        assert store.get(doc1.uid).full_text is None
        assert store.get(doc2.uid).full_text is not None


def test_provenance_detail_frozen_format(temp_db):
    """D38 §0.3: detail của FULLTEXT_FETCHED phải theo hợp đồng đóng băng."""
    with StagingStore(temp_db) as store:
        doc = create_dummy_doc("arxiv:2412.70001")
        store.upsert(doc)
        store.log_event(doc.uid, "SCREEN_INCLUDED", "passed screening")

        text = "Frozen contract text. " * 150
        with respx.mock(base_url="https://arxiv.org") as respx_mock:
            respx_mock.get("/pdf/2412.70001.pdf").respond(200, content=b"%PDF-c")
            with patch("tools.fulltext_fetch.extract_text_from_pdf", return_value=text):
                fetch_fulltext_batch(store, limit=10, rungs=[1])

        row = store.conn.execute(
            "SELECT detail FROM events WHERE uid = ? AND event_type = 'FULLTEXT_FETCHED'",
            (doc.uid,),
        ).fetchone()
        assert row is not None
        assert row["detail"] == f"rung=1 source=arxiv_pdf chars={len(text.strip())}"


# --- New D38 Ladder Rung Tests (§4 a-d) ---------------------------------------------


def test_ladder_stops_at_first_successful_rung(temp_db):
    """D38 §4(a): Rung 1 fails (non-arxiv doc), Rung 2 (EuropePMC XML) succeeds and stops ladder."""
    with StagingStore(temp_db) as store:
        doc = create_dummy_doc(
            "europepmc:MED:38111222",
            source="europepmc",
            is_open_access=True,
        )
        store.upsert(doc)
        store.log_event(doc.uid, "SCREEN_INCLUDED", "passed screening")

        xml_body = """<article><body><p>""" + ("Europe PMC Full Text Content Body. " * 100) + """</p></body><back><ref-list><ref>Ref 1</ref></ref-list></back></article>"""

        with respx.mock(base_url="https://www.ebi.ac.uk") as respx_mock:
            route = respx_mock.get("/europepmc/webservices/rest/MED/38111222/fullTextXML").respond(
                200, text=xml_body
            )
            count = fetch_fulltext_batch(store, limit=10, rungs=[1, 2, 3, 4])

            assert count == 1
            assert route.called
            doc_after = store.get(doc.uid)
            assert doc_after.full_text is not None
            assert len(doc_after.full_text) >= 2000
            assert "Europe PMC Full Text Content" in doc_after.full_text
            assert "Ref 1" not in doc_after.full_text

            events = store.conn.execute(
                "SELECT event_type, detail FROM events WHERE uid = ?", (doc.uid,)
            ).fetchall()
            event_types = [e["event_type"] for e in events]
            assert "FULLTEXT_FETCHED" in event_types
            fetched_detail = [e["detail"] for e in events if e["event_type"] == "FULLTEXT_FETCHED"][0]
            assert fetched_detail.startswith("rung=2 source=europepmc_xml chars=")


def test_ladder_all_rungs_fail(temp_db, temp_warehouse_db):
    """D38 §4(b): When all active rungs fail, full_text is NOT written, events logged."""
    with StagingStore(temp_db) as store:
        doc = create_dummy_doc("europepmc:MED:99999999", source="europepmc", is_open_access=True)
        store.upsert(doc)
        store.log_event(doc.uid, "SCREEN_INCLUDED", "passed screening")

        with tempfile.TemporaryDirectory() as empty_inbox:
            with respx.mock(base_url="https://www.ebi.ac.uk") as respx_mock:
                respx_mock.get("/europepmc/webservices/rest/MED/99999999/fullTextXML").respond(404, text="Not found")

                count = fetch_fulltext_batch(
                    store,
                    limit=10,
                    rungs=[1, 2, 3, 4],
                    warehouse_db_path=temp_warehouse_db,
                    inbox_dir=Path(empty_inbox),
                )

                assert count == 1
                doc_after = store.get(doc.uid)
                assert doc_after.full_text is None

                events = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (doc.uid,)).fetchall()]
                assert "FULLTEXT_FETCHED" not in events
                assert events.count("FULLTEXT_FETCH_FAILED") >= 2


def test_warehouse_rung3_single_match(temp_warehouse_db):
    """D38 §4(c): Rung 3 matches 1 warehouse doc and returns chunks in page, rowid order."""
    conn = sqlite3.connect(str(temp_warehouse_db))
    conn.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("c1", "/warehouse/Test Paper.pdf", "Anesthesia", 1, "0-100", "Chunk 1 content. " * 100, "hash1", "T1")
    )
    conn.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("c2", "/warehouse/Test Paper.pdf", "Anesthesia", 2, "0-100", "Chunk 2 content. " * 100, "hash2", "T1")
    )
    conn.commit()
    conn.close()

    doc = create_dummy_doc("ieee:10002000", source="ieee", title="Test Paper")
    norm_title = doc.title_normalized

    text = get_document_text(norm_title, temp_warehouse_db)
    assert text is not None
    assert "Chunk 1 content" in text
    assert "Chunk 2 content" in text
    assert text.index("Chunk 1 content") < text.index("Chunk 2 content")


def test_warehouse_rung3_multiple_match_returns_none(temp_warehouse_db):
    """D38 §4(c): Rung 3 matching >1 warehouse doc returns None (ambiguity fail-closed)."""
    conn = sqlite3.connect(str(temp_warehouse_db))
    conn.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("c1", "/dir1/Same Paper.pdf", "Anesthesia", 1, "0-100", "Doc 1 text", "hash1", "T1")
    )
    conn.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("c2", "/dir2/Same Paper.pdf", "Anesthesia", 1, "0-100", "Doc 2 text", "hash2", "T1")
    )
    conn.commit()
    conn.close()

    doc = create_dummy_doc("ieee:10003000", source="ieee", title="Same Paper")
    text = get_document_text(doc.title_normalized, temp_warehouse_db)
    assert text is None


def test_inbox_rung4_matching_file(temp_db):
    """D38 §4(d): Rung 4 ingests matching inbox PDF file named uid.replace(':', '_') + '.pdf'."""
    with StagingStore(temp_db) as store:
        doc = create_dummy_doc("ieee:88887777", source="ieee")
        store.upsert(doc)
        store.log_event(doc.uid, "SCREEN_INCLUDED", "passed screening")

        with tempfile.TemporaryDirectory() as inbox_dir:
            inbox_path = Path(inbox_dir)
            matching_pdf = inbox_path / "ieee_88887777.pdf"
            matching_pdf.write_bytes(b"%PDF-inbox-content")

            unrelated_pdf = inbox_path / "other_file.pdf"
            unrelated_pdf.write_bytes(b"%PDF-other-content")

            extracted_text = "Inbox PDF extracted full text content. " * 100
            with patch("tools.fulltext_fetch.extract_text_from_pdf", return_value=extracted_text):
                count = fetch_fulltext_batch(
                    store,
                    limit=10,
                    rungs=[4],
                    inbox_dir=inbox_path,
                )

                assert count == 1
                doc_after = store.get(doc.uid)
                assert doc_after.full_text == extracted_text

                events = store.conn.execute(
                    "SELECT detail FROM events WHERE uid = ? AND event_type = 'FULLTEXT_FETCHED'",
                    (doc.uid,),
                ).fetchall()
                assert len(events) == 1
                assert events[0]["detail"].startswith("rung=4 source=inbox chars=")

"""Unit tests for tools.fulltext_fetch (arXiv Full-Text Acquisition).

Verifies document selection, offline fetching with respx mocks, PDF extraction handling,
fail-closed events, and idempotency.
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
from tools.fulltext_fetch import fetch_arxiv_fulltext_batch, MIN_FULLTEXT_LENGTH


@pytest.fixture
def temp_db():
    temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
    db_path = Path(temp_path)
    yield db_path
    os.close(temp_fd)
    if db_path.exists():
        db_path.unlink()


def create_dummy_doc(uid: str, source: str = "arxiv", full_text: str | None = None, status: str = "queued") -> Document:
    source_id = uid.split(":", 1)[1] if ":" in uid else uid
    if source == "arxiv":
        source_id = uid
    doc_data = {
        "uid": uid,
        "source": source,
        "source_id": source_id,
        "authority_tier": 1,
        "title": f"Test Document {uid}",
        "title_normalized": f"test document {uid}",
        "abstract": "Abstract text for test document.",
        "full_text": full_text,
        "status": status,
        "fetched_at": "2026-07-19T12:00:00Z",
    }
    return Document.model_validate(doc_data)


def test_select_right_doc(temp_db):
    """Test that only queued arXiv docs with SCREEN_INCLUDED and missing full_text are selected."""
    with StagingStore(temp_db) as store:
        # Doc 1: Target - queued, arxiv, SCREEN_INCLUDED, no full_text
        doc1 = create_dummy_doc("arxiv:2412.00001")
        store.upsert(doc1)
        store.log_event(doc1.uid, "SCREEN_INCLUDED", "passed screening")

        # Doc 2: Missing SCREEN_INCLUDED
        doc2 = create_dummy_doc("arxiv:2412.00002")
        store.upsert(doc2)

        # Doc 3: Already has full_text
        doc3 = create_dummy_doc("arxiv:2412.00003", full_text="A" * 3000)
        store.upsert(doc3)
        store.log_event(doc3.uid, "SCREEN_INCLUDED", "passed screening")

        # Doc 4: Non-arxiv source
        doc4 = create_dummy_doc("ieee:99999999", source="ieee")
        store.upsert(doc4)
        store.log_event(doc4.uid, "SCREEN_INCLUDED", "passed screening")

        # Doc 5: Rejected status
        doc5 = create_dummy_doc("arxiv:2412.00005", status="rejected")
        store.upsert(doc5)
        store.log_event(doc5.uid, "SCREEN_INCLUDED", "passed screening")

        with respx.mock(base_url="https://arxiv.org") as respx_mock:
            route = respx_mock.get("/pdf/2412.00001.pdf").respond(200, content=b"%PDF-fake-content")
            with patch("tools.fulltext_fetch.extract_text_from_pdf", return_value="Sample Text " * 200):
                count = fetch_arxiv_fulltext_batch(store, limit=10)

                assert count == 1
                assert route.called
                doc1_updated = store.get("arxiv:2412.00001")
                assert doc1_updated is not None
                assert doc1_updated.full_text is not None
                assert len(doc1_updated.full_text) >= MIN_FULLTEXT_LENGTH

                events_doc1 = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (doc1.uid,)).fetchall()]
                assert "FULLTEXT_FETCHED" in events_doc1


def test_fetch_fail(temp_db):
    """Test that HTTP 404/500 or network errors log FULLTEXT_FETCH_FAILED without crashing the batch."""
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

            count = fetch_arxiv_fulltext_batch(store, limit=10)

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
                count = fetch_arxiv_fulltext_batch(store, limit=10)

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

        extracted_text = "Detailed Academic Text Content. " * 100  # > 2000 chars
        with respx.mock(base_url="https://arxiv.org") as respx_mock:
            respx_mock.get("/pdf/2412.30001.pdf").respond(200, content=b"%PDF-full-content")
            with patch("tools.fulltext_fetch.extract_text_from_pdf", return_value=extracted_text):
                count = fetch_arxiv_fulltext_batch(store, limit=10)

                assert count == 1
                events = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (doc.uid,)).fetchall()]
                assert "FULLTEXT_FETCHED" in events
                doc_after = store.get("arxiv:2412.30001")
                assert doc_after.full_text == extracted_text
                assert len(doc_after.full_text) >= 2000


def test_idempotency(temp_db):
    """Test that running fetch_arxiv_fulltext_batch twice does not re-fetch already fetched docs."""
    with StagingStore(temp_db) as store:
        doc = create_dummy_doc("arxiv:2412.40001")
        store.upsert(doc)
        store.log_event(doc.uid, "SCREEN_INCLUDED", "passed screening")

        extracted_text = "Full text content here. " * 150
        with respx.mock(base_url="https://arxiv.org") as respx_mock:
            route = respx_mock.get("/pdf/2412.40001.pdf").respond(200, content=b"%PDF-content")
            with patch("tools.fulltext_fetch.extract_text_from_pdf", return_value=extracted_text):
                count1 = fetch_arxiv_fulltext_batch(store, limit=10)
                assert count1 == 1
                assert route.call_count == 1

                # Second run: doc now has full_text, so it should be skipped
                count2 = fetch_arxiv_fulltext_batch(store, limit=10)
                assert count2 == 0
                assert route.call_count == 1  # Route not called again

                events = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (doc.uid,)).fetchall()]
                assert events.count("FULLTEXT_FETCHED") == 1
                assert store.get("arxiv:2412.40001").full_text == extracted_text


# --- Test đối kháng của PM (luật Oracle — pm-succession.md §3 bước 6) -----------------


def test_ttl_clock_not_reset_on_fetch(temp_db):
    """D38 §4(g): fetch full_text KHÔNG được reset đồng hồ TTL triage (touch=False).

    Nếu vi phạm, mọi doc SR được fetch sẽ trẻ hóa last_interaction_at và
    lách cơ chế purge — đúng họ bug TTL đã trả học phí ở PR #23.
    """
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
                fetch_arxiv_fulltext_batch(store, limit=10)

        row = store.conn.execute(
            "SELECT last_interaction_at FROM documents WHERE uid = ?", (doc.uid,)
        ).fetchone()
        assert row["last_interaction_at"] == old_ts
        assert store.get(doc.uid).full_text is not None


def test_extractor_raises_is_fail_closed(temp_db):
    """pdftotext/mutool vắng mặt (ca MISSING EXTRACTOR có thật trong run FL-2):
    extract raise ⇒ FULLTEXT_FETCH_FAILED, KHÔNG ghi full_text, batch vẫn đi tiếp doc sau."""
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
                count = fetch_arxiv_fulltext_batch(store, limit=10)

        assert count == 2
        events1 = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (doc1.uid,)).fetchall()]
        assert "FULLTEXT_FETCH_FAILED" in events1
        assert "FULLTEXT_FETCHED" not in events1
        assert store.get(doc1.uid).full_text is None
        assert store.get(doc2.uid).full_text is not None


def test_provenance_detail_frozen_format(temp_db):
    """D38 §0.3: detail của FULLTEXT_FETCHED phải theo hợp đồng đóng băng
    `rung=<n> source=<...> chars=<len>` — bậc 2-4 và console D37 sẽ đọc format này."""
    with StagingStore(temp_db) as store:
        doc = create_dummy_doc("arxiv:2412.70001")
        store.upsert(doc)
        store.log_event(doc.uid, "SCREEN_INCLUDED", "passed screening")

        text = "Frozen contract text. " * 150
        with respx.mock(base_url="https://arxiv.org") as respx_mock:
            respx_mock.get("/pdf/2412.70001.pdf").respond(200, content=b"%PDF-c")
            with patch("tools.fulltext_fetch.extract_text_from_pdf", return_value=text):
                fetch_arxiv_fulltext_batch(store, limit=10)

        row = store.conn.execute(
            "SELECT detail FROM events WHERE uid = ? AND event_type = 'FULLTEXT_FETCHED'",
            (doc.uid,),
        ).fetchone()
        assert row is not None
        assert row["detail"] == f"rung=1 source=arxiv_pdf chars={len(text.strip())}"

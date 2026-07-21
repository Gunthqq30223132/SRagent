"""Tests for D36 - Run Scoping."""

import os
import json
import sqlite3
import hashlib
import pytest
from pathlib import Path
from datetime import datetime, timedelta, timezone

from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from tools.prisma_report import generate_prisma_report
from tools.sr_run import is_consensus_approved


def test_db_migration(tmp_path):
    """(a) migration DB cũ -> có cột, data nguyên."""
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            uid        TEXT NOT NULL,
            event_type TEXT NOT NULL,
            detail     TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
    """)
    conn.execute(
        "INSERT INTO events (uid, event_type, detail, created_at) "
        "VALUES ('doc1', 'FETCHED', 'test', '2026-07-20T00:00:00Z')"
    )
    conn.commit()
    conn.close()

    with StagingStore(db_path) as store:
        cursor = store.conn.execute("PRAGMA table_info(events)")
        cols = [r["name"] for r in cursor.fetchall()]
        assert "run_id" in cols

        rows = store.conn.execute("SELECT * FROM events").fetchall()
        assert len(rows) == 1
        assert rows[0]["uid"] == "doc1"
        assert rows[0]["event_type"] == "FETCHED"


def test_log_event_scoping(tmp_path):
    """(b) log_event stamp env đúng + tham số tường minh thắng env."""
    db_path = tmp_path / "test.db"
    with StagingStore(db_path) as store:
        store.log_event("doc1", "FETCHED")
        row = store.conn.execute("SELECT run_id FROM events WHERE uid='doc1'").fetchone()
        assert row["run_id"] is None

        os.environ["SR_RUN_ID"] = "run_env_123"
        try:
            store.log_event("doc2", "FETCHED")
            row2 = store.conn.execute("SELECT run_id FROM events WHERE uid='doc2'").fetchone()
            assert row2["run_id"] == "run_env_123"

            store.log_event("doc3", "FETCHED", run_id="run_explicit_456")
            row3 = store.conn.execute("SELECT run_id FROM events WHERE uid='doc3'").fetchone()
            assert row3["run_id"] == "run_explicit_456"
        finally:
            del os.environ["SR_RUN_ID"]


def test_parallel_runs_isolation(tmp_path):
    """(c) hai run song song không nhìn thấy event của nhau qua view membership."""
    db_path = tmp_path / "test.db"
    with StagingStore(db_path) as store:
        store.log_event("doc1", "SCREEN_INCLUDED", run_id="run_A")
        store.log_event("doc2", "SCREEN_INCLUDED", run_id="run_B")

        rows_A = store.conn.execute("SELECT DISTINCT uid FROM events WHERE run_id = 'run_A'").fetchall()
        uids_A = {r["uid"] for r in rows_A}
        assert "doc1" in uids_A
        assert "doc2" not in uids_A

        rows_B = store.conn.execute("SELECT DISTINCT uid FROM events WHERE run_id = 'run_B'").fetchall()
        uids_B = {r["uid"] for r in rows_B}
        assert "doc2" in uids_B
        assert "doc1" not in uids_B


def test_resume_mismatched_protocol_sha(tmp_path):
    """(d) resume sai protocol_sha256 -> rc=2."""
    db_path = tmp_path / "test.db"
    proto_a = tmp_path / "proto_a.json"
    proto_a.write_text(json.dumps({"topic_vi": "A"}))
    sha_a = hashlib.sha256(proto_a.read_bytes()).hexdigest()

    proto_b = tmp_path / "proto_b.json"
    proto_b.write_text(json.dumps({"topic_vi": "B"}))

    with StagingStore(db_path) as store:
        store.conn.execute(
            "INSERT INTO sr_runs (run_id, query, protocol_path, protocol_sha256, state, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("run_123", "query", str(proto_a), sha_a, "OPEN", "2026-07-20T00:00:00Z")
        )
        store.conn.commit()

    from tools.sr_run import main as sr_run_main
    rc = sr_run_main(["run", "--run", "run_123", "--protocol", str(proto_b), "--db", str(db_path)])
    assert rc == 2

    rc_missing = sr_run_main(
        ["run", "--run", "run_123", "--protocol", str(tmp_path / "nonexistent.json"), "--db", str(db_path)]
    )
    assert rc_missing == 2


def test_consensus_gate_per_run(tmp_path):
    """(e) approve run A không mở gate run B."""
    db_path = tmp_path / "test.db"
    with StagingStore(db_path) as store:
        store.log_event("any", "CONSENSUS_APPROVED", run_id="run_A")

        os.environ["SR_RUN_ID"] = "run_A"
        try:
            assert is_consensus_approved(store) is True
        finally:
            del os.environ["SR_RUN_ID"]

        os.environ["SR_RUN_ID"] = "run_B"
        try:
            assert is_consensus_approved(store) is False
        finally:
            del os.environ["SR_RUN_ID"]


def test_prisma_scoping(tmp_path):
    """(f) PRISMA --run đếm đúng."""
    db_path = tmp_path / "test.db"
    with StagingStore(db_path) as store:
        store.log_event("doc1", "FETCHED", run_id="run_A")
        store.log_event("doc1", "SCREEN_INCLUDED", run_id="run_A")
        store.log_event("doc1", "ELIG_INCLUDED", run_id="run_A")

        store.log_event("doc2", "FETCHED", run_id="run_B")

        report_A = generate_prisma_report(store, "run_A")
        assert "- **Records identified from databases**: 1" in report_A
        assert "- **Studies included in systematic review**: 1" in report_A
        assert "Run: run_A" in report_A

        report_B = generate_prisma_report(store, "run_B")
        assert "- **Records identified from databases**: 1" in report_B
        assert "- **Studies included in systematic review**: 0" in report_B
        assert "Run: run_B" in report_B

        report_global = generate_prisma_report(store)
        assert "legacy/all-history" in report_global


def test_wip_queue_scoping(tmp_path):
    """(g) WIP triage loại doc thuộc run OPEN."""
    db_path = tmp_path / "test.db"
    with StagingStore(db_path) as store:
        store.conn.execute(
            "INSERT INTO sr_runs (run_id, query, protocol_path, protocol_sha256, state, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("run_A", "q", "p", "s", "OPEN", "2026-07-20T00:00:00Z")
        )
        doc1 = Document(uid="arxiv:2401.12345", source="arxiv", source_id="arxiv:2401.12345", authority_tier=1, title="doc1", status=DocStatus.QUEUED)
        doc2 = Document(uid="arxiv:2401.54321", source="arxiv", source_id="arxiv:2401.54321", authority_tier=1, title="doc2", status=DocStatus.QUEUED)
        store.upsert(doc1)
        store.upsert(doc2)

        store.log_event("arxiv:2401.12345", "SCREEN_INCLUDED", run_id="run_A")

        queue = store.get_wip_queue()
        assert len(queue) == 1
        assert queue[0].uid == "arxiv:2401.54321"


def test_purge_expired_exempts_open_run(tmp_path):
    """(h) purge miễn trừ doc run OPEN."""
    db_path = tmp_path / "test.db"
    with StagingStore(db_path) as store:
        store.conn.execute(
            "INSERT INTO sr_runs (run_id, query, protocol_path, protocol_sha256, state, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("run_A", "q", "p", "s", "OPEN", "2026-07-20T00:00:00Z")
        )
        doc1 = Document(uid="arxiv:2401.12345", source="arxiv", source_id="arxiv:2401.12345", authority_tier=1, title="doc1", status=DocStatus.QUEUED)
        doc2 = Document(uid="arxiv:2401.54321", source="arxiv", source_id="arxiv:2401.54321", authority_tier=1, title="doc2", status=DocStatus.QUEUED)
        store.upsert(doc1)
        store.upsert(doc2)

        past_time = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
        store.conn.execute("UPDATE documents SET last_interaction_at = ?", (past_time,))
        store.conn.commit()

        store.log_event("arxiv:2401.12345", "SCREEN_INCLUDED", run_id="run_A")

        purged = store.purge_expired(ttl_hours=24)
        assert "arxiv:2401.54321" in purged
        assert "arxiv:2401.12345" not in purged
        assert store.exists("arxiv:2401.12345") is True
        assert store.exists("arxiv:2401.54321") is False


def test_abandoned_run_releases_exemption(tmp_path):
    """(i) ABANDONED thả miễn trừ."""
    db_path = tmp_path / "test.db"
    with StagingStore(db_path) as store:
        store.conn.execute(
            "INSERT INTO sr_runs (run_id, query, protocol_path, protocol_sha256, state, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("run_A", "q", "p", "s", "ABANDONED", "2026-07-20T00:00:00Z")
        )
        doc1 = Document(uid="arxiv:2401.12345", source="arxiv", source_id="arxiv:2401.12345", authority_tier=1, title="doc1", status=DocStatus.QUEUED)
        store.upsert(doc1)

        store.log_event("arxiv:2401.12345", "SCREEN_INCLUDED", run_id="run_A")

        queue = store.get_wip_queue()
        assert len(queue) == 1
        assert queue[0].uid == "arxiv:2401.12345"

        past_time = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
        store.conn.execute("UPDATE documents SET last_interaction_at = ?", (past_time,))
        store.conn.commit()

        purged = store.purge_expired(ttl_hours=24)
        assert "arxiv:2401.12345" in purged
        assert store.exists("arxiv:2401.12345") is False


# --- Test đối kháng của PM (luật Oracle — pm-succession.md §3 bước 6) -----------------


def test_legacy_null_run_events_not_excluded(tmp_path):
    """Doc di sản (event KHÔNG có run_id) tuyệt đối không bị loại oan khỏi triage/purge
    khi tồn tại run OPEN — nếu subquery xử NULL sai, toàn bộ hàng đợi duyệt biến mất."""
    db_path = tmp_path / "test.db"
    with StagingStore(db_path) as store:
        store.conn.execute(
            "INSERT INTO sr_runs (run_id, query, protocol_path, protocol_sha256, state, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("run_A", "q", "p", "s", "OPEN", "2026-07-20T00:00:00Z"),
        )
        legacy = Document(uid="arxiv:2401.00001", source="arxiv", source_id="arxiv:2401.00001",
                          authority_tier=1, title="legacy", status=DocStatus.QUEUED)
        store.upsert(legacy)
        # event di sản: không run_id (env cũng phải sạch)
        os.environ.pop("SR_RUN_ID", None)
        store.log_event(legacy.uid, "FETCHED", "legacy triage doc")

        queue = store.get_wip_queue()
        assert len(queue) == 1
        assert queue[0].uid == legacy.uid

        past_time = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
        store.conn.execute("UPDATE documents SET last_interaction_at = ?", (past_time,))
        store.conn.commit()
        purged = store.purge_expired(ttl_hours=24)
        assert legacy.uid in purged  # di sản vẫn theo vòng đời TTL bình thường


def test_closed_run_releases_exemption(tmp_path):
    """CLOSED (không chỉ ABANDONED) cũng thả miễn trừ — run chốt xong thì doc
    quay về vòng đời triage, không bất tử."""
    db_path = tmp_path / "test.db"
    with StagingStore(db_path) as store:
        store.conn.execute(
            "INSERT INTO sr_runs (run_id, query, protocol_path, protocol_sha256, state, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("run_C", "q", "p", "s", "CLOSED", "2026-07-20T00:00:00Z"),
        )
        doc = Document(uid="arxiv:2401.00002", source="arxiv", source_id="arxiv:2401.00002",
                       authority_tier=1, title="closed-run doc", status=DocStatus.QUEUED)
        store.upsert(doc)
        store.log_event(doc.uid, "SCREEN_INCLUDED", run_id="run_C")

        queue = store.get_wip_queue()
        assert len(queue) == 1
        assert queue[0].uid == doc.uid

from datetime import datetime, timedelta, timezone

from sr_agent.models.schemas import DocStatus, Document, RubricResult
from sr_agent.store.staging import StagingStore


def make_doc(pmid: str, score: float | None = None, status=DocStatus.QUEUED):
    return Document(
        uid="",
        source="ieee",
        source_id=pmid,
        authority_tier=1,
        title=f"Paper {pmid}",
        rubric=RubricResult(total=score, passed=score >= 60) if score is not None else None,
        status=status,
    )


def test_wal_and_busy_timeout_active(tmp_path):
    # File-based DB PHẢI ở WAL để ingest (ghi) và UI duyệt (đọc) đồng thời.
    with StagingStore(tmp_path / "t.db") as store:
        mode = store.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
        timeout = store.conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert timeout == 30000


def test_wal_survives_reopen(tmp_path):
    # journal_mode bền vững theo file: mở lại vẫn WAL.
    db = tmp_path / "t.db"
    with StagingStore(db):
        pass
    with StagingStore(db) as store2:
        mode = store2.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"


def test_concurrent_read_while_open_write_connection(tmp_path):
    # Dưới WAL, một reader thứ hai đọc được trong khi connection ghi còn mở.
    db = tmp_path / "t.db"
    with StagingStore(db) as writer:
        writer.upsert(make_doc("11111111", 80))
        with StagingStore(db) as reader:
            assert reader.exists("ieee:11111111")


def test_upsert_get_roundtrip(tmp_path):
    with StagingStore(tmp_path / "t.db") as store:
        doc = make_doc("11111111", 80)
        store.upsert(doc)
        got = store.get("ieee:11111111")
        assert got is not None
        assert got.rubric.total == 80
        assert store.exists("ieee:11111111")
        assert not store.exists("ieee:22222222")


def test_wip_queue_sorted_by_rubric_and_limited(tmp_path):
    with StagingStore(tmp_path / "t.db") as store:
        scores = [50, 90, 70, 60, 85, 95, 40]
        for i, s in enumerate(scores):
            store.upsert(make_doc(f"1000000{i}", s))
        # bản ghi không QUEUED không được vào hàng đợi
        store.upsert(make_doc("99999999", 99, status=DocStatus.FETCHED))

        queue = store.get_wip_queue(limit=5)
        got_scores = [d.rubric.total for d in queue]
        assert got_scores == [95, 90, 85, 70, 60]  # WIP_LIMIT=5, giảm dần


def test_ttl_purge_only_untouched_non_terminal(tmp_path):
    with StagingStore(tmp_path / "t.db") as store:
        store.upsert(make_doc("11111111", 80, status=DocStatus.QUEUED))
        store.upsert(make_doc("22222222", 80, status=DocStatus.APPROVED))
        store.upsert(make_doc("33333333", 80, status=DocStatus.REJECTED))

        # giả lập 73h trôi qua: lùi last_interaction_at của mọi bản ghi
        old = (datetime.now(timezone.utc) - timedelta(hours=73)).isoformat()
        store.conn.execute("UPDATE documents SET last_interaction_at = ?", (old,))
        store.conn.commit()

        purged = store.purge_expired(ttl_hours=72)
        assert purged == ["ieee:11111111"]  # APPROVED/REJECTED miễn purge
        assert not store.exists("ieee:11111111")
        assert store.exists("ieee:22222222")


def test_ttl_keeps_recent_records(tmp_path):
    with StagingStore(tmp_path / "t.db") as store:
        store.upsert(make_doc("11111111", 80))
        assert store.purge_expired(ttl_hours=72) == []


def test_dlq_isolation(tmp_path):
    with StagingStore(tmp_path / "t.db") as store:
        store.push_dlq("ieee:11111111", "RateLimited", "429", retry_eligible=True)
        store.push_dlq("arxiv:2401.00001", "LayoutParseError", "bad xml")
        assert len(store.dlq_entries()) == 2
        retryable = store.dlq_entries(retry_eligible_only=True)
        assert len(retryable) == 1 and retryable[0]["uid"] == "ieee:11111111"
        store.clear_dlq_entry(retryable[0]["id"])
        assert len(store.dlq_entries()) == 1

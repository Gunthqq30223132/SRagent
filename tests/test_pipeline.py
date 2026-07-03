from datetime import datetime, timedelta, timezone

import pytest

from sr_agent.errors import LayoutParseError, RateLimited
from sr_agent.ingest.router import SourceRouter
from sr_agent.models.schemas import DocStatus, Document
from sr_agent.pipeline import Pipeline
from sr_agent.store.staging import StagingStore


def make_doc(source, source_id, title, tier, *, rich=True):
    return Document(
        uid="", source=source, source_id=source_id, authority_tier=tier, title=title,
        abstract=(
            "We evaluate on benchmarks, code at https://github.com/x/y, dataset on "
            "huggingface.co/datasets. " + "More details of the experiments. " * 30
        ) if rich else None,
        authors=["A"] if rich else [],
        published_date=datetime.now(timezone.utc) - timedelta(days=30) if rich else None,
    )


class FakeFetcher:
    """Fetcher tất định cho test: trả docs dựng sẵn hoặc ném lỗi."""

    def __init__(self, source, docs=None, error=None):
        self.source = source
        self.docs = docs or []
        self.error = error

    def search(self, query, max_results=20):
        if self.error:
            raise self.error
        return [d.source_id for d in self.docs]

    def fetch(self, source_ids):
        if self.error:
            raise self.error
        return [d for d in self.docs if d.source_id in set(source_ids)]


@pytest.fixture
def store(tmp_path):
    with StagingStore(tmp_path / "t.db") as s:
        yield s


def build(store, fetchers, parser=None):
    return Pipeline(store, router=SourceRouter(fetchers=fetchers), parser=parser)


def test_happy_path_queues_passing_docs(store):
    ieee = make_doc("ieee", "38111222", "Paper One", 1)
    weak = make_doc("ieee", "37000111", "Paper Two", 1, rich=False)
    pipeline = build(store, {"ieee": FakeFetcher("ieee", [ieee, weak])})

    report = pipeline.run("q")
    assert report.fetched == 2 and report.queued == 1
    assert report.rejected_by_rubric == 1
    assert store.get("ieee:38111222").status is DocStatus.QUEUED
    assert store.get("ieee:37000111").status is DocStatus.REJECTED


def test_dedup_supersedes_across_sources(store):
    title = "Efficient Transformer Inference on Edge Devices"
    arxiv = make_doc("arxiv", "arxiv:2401.12345", title, 2)
    ieee = make_doc("ieee", "38111222", title + "!", 1)
    pipeline = build(store, {"arxiv": FakeFetcher("arxiv", [arxiv])})
    pipeline.run("q")

    pipeline2 = build(store, {"ieee": FakeFetcher("ieee", [ieee])})
    report = pipeline2.run("q")
    assert report.superseded == 1
    assert not store.exists("arxiv:2401.12345")  # bản preprint bị thay thế
    winner = store.get("ieee:38111222")
    assert winner.alternate_uids == ["arxiv:2401.12345"]  # nhưng giữ vết


def test_rate_limited_source_skipped_others_continue(store):
    ok_doc = make_doc("arxiv", "arxiv:2401.12345", "Fine Paper", 2)
    pipeline = build(store, {
        "ieee": FakeFetcher("ieee", error=RateLimited("429", retry_after=30)),
        "arxiv": FakeFetcher("arxiv", [ok_doc]),
    })
    report = pipeline.run("q")
    # nguồn 429 vào DLQ retry_eligible, nguồn còn lại vẫn chạy trọn
    assert report.skipped_sources == ["ieee"]
    assert report.queued == 1
    entries = store.dlq_entries(retry_eligible_only=True)
    assert len(entries) == 1 and entries[0]["uid"] == "ieee:batch"


def test_permanent_error_isolated_per_document(store, tmp_path, monkeypatch):
    monkeypatch.setattr("sr_agent.pipeline.QUARANTINE_DIR", tmp_path / "quarantine")
    bad = make_doc("ieee", "38111222", "Corrupt Layout", 1)
    good = make_doc("ieee", "37000111", "Good Paper", 1)

    def parser(doc):
        if doc.uid == "ieee:38111222":
            raise LayoutParseError("layout hỏng")
        return doc

    pipeline = build(store, {"ieee": FakeFetcher("ieee", [bad, good])}, parser=parser)
    report = pipeline.run("q")

    # bản lỗi cô lập: DLQ + quarantine + status DLQ; bản tốt vẫn QUEUED
    assert report.dlq == 1 and report.queued == 1
    assert store.get("ieee:38111222").status is DocStatus.DLQ
    assert store.get("ieee:37000111").status is DocStatus.QUEUED
    entry = store.dlq_entries()[0]
    assert entry["error_type"] == "LayoutParseError"
    assert (tmp_path / "quarantine" / "ieee_38111222.raw").exists()


def test_circuit_breaker_stops_source_after_consecutive_failures(store):
    docs = [make_doc("ieee", f"3811122{i}", f"Paper {i}", 1) for i in range(5)]

    def always_transient(doc):
        raise RateLimited("ollama quá tải")

    pipeline = build(store, {"ieee": FakeFetcher("ieee", docs)}, parser=always_transient)
    report = pipeline.run("q")
    # ngắt sau 3 lỗi liên tiếp (CIRCUIT_BREAKER_FAILURES), không xử lý nốt 2 bản còn lại
    assert report.dlq == 3
    assert report.skipped_sources == ["ieee"]
    assert all(e["retry_eligible"] == 1 for e in store.dlq_entries())


def test_ttl_purge_runs_at_batch_start(store):
    stale = make_doc("ieee", "38111222", "Old Paper", 1)
    stale.status = DocStatus.QUEUED
    store.upsert(stale)
    old = (datetime.now(timezone.utc) - timedelta(hours=73)).isoformat()
    store.conn.execute("UPDATE documents SET last_interaction_at = ?", (old,))
    store.conn.commit()

    pipeline = build(store, {"ieee": FakeFetcher("ieee", [])})
    report = pipeline.run("q")
    assert report.purged == ["ieee:38111222"]

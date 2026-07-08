"""Chạy thử SR-Agent end-to-end bằng bộ seed offline, qua ĐÚNG pipeline thật.

Dùng khi môi trường không truy cập được arXiv/IEEE API. Trên máy có mạng,
chạy bản thật bằng: make run QUERY="..."

Chạy demo (mặc định: chủ đề RAG):
    .venv/bin/python demo/rag_demo.py
    .venv/bin/python demo/rag_demo.py --seed demo/agentic_seed.json \
        --query "llm agents harness engineering" --db staging/demo_agentic.db

- DB riêng (không đụng DB vận hành mặc định), xóa làm lại mỗi lần chạy.
- Có Ollama đang chạy -> tự cắm StructuralParser; không có -> tất định thuần
  (doc vào queue ở trạng thái degraded — tầng M4 sẽ flag và alert).
- Sau batch: ghi bảng runs + chạy máy trạng thái alert + in health snapshot,
  đúng những gì CLI `pipeline run` thật làm từ M4.
- Approve luôn ép dry-run (không bao giờ tạo trang Notion thật từ dữ liệu demo).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # chạy được khi chưa pip install -e

from sr_agent.ingest.router import SourceRouter
from sr_agent.models.schemas import Document
from sr_agent.monitor import alerts, health
from sr_agent.pipeline import BatchReport, Pipeline
from sr_agent.publish.notion_page import NotionPublisher
from sr_agent.store.staging import StagingStore

DEFAULT_SEED = Path(__file__).parent / "rag_seed.json"
DEFAULT_DB = ROOT / "staging" / "demo_rag.db"
DEFAULT_QUERY = "retrieval augmented generation"


class DemoFetcher:
    """Fetcher tất định đọc từ seed JSON — cùng giao diện với fetcher thật."""

    def __init__(self, source: str, docs: list[Document]):
        self.source = source
        self.docs = docs

    def search(self, query: str, max_results: int = 20) -> list[str]:
        return [d.source_id for d in self.docs[:max_results]]

    def fetch(self, source_ids: list[str]) -> list[Document]:
        wanted = set(source_ids)
        return [d for d in self.docs if d.source_id in wanted]


def load_seed(seed_path: Path) -> dict[str, list[Document]]:
    raw = json.loads(seed_path.read_text(encoding="utf-8"))
    by_source: dict[str, list[Document]] = {"arxiv": [], "ieee": []}
    for p in raw["papers"]:
        doc = Document(
            uid="",
            source=p["source"],
            source_id=p["source_id"],
            authority_tier=p["authority_tier"],
            title=p["title"],
            abstract=p["abstract"],
            authors=p["authors"],
            published_date=datetime.fromisoformat(p["published_date"]),
            url=p["url"],
        )
        by_source[doc.source].append(doc)
    return by_source


def print_report(label: str, report: BatchReport) -> None:
    print(f"\n== {label} ==")
    print(
        f"fetched={report.fetched} new={report.new} dup={report.duplicates} "
        f"superseded={report.superseded} rubric_rejected={report.rejected_by_rubric} "
        f"queued={report.queued} dlq={report.dlq}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Demo SR-Agent bằng seed offline")
    ap.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    ap.add_argument("--query", default=DEFAULT_QUERY)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = ap.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    args.db.unlink(missing_ok=True)

    seed = load_seed(args.seed)
    router = SourceRouter(fetchers={
        "arxiv": DemoFetcher("arxiv", seed["arxiv"]),
        "ieee": DemoFetcher("ieee", seed["ieee"]),
    })

    # Cắm LLM parser nếu Ollama sẵn sàng — giống _build_default_pipeline
    from sr_agent.parser.ollama_client import OllamaClient

    client = OllamaClient()
    parser = None
    if client.is_available():
        from sr_agent.parser.structural import StructuralParser

        parser = StructuralParser(client).parse
        print(f"Ollama OK ({client.model}) — bật LLM parse.")
    else:
        print("Ollama không phản hồi — chạy tất định thuần "
              "(doc vào queue sẽ bị flag 'chưa phân tích LLM').")

    with StagingStore(args.db) as store:
        pipeline = Pipeline(store, router=router, parser=parser)

        started = datetime.now(timezone.utc).isoformat()
        report = pipeline.run(args.query)
        print_report(f'Batch — query "{args.query}"', report)

        # M4: heartbeat + máy trạng thái alert, đúng như CLI `pipeline run` thật
        store.record_run(args.query, started, json.dumps(asdict(report)))
        fired = alerts.evaluate(store, notifier=lambda t, m: print(f"  [ALERT] {t}: {m}"))
        if not fired:
            print("  (không có chuyển trạng thái alert nào — im lặng)")

        print("\n== Quyết định dedup (bảng events) ==")
        rows = list(store.conn.execute(
            "SELECT uid, event_type, detail FROM events ORDER BY id"))
        for row in rows:
            print(f"  [{row['event_type']}] {row['uid']}: {row['detail']}")
        if not rows:
            print("  (không có — seed không chứa bản trùng)")

        print(f"\n== Hàng đợi duyệt (WIP top-5 theo rubric, {args.query!r}) ==")
        queue = store.get_wip_queue()
        for i, doc in enumerate(queue, 1):
            degraded = " ⚠️ chưa phân tích LLM" if doc.tech_meta is None else ""
            print(f"\n{i}. [{doc.rubric.total:6.2f}] {doc.uid} — {doc.title}{degraded}")
            for c in doc.rubric.breakdown:
                print(f"     {c.key:<22} {c.sub_score:6.1f} x{c.weight:<4.0f} ({c.reason})")

        print("\n== Health snapshot (M4) ==")
        snap = health.snapshot(store)
        print(f"  degraded: {snap.degraded_count} | DLQ: {snap.dlq_total} | "
              f"status: {snap.status_counts}")
        print(f"  alert đang mở: {[a['key'] for a in alerts.open_alerts(store)] or 'không'}")

        # Approve bài top-1 — ÉP dry-run: demo không bao giờ ghi Notion thật
        if queue:
            top = queue[0]
            print(f"\n== Dry-run Approve bài top-1: {top.uid} ==")
            publisher = NotionPublisher(token="", parent_page_id="")
            publisher.publish(top, store)
            print(f"\n-> status sau approve: {store.get(top.uid).status.value}")


if __name__ == "__main__":
    main()

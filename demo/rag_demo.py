"""Chạy thử SR-Agent end-to-end với chủ đề RAG bằng bộ seed offline.

Dùng khi môi trường không truy cập được arXiv/IEEE API: nạp demo/rag_seed.json
qua ĐÚNG pipeline thật (D34 dedup -> rubric gate -> queue -> dry-run approve),
không sửa logic nào trong sr_agent/. Trên máy có mạng, chạy bản thật bằng:

    make run QUERY="retrieval augmented generation"

Chạy demo:
    .venv/bin/python demo/rag_demo.py

- DB riêng staging/demo_rag.db (không đụng DB vận hành mặc định), xóa làm lại
  mỗi lần chạy để kết quả tái lập được.
- Có Ollama đang chạy -> tự cắm StructuralParser (tech_meta + câu hỏi phản biện);
  không có -> chế độ tất định thuần, đúng hành vi suy giảm êm của pipeline.
- Approve luôn ép dry-run (không bao giờ tạo trang Notion thật từ dữ liệu demo).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # chạy được khi chưa pip install -e

from sr_agent.ingest.router import SourceRouter
from sr_agent.models.schemas import DocStatus, Document
from sr_agent.pipeline import BatchReport, Pipeline
from sr_agent.publish.notion_page import NotionPublisher
from sr_agent.store.staging import StagingStore

SEED_PATH = Path(__file__).parent / "rag_seed.json"
DEMO_DB = Path(__file__).parent.parent / "staging" / "demo_rag.db"
QUERY = "retrieval augmented generation"


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


def load_seed() -> dict[str, list[Document]]:
    raw = json.loads(SEED_PATH.read_text(encoding="utf-8"))
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
    DEMO_DB.parent.mkdir(parents=True, exist_ok=True)
    DEMO_DB.unlink(missing_ok=True)

    seed = load_seed()
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
        print("Ollama không phản hồi — chạy tất định thuần (không tech_meta/câu hỏi phản biện).")

    with StagingStore(DEMO_DB) as store:
        pipeline = Pipeline(store, router=router, parser=parser)

        print_report(f'Batch 1 — query "{QUERY}"', pipeline.run(QUERY))

        print("\n== Quyết định dedup (bảng events) ==")
        for row in store.conn.execute(
            "SELECT uid, event_type, detail FROM events ORDER BY id"
        ):
            print(f"  [{row['event_type']}] {row['uid']}: {row['detail']}")

        # Chạy lại cùng batch: demo D34 tầng 1 (exact ID) + idempotency
        print_report("Batch 2 — chạy lại y hệt (kiểm chứng idempotency)",
                     pipeline.run(QUERY))

        print(f"\n== Hàng đợi duyệt (WIP top-5 theo rubric, {QUERY!r}) ==")
        queue = store.get_wip_queue()
        for i, doc in enumerate(queue, 1):
            print(f"\n{i}. [{doc.rubric.total:6.2f}] {doc.uid} — {doc.title}")
            for c in doc.rubric.breakdown:
                print(f"     {c.key:<22} {c.sub_score:6.1f} x{c.weight:<4.0f} ({c.reason})")
            if doc.alternate_uids:
                print(f"     merged từ: {', '.join(doc.alternate_uids)}")

        print("\n== Trạng thái staging (DB demo) ==")
        for row in store.conn.execute(
            "SELECT status, COUNT(*) n FROM documents GROUP BY status ORDER BY status"
        ):
            print(f"  {row['status']:>10}: {row['n']}")

        # Approve bài top-1 — ÉP dry-run: demo không bao giờ ghi Notion thật
        if queue:
            top = queue[0]
            print(f"\n== Dry-run Approve bài top-1: {top.uid} ==")
            publisher = NotionPublisher(token="", parent_page_id="")
            publisher.publish(top, store)
            print(f"\n-> status sau approve: {store.get(top.uid).status.value}")


if __name__ == "__main__":
    main()

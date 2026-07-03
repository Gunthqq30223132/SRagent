"""Orchestrator ETL của SR-Agent.

Thứ tự "rẻ trước, đắt sau":
  purge TTL -> fetch -> D34 dedup -> rubric score (gate) -> [LLM parse] -> QUEUED

Nguyên tắc chống nghẽn mạch:
- try/except quanh TỪNG bản ghi: 1 bản lỗi chỉ rơi vào DLQ, batch vẫn chạy.
- TransientError đã hết lượt retry -> DLQ với retry_eligible=1 (retry-dlq xử lý lại).
- PermanentError -> DLQ + quarantine raw payload để debug thủ công.
- Circuit breaker: N lỗi transient liên tiếp từ 1 nguồn -> skip nguồn đó
  trong batch hiện tại, nguồn còn lại vẫn chạy bình thường.

CLI:
  python -m sr_agent.pipeline run --query "..." [--max-results 20]
  python -m sr_agent.pipeline retry-dlq
  python -m sr_agent.pipeline status
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from typing import Callable

from sr_agent.config import CIRCUIT_BREAKER_FAILURES, QUARANTINE_DIR
from sr_agent.dedup.d34 import DedupAction, decide, merge_superseded
from sr_agent.errors import PermanentError, TransientError
from sr_agent.ingest.router import SourceRouter
from sr_agent.models.schemas import DocStatus, Document
from sr_agent.quality.rubric import DEFAULT_RUBRIC, score_document
from sr_agent.store.staging import StagingStore

logger = logging.getLogger("sr_agent.pipeline")

# Parser là pluggable: M1 chạy không LLM (None), M2 cắm structural parser vào.
ParserFn = Callable[[Document], Document]


@dataclass
class BatchReport:
    fetched: int = 0
    new: int = 0
    duplicates: int = 0
    superseded: int = 0
    rejected_by_rubric: int = 0
    queued: int = 0
    dlq: int = 0
    purged: list[str] = field(default_factory=list)
    skipped_sources: list[str] = field(default_factory=list)


def _quarantine(uid: str, raw: str) -> str:
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    path = QUARANTINE_DIR / f"{uid.replace(':', '_')}.raw"
    path.write_text(raw, encoding="utf-8")
    return str(path)


class Pipeline:
    def __init__(
        self,
        store: StagingStore,
        router: SourceRouter | None = None,
        parser: ParserFn | None = None,
        rubric: dict | None = None,
    ):
        self.store = store
        self.router = router or SourceRouter()
        self.parser = parser
        self.rubric = rubric or DEFAULT_RUBRIC

    # --- bước xử lý 1 bản ghi (được cô lập lỗi ở run()) -----------------------

    def process_document(self, doc: Document, report: BatchReport) -> None:
        decision = decide(
            doc,
            existing_uids=self.store.all_uids(),
            titles_index=self.store.titles_index(),
            tier_lookup=self.store.tiers_index(),
        )
        if decision.action is DedupAction.DUPLICATE_ID:
            report.duplicates += 1
            return
        if decision.action is DedupAction.DUPLICATE_FUZZY:
            report.duplicates += 1
            self.store.log_event(
                doc.uid, "DEDUP_DROPPED",
                f"trùng mờ với {decision.matched_uid} (score={decision.score:.1f})",
            )
            return
        if decision.action is DedupAction.SUPERSEDES:
            loser = self.store.get(decision.matched_uid)
            if loser is not None:
                doc = merge_superseded(doc, loser)
                self.store.conn.execute(
                    "DELETE FROM documents WHERE uid = ?", (decision.matched_uid,)
                )
                self.store.conn.commit()
            report.superseded += 1
            self.store.log_event(
                doc.uid, "DEDUP_MERGED",
                f"thay thế {decision.matched_uid} (tier ưu tiên, score={decision.score:.1f})",
            )
        else:
            report.new += 1
        doc.status = DocStatus.DEDUPED

        # Rubric gate: loại tài liệu kém TRƯỚC khi tốn LLM
        doc.rubric = score_document(doc, self.rubric)
        doc.status = DocStatus.SCORED
        if not doc.rubric.passed:
            report.rejected_by_rubric += 1
            doc.status = DocStatus.REJECTED
            self.store.upsert(doc)
            self.store.log_event(
                doc.uid, "RUBRIC_REJECTED", f"điểm {doc.rubric.total} dưới ngưỡng"
            )
            return

        if self.parser is not None:
            doc = self.parser(doc)
            doc.status = DocStatus.PARSED

        doc.status = DocStatus.QUEUED
        self.store.upsert(doc)
        report.queued += 1

    # --- batch run ----------------------------------------------------------------

    def run(self, query: str, max_results: int = 20) -> BatchReport:
        report = BatchReport()
        report.purged = self.store.purge_expired()
        if report.purged:
            logger.info("TTL purge: %d bản ghi", len(report.purged))

        for source, fetcher in self.router.fetchers.items():
            consecutive_failures = 0
            try:
                ids = fetcher.search(query, max_results=max_results)
                docs = fetcher.fetch(ids)
            except TransientError as exc:
                # cả nguồn sập (rate limit/search fail) -> skip, nguồn khác vẫn chạy
                logger.warning("Nguồn %s lỗi transient, bỏ qua batch này: %s", source, exc)
                self.store.push_dlq(
                    f"{source}:batch", type(exc).__name__, str(exc), retry_eligible=True
                )
                report.skipped_sources.append(source)
                report.dlq += 1
                continue
            except PermanentError as exc:
                logger.error("Nguồn %s trả dữ liệu hỏng: %s", source, exc)
                self.store.push_dlq(f"{source}:batch", type(exc).__name__, str(exc))
                report.skipped_sources.append(source)
                report.dlq += 1
                continue

            report.fetched += len(docs)
            for doc in docs:
                try:
                    self.process_document(doc, report)
                    consecutive_failures = 0
                except TransientError as exc:
                    consecutive_failures += 1
                    report.dlq += 1
                    self._demote_to_dlq(doc, exc, retry_eligible=True)
                    if consecutive_failures >= CIRCUIT_BREAKER_FAILURES:
                        logger.warning(
                            "Circuit breaker: %s lỗi %d lần liên tiếp — skip phần còn lại",
                            source, consecutive_failures,
                        )
                        report.skipped_sources.append(source)
                        break
                except PermanentError as exc:
                    report.dlq += 1
                    raw_path = _quarantine(doc.uid, doc.model_dump_json())
                    self._demote_to_dlq(doc, exc, raw_path=raw_path)
        return report

    def _demote_to_dlq(
        self,
        doc: Document,
        exc: Exception,
        *,
        retry_eligible: bool = False,
        raw_path: str | None = None,
    ) -> None:
        """Cô lập bản ghi lỗi: bảng dlq + hạ documents.status xuống DLQ."""
        self.store.push_dlq(
            doc.uid, type(exc).__name__, str(exc),
            raw_path=raw_path, retry_eligible=retry_eligible,
        )
        doc.status = DocStatus.DLQ
        self.store.upsert(doc)

    def retry_dlq(self, max_results_per_entry: int = 1) -> int:
        """Tái xử lý các entry retry_eligible: fetch lại theo uid rồi đi lại pipeline."""
        retried = 0
        for entry in self.store.dlq_entries(retry_eligible_only=True):
            uid = entry["uid"]
            if uid.endswith(":batch"):
                continue  # batch-level: chạy lại bằng lệnh run
            try:
                source, source_id = self.router.classify(uid.split(":", 1)[1] if uid.startswith("ieee:") else uid)
                docs = self.router.fetcher_for(source).fetch([source_id])
                report = BatchReport()
                for doc in docs:
                    self.process_document(doc, report)
                self.store.clear_dlq_entry(entry["id"])
                retried += 1
            except (TransientError, PermanentError) as exc:
                logger.warning("Retry DLQ %s vẫn lỗi: %s", uid, exc)
        return retried


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="sr_agent.pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="chạy 1 batch ingest")
    run_p.add_argument("--query", required=True)
    run_p.add_argument("--max-results", type=int, default=20)
    sub.add_parser("retry-dlq", help="tái xử lý DLQ retry_eligible")
    sub.add_parser("status", help="thống kê staging")
    args = ap.parse_args(argv)

    with StagingStore() as store:
        pipeline = _build_default_pipeline(store)
        if args.cmd == "run":
            report = pipeline.run(args.query, max_results=args.max_results)
            print(
                f"fetched={report.fetched} new={report.new} dup={report.duplicates} "
                f"superseded={report.superseded} rubric_rejected={report.rejected_by_rubric} "
                f"queued={report.queued} dlq={report.dlq} purged={len(report.purged)} "
                f"skipped_sources={report.skipped_sources}"
            )
        elif args.cmd == "retry-dlq":
            print(f"retried={pipeline.retry_dlq()}")
        elif args.cmd == "status":
            for row in store.conn.execute(
                "SELECT status, COUNT(*) n FROM documents GROUP BY status"
            ):
                print(f"{row['status']:>10}: {row['n']}")
            print(f"{'dlq':>10}: {len(store.dlq_entries())}")
    return 0


def _build_default_pipeline(store: StagingStore) -> Pipeline:
    """Cắm structural parser nếu Ollama sẵn sàng; không thì chạy tất định thuần."""
    from sr_agent.parser.ollama_client import OllamaClient
    from sr_agent.parser.structural import StructuralParser

    client = OllamaClient()
    if client.is_available():
        return Pipeline(store, parser=StructuralParser(client).parse)
    logger.info(
        "Ollama không phản hồi tại %s — chạy pipeline tất định thuần (không LLM parse)",
        client.base_url,
    )
    return Pipeline(store)


if __name__ == "__main__":
    sys.exit(main())

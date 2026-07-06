"""Auto-recovery: heal (retry DLQ khi hạ tầng hồi phục) + enrich (LLM đêm).

Chạy nền qua launchd mỗi 15 phút (com.sragent.heal) — probe trước, hành động
sau, thoát nhanh khi không có gì làm. Không đụng control flow của Pipeline:
heal chỉ GỌI các API sẵn có (run/retry_dlq) đúng lúc hạ tầng đã sống lại.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Callable

from sr_agent.config import AUTHORITY_TIERS, OLLAMA_MODEL, QUARANTINE_DIR
from sr_agent.errors import PermanentError, TransientError
from sr_agent.models.schemas import DocStatus, Document
from sr_agent.monitor import alerts, probes
from sr_agent.store.staging import StagingStore

logger = logging.getLogger("sr_agent.monitor.recover")

ENRICH_WINDOW = range(1, 6)     # 01:00–05:59 giờ máy — Ollama chạy khi máy rảnh
HOUSEKEEPING_DAYS = 90
DEFAULT_ENRICH_LIMIT = 10       # trần mỗi đêm: ~1-3 phút/doc với model 7B trên M4


def enrich_degraded(
    store: StagingStore,
    *,
    limit: int = DEFAULT_ENRICH_LIMIT,
    parse_fn: Callable[[Document], Document] | None = None,
) -> int:
    """Tái xử lý doc QUEUED heuristic-only bằng LLM. Trả về số doc đã enrich.

    Chỉ đụng QUEUED — bản APPROVED bất biến (trang Notion đã phát hành).
    Per-doc try/except đúng taxonomy sẵn có: Permanent -> DLQ + quarantine;
    Transient -> dừng đợt (Ollama chập chờn, đêm sau heal thử lại).
    """
    if parse_fn is None:
        from sr_agent.parser.ollama_client import OllamaClient
        from sr_agent.parser.structural import StructuralParser

        client = OllamaClient()
        if not client.is_available():
            logger.info("enrich: Ollama không phản hồi — bỏ qua đợt này")
            return 0
        parse_fn = StructuralParser(client).parse

    enriched = 0
    for uid in store.degraded_uids()[:limit]:
        doc = store.get(uid)
        if doc is None:
            continue
        try:
            doc = parse_fn(doc)
            doc.status = DocStatus.QUEUED
            store.upsert(doc)  # touch=True: reset TTL — doc vừa được làm giàu
            store.log_event(uid, "ENRICHED", f"model={OLLAMA_MODEL}")
            enriched += 1
        except TransientError as exc:
            logger.warning("enrich: %s lỗi transient (%s) — dừng đợt", uid, exc)
            break
        except PermanentError as exc:
            from sr_agent.pipeline import _quarantine

            raw_path = _quarantine(uid, doc.model_dump_json())
            store.push_dlq(uid, type(exc).__name__, str(exc), raw_path=raw_path)
            store.set_status(uid, DocStatus.DLQ)
    return enriched


def _housekeeping(store: StagingStore, days: int = HOUSEKEEPING_DAYS) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    store.conn.execute("DELETE FROM events WHERE created_at < ?", (cutoff,))
    store.conn.execute(
        "DELETE FROM dlq WHERE retry_eligible = 0 AND created_at < ?", (cutoff,)
    )
    store.conn.commit()
    if QUARANTINE_DIR.exists():
        limit_ts = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
        for f in QUARANTINE_DIR.iterdir():
            if f.is_file() and f.stat().st_mtime < limit_ts:
                f.unlink(missing_ok=True)


def heal(
    store: StagingStore,
    *,
    now: bool = False,
    query: str | None = None,
    pipeline_factory: Callable[[StagingStore], "object"] | None = None,
    probe_source_fn: Callable[[str], bool] = probes.probe_source,
    probe_ollama_fn: Callable[[], bool] = probes.probe_ollama,
    notifier=alerts.notify,
) -> dict:
    """Một chu kỳ heal. Trả về summary dict (phục vụ log/test).

    now=True bỏ qua cửa sổ đêm của enrich (chạy tay/kiểm thử).
    """
    if pipeline_factory is None:
        from sr_agent.pipeline import _build_default_pipeline

        pipeline_factory = _build_default_pipeline

    summary: dict = {"sources_up": [], "batch_rerun": None,
                     "retried_docs": 0, "bumped": 0, "enriched": 0}
    reachable = {s for s in AUTHORITY_TIERS if probe_source_fn(s)}
    summary["sources_up"] = sorted(reachable)
    ollama_up = probe_ollama_fn()
    summary["ollama_up"] = ollama_up

    entries = store.dlq_entries(retry_eligible_only=True)
    batch_entries = [e for e in entries if e["uid"].endswith(":batch")]
    doc_entries = [e for e in entries if not e["uid"].endswith(":batch")]

    pipeline = None

    # 1. Nguồn sập toàn phần đã sống lại -> chạy lại standing query
    healable_batches = [
        e for e in batch_entries if e["uid"].split(":", 1)[0] in reachable
    ]
    if healable_batches:
        run_query = query or (
            store.last_run()["query"] if store.last_run() else None
        )
        if run_query:
            # entry batch của nguồn đã thông bị thay bằng kết quả run mới
            # (nguồn còn sập sẽ tự sinh entry mới từ chính lần run này)
            for e in healable_batches:
                store.clear_dlq_entry(e["id"])
            pipeline = pipeline_factory(store)
            report = pipeline.run(run_query)
            summary["batch_rerun"] = {"query": run_query, **asdict(report)}
            store.record_run(
                run_query, datetime.now(timezone.utc).isoformat(),
                json.dumps(asdict(report)),
            )
        else:
            logger.warning("heal: có entry batch nhưng chưa biết standing query "
                           "(bảng runs trống) — chạy `pipeline run` một lần trước")

    # 2. Bản ghi lẻ chờ retry -> Pipeline.retry_dlq() sẵn có; fail thì tăng attempts
    doc_ids_before = {
        e["id"] for e in doc_entries if e["uid"].split(":", 1)[0] in reachable
    }
    if doc_ids_before:
        pipeline = pipeline or pipeline_factory(store)
        summary["retried_docs"] = pipeline.retry_dlq()
        still_there = {e["id"] for e in store.dlq_entries(retry_eligible_only=True)}
        for entry_id in doc_ids_before & still_there:
            store.bump_dlq_attempt(entry_id)
            summary["bumped"] += 1

    # 3. Ollama sống + có doc degraded -> enrich (trong cửa sổ đêm, trừ khi --now)
    if ollama_up and store.degraded_uids():
        if now or datetime.now().hour in ENRICH_WINDOW:
            summary["enriched"] = enrich_degraded(store)

    _housekeeping(store)

    # 4. Cập nhật máy trạng thái alert — nơi phát tin "🟢 đã hồi phục"
    summary["alerts"] = alerts.evaluate(store, ollama_up=ollama_up, notifier=notifier)
    return summary

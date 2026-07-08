"""Cầu nối ngữ nghĩa → ID tất định (bản tinh gọn, thay TS-D29-01 v1.0).

Nguyên tắc: ngữ nghĩa của con người (chủ đề, từ khóa) dừng lại Ở ĐÂY — tầng
ngoại vi. Mọi thứ đi vào core là ID khớp config.ID_PATTERNS. Core (router,
Pipeline, config) KHÔNG bị sửa một dòng nào: per-source query đạt được bằng
ProfiledFetcher — wrapper thay query ở tầng adapter.

3 chế độ:
    # Chạy thẳng: chủ đề -> query per-source (profile) -> pipeline thật
    .venv/bin/python tools/topic_run.py --terms "retrieval augmented generation"

    # Lập kế hoạch để người duyệt TRƯỚC khi nạp: chỉ search lấy ID, ghi manifest
    .venv/bin/python tools/topic_run.py --terms "..." --plan --out plan.json

    # Nạp manifest đã duyệt/chỉnh tay (ID được validate lại tại biên)
    .venv/bin/python tools/topic_run.py --from-plan plan.json

--topic ghi lại ý định gốc (mọi ngôn ngữ) vào manifest/runs; --terms là cụm
từ khóa tiếng Anh đổ vào template. --expand nhờ Ollama local sinh thêm biến
thể terms (structured output, temperature 0) — Ollama chết thì suy giảm êm.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # chạy được khi chưa pip install -e

from pydantic import BaseModel, Field

from sr_agent.config import ID_PATTERNS
from sr_agent.errors import PermanentError, SRAgentError, TransientError
from sr_agent.ingest.arxiv import ArxivFetcher, normalize_arxiv_id
from sr_agent.ingest.ieee import IEEEXploreFetcher
from sr_agent.ingest.router import SourceRouter
from sr_agent.models.schemas import DocStatus
from sr_agent.pipeline import BatchReport, Pipeline
from sr_agent.store.staging import StagingStore

logger = logging.getLogger("tools.topic_run")

DEFAULT_PROFILE = Path(__file__).parent / "profiles" / "default.json"
MANIFEST_VERSION = "1.0"


# --- profile & queries --------------------------------------------------------------

def load_profile(path: Path) -> dict:
    profile = json.loads(path.read_text(encoding="utf-8"))
    if "sources" not in profile:
        raise ValueError(f"Profile {path} thiếu key 'sources'")
    return profile


def render_queries(profile: dict, source: str, terms_list: list[str]) -> list[str]:
    """Mỗi template × mỗi cụm terms = 1 query; union giữ thứ tự, bỏ trùng."""
    templates = profile["sources"].get(source, {}).get("templates", [])
    seen: list[str] = []
    for terms in terms_list:
        for tpl in templates:
            q = tpl.format(terms=terms)
            if q not in seen:
                seen.append(q)
    return seen


class _TermsExpansion(BaseModel):
    """Schema cho Ollama structured output — biến thể từ khóa tìm kiếm."""

    terms: list[str] = Field(
        min_length=1, max_length=5,
        description="English search key-phrases for academic databases, "
                    "each 2-6 words, no boolean operators",
    )


def expand_terms(topic: str, base_terms: list[str]) -> list[str]:
    """Nhờ LLM local sinh thêm biến thể terms. Lỗi bất kỳ -> trả base (suy giảm êm)."""
    try:
        from sr_agent.parser.ollama_client import OllamaClient

        client = OllamaClient()
        if not client.is_available():
            logger.warning("--expand: Ollama không phản hồi — dùng terms gốc")
            return base_terms
        result = client.generate_structured(
            system_prompt=(
                "You generate search key-phrases for academic databases (IEEE, arXiv). "
                "Given a research topic in any language, output 3-5 English key-phrases "
                "covering its main aspects. No boolean operators, no quotes."
            ),
            user_prompt=f"Topic: {topic}",
            schema_model=_TermsExpansion,
        )
        merged = list(dict.fromkeys([*base_terms, *result.terms]))
        return merged
    except (SRAgentError, Exception) as exc:  # sink mở rộng không được làm sập tool
        logger.warning("--expand lỗi (%s) — dùng terms gốc", exc)
        return base_terms


# --- adapter wrapper: per-source query, core không đổi -------------------------------

class ProfiledFetcher:
    """Wrapper thay query ở tầng adapter — Pipeline.run() giữ nguyên hợp đồng.

    search() BỎ QUA query truyền vào, chạy lần lượt các query của profile,
    union ID (giữ thứ tự, bỏ trùng), cắt trần max_results. fetch() passthrough.
    """

    def __init__(self, inner, queries: list[str]):
        self.inner = inner
        self.source = inner.source
        self.queries = queries

    def search(self, query: str, max_results: int = 20) -> list[str]:
        ids: list[str] = []
        for q in self.queries:
            for sid in self.inner.search(q, max_results=max_results):
                if sid not in ids:
                    ids.append(sid)
            if len(ids) >= max_results:
                break
        return ids[:max_results]

    def fetch(self, source_ids):
        return self.inner.fetch(source_ids)


def build_fetchers(sources: list[str]) -> dict:
    real = {"arxiv": ArxivFetcher, "ieee": IEEEXploreFetcher}
    return {s: real[s]() for s in sources}


def _validate_id(source: str, raw_id: str) -> str | None:
    """ID hợp lệ (đã chuẩn hóa) hoặc None. Không bao giờ 'sửa đoán' ID."""
    if source == "arxiv":
        return normalize_arxiv_id(raw_id)
    return raw_id if ID_PATTERNS[source].match(raw_id) else None


# --- 3 chế độ ------------------------------------------------------------------------

def plan(topic: str, queries_by_source: dict[str, list[str]],
         fetchers: dict, max_per_source: int) -> dict:
    """Chỉ search lấy ID + provenance, KHÔNG fetch nội dung, KHÔNG đụng DB."""
    manifest = {
        "spec_version": MANIFEST_VERSION,
        "topic": topic,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queries": queries_by_source,
        "items": [],
        "rejected": [],
    }
    for source, queries in queries_by_source.items():
        fetcher, rank = fetchers[source], 0
        seen: set[str] = set()
        for q in queries:
            try:
                found = fetcher.search(q, max_results=max_per_source)
            except SRAgentError as exc:
                manifest["rejected"].append(
                    {"raw_id": f"{source}:<query>", "reason": f"search lỗi: {exc}"})
                continue
            for raw in found:
                valid = _validate_id(source, raw)
                if valid is None:
                    manifest["rejected"].append(
                        {"raw_id": raw, "reason": "không khớp ID_PATTERNS"})
                elif valid not in seen and rank < max_per_source:
                    rank += 1
                    seen.add(valid)
                    manifest["items"].append({
                        "source": source, "id": valid,
                        "rank": rank, "found_by_query": q,
                    })
    return manifest


def ingest_manifest(store: StagingStore, manifest: dict,
                    fetchers: dict, parser=None) -> BatchReport:
    """Nạp manifest đã duyệt: validate lại ID tại biên rồi đi đúng pipeline thật."""
    pipeline = Pipeline(store, router=SourceRouter(fetchers=fetchers), parser=parser)
    report = BatchReport()
    report.purged = store.purge_expired()

    by_source: dict[str, list[str]] = {}
    for item in manifest.get("items", []):
        valid = _validate_id(item["source"], item["id"])
        if valid is None:  # manifest có thể bị sửa tay -> biên phải tự vệ
            logger.warning("Bỏ qua ID không hợp lệ trong manifest: %r", item["id"])
            continue
        by_source.setdefault(item["source"], []).append(valid)

    for source, ids in by_source.items():
        try:
            docs = fetchers[source].fetch(ids)
        except SRAgentError as exc:
            store.push_dlq(f"{source}:batch", type(exc).__name__, str(exc),
                           retry_eligible=isinstance(exc, TransientError))
            report.skipped_sources.append(source)
            report.dlq += 1
            continue
        report.fetched += len(docs)
        for doc in docs:  # cô lập lỗi từng bản ghi như run()
            try:
                pipeline.process_document(doc, report)
            except (TransientError, PermanentError) as exc:
                store.push_dlq(doc.uid, type(exc).__name__, str(exc),
                               retry_eligible=isinstance(exc, TransientError))
                doc.status = DocStatus.DLQ
                store.upsert(doc)
                report.dlq += 1
    return report


def run_direct(store: StagingStore, topic: str,
               queries_by_source: dict[str, list[str]],
               fetchers: dict, parser=None) -> BatchReport:
    """Chạy thẳng qua pipeline thật với fetcher đã profile hóa + ghi M4."""
    wrapped = {
        s: ProfiledFetcher(f, queries_by_source[s]) for s, f in fetchers.items()
    }
    pipeline = Pipeline(store, router=SourceRouter(fetchers=wrapped), parser=parser)
    started = datetime.now(timezone.utc).isoformat()
    report = pipeline.run(topic)  # query bị ProfiledFetcher bỏ qua — chỉ làm nhãn
    from dataclasses import asdict

    from sr_agent.monitor import alerts

    store.record_run(topic, started, json.dumps(asdict(report)))
    alerts.evaluate(store)
    return report


def _build_parser():
    """Cắm LLM parser nếu Ollama sống (đúng hành vi _build_default_pipeline)."""
    from sr_agent.parser.ollama_client import OllamaClient

    client = OllamaClient()
    if client.is_available():
        from sr_agent.parser.structural import StructuralParser

        return StructuralParser(client).parse
    return None


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(
        description="Cầu nối: chủ đề ngữ nghĩa -> query per-source -> pipeline/manifest")
    ap.add_argument("--topic", default="", help="ý định gốc, mọi ngôn ngữ (làm nhãn/expand)")
    ap.add_argument("--terms", default="", help="cụm từ khóa tiếng Anh đổ vào template")
    ap.add_argument("--sources", default="arxiv,ieee")
    ap.add_argument("--max-per-source", type=int, default=20)
    ap.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    ap.add_argument("--expand", action="store_true", help="Ollama sinh thêm biến thể terms")
    ap.add_argument("--plan", action="store_true", help="chỉ ghi manifest ID, không nạp")
    ap.add_argument("--out", type=Path, default=None, help="đường dẫn manifest (chế độ --plan)")
    ap.add_argument("--from-plan", type=Path, default=None, help="nạp manifest đã duyệt")
    ap.add_argument("--db", type=Path, default=None, help="override DB (mặc định theo config)")
    args = ap.parse_args(argv)

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    store_path = args.db if args.db else None

    if args.from_plan:
        manifest = json.loads(args.from_plan.read_text(encoding="utf-8"))
        with StagingStore(store_path) if store_path else StagingStore() as store:
            report = ingest_manifest(store, manifest, build_fetchers(sources),
                                     parser=_build_parser())
            print(f"fetched={report.fetched} queued={report.queued} "
                  f"dup={report.duplicates} rejected={report.rejected_by_rubric} "
                  f"dlq={report.dlq}")
        return 0

    terms = [t for t in [args.terms.strip() or args.topic.strip()] if t]
    if not terms:
        ap.error("cần --terms (tiếng Anh) hoặc --topic")
    if not args.terms.strip() and not args.topic.isascii():
        logger.warning("--topic không phải tiếng Anh và thiếu --terms: recall sẽ thấp. "
                       "Dùng --terms hoặc --expand (cần Ollama).")
    if args.expand:
        terms = expand_terms(args.topic or terms[0], terms)
        logger.info("terms sau expand: %s", terms)

    profile = load_profile(args.profile)
    queries_by_source = {s: render_queries(profile, s, terms) for s in sources}
    for s, qs in queries_by_source.items():
        logger.info("query[%s] = %s", s, qs)

    if args.plan:
        manifest = plan(args.topic or terms[0], queries_by_source,
                        build_fetchers(sources), args.max_per_source)
        out = args.out or (ROOT / "staging" / "inbox" /
                           f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.manifest.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")  # ghi atomic
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.rename(out)
        print(str(out))
        return 0 if manifest["items"] else 2

    with StagingStore(store_path) if store_path else StagingStore() as store:
        report = run_direct(store, args.topic or terms[0], queries_by_source,
                            build_fetchers(sources), parser=_build_parser())
        print(f"fetched={report.fetched} queued={report.queued} "
              f"dup={report.duplicates} rejected={report.rejected_by_rubric} "
              f"dlq={report.dlq} skipped={report.skipped_sources}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

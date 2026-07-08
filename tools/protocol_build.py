"""Review Protocol Builder (PICO + exclusion criteria).

Generates, renders, and runs review protocols for the SR-Agent system.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field

from sr_agent.store.staging import StagingStore
from tools.topic_run import DEFAULT_PROFILE, build_fetchers, load_profile, run_direct

logger = logging.getLogger("tools.protocol_build")


# --- Contracts (D1) ------------------------------------------------------------------

class PicoConcept(BaseModel):
    concept: str                 # cụm chính, tiếng Anh
    synonyms: list[str] = Field(default_factory=list)     # OR trong cùng khối
    required: bool = True        # False = không vào query, chỉ dùng khi screening


class ReviewProtocol(BaseModel):
    topic_vi: str                        # ý định gốc — chỉ là nhãn/audit
    population: PicoConcept
    intervention: PicoConcept
    comparison: PicoConcept | None = None
    outcome: PicoConcept | None = None
    year_range: tuple[int, int] | None = None
    languages: list[str] = Field(default_factory=lambda: ["en"])
    study_types_excluded: list[str] = Field(default_factory=lambda: ["editorial", "poster", "thesis"])
    exclusion_criteria: list[str]        # tập con của ET1..ET7, EF1..EF4


# --- Helper functions ----------------------------------------------------------------

def make_slug(text: str) -> str:
    # Chuẩn hóa về không dấu tiếng Việt đơn giản (nếu có)
    # Ở đây dùng regex đơn giản thay thế ký tự đặc biệt
    text = text.lower()
    # Loại bỏ dấu tiếng Việt cơ bản để có slug đẹp
    map_chars = {
        "á": "a", "à": "a", "ả": "a", "ã": "a", "ạ": "a", "ă": "a", "ắ": "a", "ằ": "a", "ẳ": "a", "ẵ": "a", "ặ": "a",
        "â": "a", "ấ": "a", "ầ": "a", "ẩ": "a", "ẫ": "a", "ậ": "a", "é": "e", "è": "e", "ẻ": "e", "ẽ": "e", "ẹ": "e",
        "ê": "e", "ế": "e", "ề": "e", "ể": "e", "ễ": "e", "ệ": "e", "í": "i", "ì": "i", "ỉ": "i", "ĩ": "i", "ị": "i",
        "ó": "o", "ò": "o", "ỏ": "o", "õ": "o", "ọ": "o", "ô": "o", "ố": "o", "ồ": "o", "ổ": "o", "ỗ": "o", "ộ": "o",
        "ơ": "o", "ớ": "o", "ờ": "o", "ở": "o", "ỡ": "o", "ợ": "o", "ú": "u", "ù": "u", "ủ": "u", "ũ": "u", "ụ": "u",
        "ư": "u", "ứ": "u", "ừ": "u", "ử": "u", "ữ": "u", "ự": "u", "ý": "y", "ỳ": "y", "ỷ": "y", "ỹ": "y", "ỵ": "y",
        "đ": "d",
    }
    for k, v in map_chars.items():
        text = text.replace(k, v)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def make_concept_expr(concept: PicoConcept) -> str:
    terms = [concept.concept] + concept.synonyms
    quoted_terms = []
    for t in terms:
        t_clean = t.strip().strip('"')
        if t_clean:
            quoted_terms.append(f'"{t_clean}"')
    if not quoted_terms:
        return ""
    if len(quoted_terms) == 1:
        return quoted_terms[0]
    return f"({ ' OR '.join(quoted_terms) })"


def render_pico_query(template: str, p_expr: str, i_expr: str) -> str:
    t = template
    # Nếu template chứa P hoặc I và có bọc trong nháy kép
    if "{P}" in t:
        if '"{P}"' in t:
            t = t.replace('"{P}"', "{P}")
        elif '\\"{P}\\"' in t:
            t = t.replace('\\"{P}\\"', "{P}")
    if "{I}" in t:
        if '"{I}"' in t:
            t = t.replace('"{I}"', "{I}")
        elif '\\"{I}\\"' in t:
            t = t.replace('\\"{I}\\"', "{I}")
    
    if "{P}" in t or "{I}" in t:
        kwargs = {}
        if "{P}" in t:
            kwargs["P"] = p_expr
        if "{I}" in t:
            kwargs["I"] = i_expr
        return t.format(**kwargs)
    
    if "{terms}" in t:
        combined = f"{p_expr} AND {i_expr}"
        if '"{terms}"' in t:
            t = t.replace('"{terms}"', "{terms}")
        elif '\\"{terms}\\"' in t:
            t = t.replace('\\"{terms}\\"', "{terms}")
        return t.format(terms=combined)
        
    return t


def compile_queries(protocol: ReviewProtocol, profile: dict, sources: list[str]) -> dict[str, list[str]]:
    p_expr = make_concept_expr(protocol.population)
    i_expr = make_concept_expr(protocol.intervention)
    
    queries_by_source = {}
    for src in sources:
        templates = profile["sources"].get(src, {}).get("templates", [])
        rendered = []
        for tpl in templates:
            q = render_pico_query(tpl, p_expr, i_expr)
            if q and q not in rendered:
                rendered.append(q)
        queries_by_source[src] = rendered
    return queries_by_source


# --- CLI commands --------------------------------------------------------------------

def draft_protocol_llm(topic: str) -> ReviewProtocol:
    """Gọi LLM local để tạo bản nháp Protocol."""
    try:
        from sr_agent.parser.ollama_client import OllamaClient
        
        client = OllamaClient()
        if not client.is_available():
            logger.warning("Ollama không phản hồi — dùng skeleton rỗng")
            return make_skeleton(topic)
            
        system_prompt = (
            "You are an expert Systematic Review librarian. Given a research topic, "
            "generate a formal ReviewProtocol following the PICO framework. "
            "Identify the Population (P) and Intervention (I) concepts and English synonyms. "
            "Output structure must match the provided JSON schema."
        )
        
        result = client.generate_structured(
            system_prompt=system_prompt,
            user_prompt=f"Research Topic: {topic}",
            schema_model=ReviewProtocol,
        )
        # Ghi đè lại topic_vi cho chính xác
        result.topic_vi = topic
        return result
    except Exception as exc:
        logger.warning("Lỗi khi tạo draft bằng LLM: %s. Dùng skeleton rỗng.", exc)
        return make_skeleton(topic)


def make_skeleton(topic: str) -> ReviewProtocol:
    """Tạo skeleton rỗng kèm hướng dẫn điền tay."""
    return ReviewProtocol(
        topic_vi=topic,
        population=PicoConcept(
            concept="[Điền Population chính bằng tiếng Anh tại đây]",
            synonyms=["[Biến thể 1]", "[Biến thể 2]"]
        ),
        intervention=PicoConcept(
            concept="[Điền Intervention chính bằng tiếng Anh tại đây]",
            synonyms=["[Biến thể 1]", "[Biến thể 2]"]
        ),
        exclusion_criteria=["ET1", "ET2", "ET3", "ET4", "ET5", "ET7"]
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Review Protocol Builder")
    ap.add_argument("--topic", help="Ý định gốc/chủ đề nghiên cứu bằng tiếng Việt")
    ap.add_argument("--draft-llm", action="store_true", help="Sử dụng Ollama để tự động đề xuất nháp")
    ap.add_argument("--render", type=Path, help="Đọc file JSON protocol và render truy vấn")
    ap.add_argument("--profile", type=Path, default=DEFAULT_PROFILE, help="Profile query per-source")
    ap.add_argument("--sources", default="arxiv,ieee", help="Danh sách nguồn tìm kiếm cách nhau bởi dấu phẩy")
    ap.add_argument("--run", action="store_true", help="Chạy thẳng pipeline ingestion sau khi render")
    ap.add_argument("--db", type=Path, help="Đường dẫn SQLite database ghi kết quả")
    
    args = ap.parse_args(argv)
    
    if args.render:
        if not args.render.exists():
            print(f"Lỗi: Không tìm thấy file protocol tại {args.render}", file=sys.stderr)
            return 1
            
        protocol = ReviewProtocol.model_validate_json(args.render.read_text(encoding="utf-8"))
        profile = load_profile(args.profile)
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
        
        queries = compile_queries(protocol, profile, sources)
        print(f"Rendered queries for topic: {protocol.topic_vi}")
        for src, qs in queries.items():
            print(f"[{src}]")
            for q in qs:
                print(f"  - {q}")
                
        if args.run:
            print("Khởi chạy pipeline ingestion với các truy vấn trên...")
            from tools.topic_run import _build_parser
            
            store_path = args.db if args.db else None
            fetchers = build_fetchers(sources)
            with StagingStore(store_path) if store_path else StagingStore() as store:
                report = run_direct(store, protocol.topic_vi, queries, fetchers, parser=_build_parser())
                print(f"Kết quả: fetched={report.fetched} queued={report.queued} "
                      f"dup={report.duplicates} rejected={report.rejected_by_rubric} "
                      f"dlq={report.dlq}")
        return 0
        
    if args.topic:
        slug = make_slug(args.topic)
        out_dir = ROOT / "tools" / "protocols"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{slug}.json"
        
        if args.draft_llm:
            protocol = draft_protocol_llm(args.topic)
        else:
            protocol = make_skeleton(args.topic)
            
        out_path.write_text(protocol.model_dump_json(indent=2), encoding="utf-8")
        print(f"Đã tạo protocol nháp tại: {out_path}")
        print("[CẢNH BÁO] Protocol phải được con người duyệt và chỉnh sửa trước khi dùng — tool không bao giờ tự chốt.")
        return 0
        
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

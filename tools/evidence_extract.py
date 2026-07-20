"""Evidence Extraction Tool (PRISMA exact-quote data extraction).

Extracts PICO fields with exact verbatim quotes and verifies them.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field, create_model

from sr_agent.config import OLLAMA_MODEL
from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from sr_agent.errors import ContextOverflowError
from tools.eligibility_run import build_full_text_str
from tools.guard.firewall import extract_anchors
from tools.screen_run import verify_quote

logger = logging.getLogger("tools.evidence_extract")


# --- Contracts (D3.2) ----------------------------------------------------------------

class EvidencedField(BaseModel):
    value: str
    quote: str          # trích VERBATIM từ văn bản nguồn
    section: str        # section id nơi quote nằm (title/abstract/context/method/...)


class LegacyField(BaseModel):
    id: str
    description_en: str
    value_hint: str | None = None


LEGACY_EXTRACTION_FIELDS = [
    LegacyField(id="has_code_repo", description_en="Whether a code repository link is explicitly stated (True/False)."),
    LegacyField(id="dataset_spec", description_en="The size/specification of dataset used verbatim, else null."),
    LegacyField(id="baselines", description_en="Verbatim list of baseline model names compared against, else null."),
    LegacyField(id="metrics", description_en="Verbatim list of evaluation metrics used, else null.")
]


# --- Helper functions ----------------------------------------------------------------

def get_section_text(doc: Document, section_name: str) -> str:
    s_name = section_name.strip().lower()
    if s_name == "full_text":
        return doc.full_text or ""
    if s_name == "title":
        return doc.title or ""
    if s_name == "abstract":
        return doc.abstract or ""
        
    # Check canonical sections
    for role, sec in doc.canonical_sections.items():
        if role.value == s_name and sec:
            return sec.content or ""
            
    # Check raw section attributes
    if doc.sections:
        for attr in ["introduction", "methods", "results", "discussion", "problem", "approach", "evaluation", "conclusion"]:
            if attr == s_name and hasattr(doc.sections, attr):
                sec = getattr(doc.sections, attr)
                if sec:
                    return sec.content or ""
    return ""


# --- Main Logic ----------------------------------------------------------------------

def pending_extraction_uids(store: StagingStore) -> list[str]:
    """Doc đủ điều kiện extract: ELIG_INCLUDED và chưa có extraction.

    Tiền điều kiện ELIG_INCLUDED là bắt buộc (bài học FL-1 2026-07-19: filter
    'queued' trần khiến batch gặm doc tồn chưa qua sàng từ các run cũ, và
    extract trên doc abstract-only sinh hàng loạt quote unverified vô ích).
    Cùng khuôn tiền-điều-kiện-theo-event với rob_run (ELIG_INCLUDED) và
    eligibility_run (SCREEN_INCLUDED).
    """
    rows = store.conn.execute(
        """SELECT uid FROM documents
           WHERE status = 'queued'
             AND uid IN (SELECT uid FROM events WHERE event_type = 'ELIG_INCLUDED')
             AND uid NOT IN (SELECT uid FROM extraction)"""
    ).fetchall()
    return [r["uid"] for r in rows]


def run_extraction_batch(store: StagingStore, limit: int, protocol = None) -> int:
    from sr_agent.parser.ollama_client import OllamaClient
    from tools.protocol_build import ReviewProtocol

    client = OllamaClient()
    if not client.is_available():
        logger.error("Ollama is not available. Cannot run evidence extraction.")
        return 0

    to_extract = pending_extraction_uids(store)

    if not to_extract:
        print("No documents require evidence extraction.")
        return 0

    # Determine extraction fields
    if protocol and getattr(protocol, "extraction_fields", None):
        fields = protocol.extraction_fields
    else:
        fields = LEGACY_EXTRACTION_FIELDS

    # Dynamic schema creation
    EvidencedExtraction = create_model(
        "EvidencedExtraction",
        **{f.id: (EvidencedField, ...) for f in fields}
    )

    # Dynamic prompt building
    fields_desc = []
    for i, f in enumerate(fields, 1):
        desc = f"{i}. {f.id}: {f.description_en}"
        if getattr(f, "value_hint", None):
            desc += f" (Hint: {f.value_hint})"
        fields_desc.append(desc)
    fields_str = "\n".join(fields_desc)

    system_prompt = (
        "You are an expert academic data extraction assistant. "
        f"Extract the following fields from the scientific article's sections:\n{fields_str}\n\n"
        "Instructions:\n"
        "- For each field, you must provide the 'value', the 'section' name (e.g. 'abstract', 'context', 'method', 'findings', 'implications'), "
        "and a verbatim 'quote' from that section supporting the value.\n"
        "- The quote must be EXACTLY word-for-word from the text. If the value is false or null and no quote is possible, output empty string for quote and section.\n"
        "- Output must strictly match the EvidencedExtraction JSON schema."
    )

    processed_count = 0
    for uid in to_extract[:limit]:
        doc = store.get(uid)
        if not doc:
            continue

        print(f"Extracting evidence: {uid} - {doc.title[:60]}")

        full_text_str = build_full_text_str(doc)

        try:
            extraction_data = client.generate_structured(
                system_prompt=system_prompt,
                user_prompt=full_text_str,
                schema_model=EvidencedExtraction
            )

            # Map fields to verify
            fields_map = {f.id: getattr(extraction_data, f.id) for f in fields}
            
            for field, data in fields_map.items():
                value = data.value
                quote = data.quote
                section = data.section
                
                verified = 0
                if quote:
                    section_text = get_section_text(doc, section)
                    if verify_quote(section_text, quote):
                        verified = 1
                        
                        # Value-anchor consistency check
                        if any(c.isdigit() for c in value):
                            val_anchors = extract_anchors(value)
                            q_anchors = extract_anchors(quote)
                            val_nums = {n for a in val_anchors for n in re.findall(r'\d+', a.raw)}
                            q_nums = {n for a in q_anchors for n in re.findall(r'\d+', a.raw)}
                            if not val_nums:
                                val_nums = set(re.findall(r'\d+', value))
                            if not q_nums:
                                q_nums = set(re.findall(r'\d+', quote))
                            if not val_nums.issubset(q_nums):
                                verified = 0
                                logger.warning(f"Value mismatch for {uid} field {field}. Numbers in value not in quote.")
                                store.log_event(uid, "EXTRACT_VALUE_MISMATCH", field)
                    else:
                        logger.warning(f"Verification failed for {uid} field {field}. Quote not in section {section}.")
                        store.log_event(uid, "EXTRACT_UNVERIFIED", field)
                else:
                    if not value or value.lower() in ("false", "null", "none", "[]", ""):
                        verified = 2
                    else:
                        verified = 0
                        
                store.add_extraction(uid, field, value, quote, section, verified)
                
            processed_count += 1
        except ContextOverflowError as exc:
            store.log_event(uid, "LLM_CONTEXT_OVERFLOW", f"stage=extract token_estimate={exc.token_estimate}")
            processed_count += 1
        except Exception as exc:
            logger.error(f"Error during extraction for {uid}: {exc}")
            
    return processed_count


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Evidence Extraction Runner")
    ap.add_argument("--limit", type=int, default=10, help="Giới hạn số lượng tài liệu xử lý")
    ap.add_argument("--db", type=Path, help="Override DB path (SQLite)")
    ap.add_argument("--protocol", type=Path, help="Đường dẫn file JSON review protocol")
    
    args = ap.parse_args(argv)
    
    protocol = None
    if args.protocol:
        if not args.protocol.exists():
            print(f"Lỗi: Không tìm thấy file protocol tại {args.protocol}", file=sys.stderr)
            return 1
        from tools.protocol_build import ReviewProtocol
        protocol = ReviewProtocol.model_validate_json(args.protocol.read_text(encoding="utf-8"))
        
    store_path = args.db if args.db else None
    with StagingStore(store_path) if store_path else StagingStore() as store:
        count = run_extraction_batch(store, args.limit, protocol=protocol)
        print(f"Đã hoàn thành trích xuất minh chứng cho {count} tài liệu.")
        
    return 0


if __name__ == "__main__":
    sys.exit(main())

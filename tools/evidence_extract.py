"""Evidence Extraction Tool (PRISMA exact-quote data extraction).

Extracts PICO fields with exact verbatim quotes and verifies them.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field

from sr_agent.config import OLLAMA_MODEL
from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from tools.screen_run import verify_quote

logger = logging.getLogger("tools.evidence_extract")


# --- Contracts (D3.2) ----------------------------------------------------------------

class EvidencedField(BaseModel):
    value: str
    quote: str          # trích VERBATIM từ văn bản nguồn
    section: str        # section id nơi quote nằm (title/abstract/context/method/...)


class EvidencedExtraction(BaseModel):
    has_code_repo: EvidencedField
    dataset_spec: EvidencedField
    baselines: EvidencedField
    metrics: EvidencedField


# --- Helper functions ----------------------------------------------------------------

def get_section_text(doc: Document, section_name: str) -> str:
    s_name = section_name.strip().lower()
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

def run_extraction_batch(store: StagingStore, limit: int) -> int:
    from sr_agent.parser.ollama_client import OllamaClient
    
    client = OllamaClient()
    if not client.is_available():
        logger.error("Ollama is not available. Cannot run evidence extraction.")
        return 0
        
    # Get all queued documents
    rows = store.conn.execute(
        "SELECT uid FROM documents WHERE status = 'queued'"
    ).fetchall()
    
    to_extract = []
    for r in rows:
        uid = r["uid"]
        # Check if already extracted
        has_ext = store.conn.execute(
            "SELECT 1 FROM extraction WHERE uid = ?", (uid,)
        ).fetchone()
        if not has_ext:
            to_extract.append(uid)
            
    if not to_extract:
        print("No documents require evidence extraction.")
        return 0
        
    processed_count = 0
    for uid in to_extract[:limit]:
        doc = store.get(uid)
        if not doc:
            continue
            
        print(f"Extracting evidence: {uid} - {doc.title[:60]}")
        
        # Compile full text or all sections
        full_text_context = []
        if doc.abstract:
            full_text_context.append(f"Section: abstract\n{doc.abstract}")
        for role, sec in doc.canonical_sections.items():
            if sec:
                full_text_context.append(f"Section: {role.value}\n{sec.content}")
                
        full_text_str = "\n\n".join(full_text_context)
        
        system_prompt = (
            "You are an expert academic data extraction assistant. "
            "Extract the following fields from the scientific article's sections:\n"
            "1. has_code_repo: Whether a code repository link is explicitly stated (True/False).\n"
            "2. dataset_spec: The size/specification of dataset used verbatim, else null.\n"
            "3. baselines: Verbatim list of baseline model names compared against, else null.\n"
            "4. metrics: Verbatim list of evaluation metrics used, else null.\n\n"
            "Instructions:\n"
            "- For each field, you must provide the 'value', the 'section' name (e.g. 'abstract', 'context', 'method', 'findings', 'implications'), "
            "and a verbatim 'quote' from that section supporting the value.\n"
            "- The quote must be EXACTLY word-for-word from the text. If the value is false or null and no quote is possible, output empty string for quote and section.\n"
            "- Output must strictly match the EvidencedExtraction JSON schema."
        )
        
        try:
            extraction_data = client.generate_structured(
                system_prompt=system_prompt,
                user_prompt=full_text_str,
                schema_model=EvidencedExtraction
            )
            
            # Map fields to verify
            fields_map = {
                "has_code_repo": extraction_data.has_code_repo,
                "dataset_spec": extraction_data.dataset_spec,
                "baselines": extraction_data.baselines,
                "metrics": extraction_data.metrics
            }
            
            for field, data in fields_map.items():
                value = data.value
                quote = data.quote
                section = data.section
                
                verified = 0
                if quote:
                    section_text = get_section_text(doc, section)
                    if verify_quote(section_text, quote):
                        verified = 1
                    else:
                        logger.warning(f"Verification failed for {uid} field {field}. Quote not in section {section}.")
                        store.log_event(uid, "EXTRACT_UNVERIFIED", field)
                else:
                    # No quote (e.g., false or null value), default to verified if value matches expected empty
                    if value.lower() in ("false", "null", "none", "[]", ""):
                        verified = 1
                        
                store.add_extraction(uid, field, value, quote, section, verified)
                
            processed_count += 1
        except Exception as exc:
            logger.error(f"Error during extraction for {uid}: {exc}")
            
    return processed_count


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Evidence Extraction Runner")
    ap.add_argument("--limit", type=int, default=10, help="Giới hạn số lượng tài liệu xử lý")
    ap.add_argument("--db", type=Path, help="Override DB path (SQLite)")
    
    args = ap.parse_args(argv)
    
    store_path = args.db if args.db else None
    with StagingStore(store_path) if store_path else StagingStore() as store:
        count = run_extraction_batch(store, args.limit)
        print(f"Đã hoàn thành trích xuất minh chứng cho {count} tài liệu.")
        
    return 0


if __name__ == "__main__":
    sys.exit(main())

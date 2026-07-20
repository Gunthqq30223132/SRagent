"""Eligibility Tool (PRISMA Full-Text Eligibility Agent).

Evaluates full-text articles for systematic review eligibility based on EF criteria.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sr_agent.config import OLLAMA_MODEL
from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from sr_agent.errors import TransientError, ContextOverflowError
import httpx

from tools.protocol_build import ReviewProtocol
from tools.screen_run import ScreenVerdict, verify_quote

logger = logging.getLogger("tools.eligibility_run")


# --- Prompts Builder ------------------------------------------------------------------

def build_eligibility_prompts(doc_title: str, full_text_str: str, protocol: ReviewProtocol, criteria: dict) -> tuple[str, str]:
    criteria_lines = []
    for cid in ["EF1", "EF2", "EF4"]:
        if cid in criteria:
            criteria_lines.append(f"- {cid}: {criteria[cid]['label_vi']} ({criteria[cid]['description_en']})")

    system_prompt = (
        "You are an academic eligibility agent conducting a systematic literature review. "
        "Your task is to decide whether a study should be INCLUDED or EXCLUDED based on its Full Text.\n\n"
        "Review Protocol:\n"
        f"- Target Population: {protocol.population.concept} (Synonyms: {', '.join(protocol.population.synonyms)})\n"
        f"- Target Intervention: {protocol.intervention.concept} (Synonyms: {', '.join(protocol.intervention.synonyms)})\n"
        f"- Allowed Languages: {', '.join(protocol.languages)}\n"
        f"- Year Range: {protocol.year_range if protocol.year_range else 'Any'}\n\n"
        "Exclusion Criteria:\n"
        + "\n".join(criteria_lines) + "\n\n"
        "Decision Rule (Burden of Proof is on Exclusion):\n"
        "1. Start with the assumption that the study should be INCLUDED.\n"
        "2. EXCLUDE only if you find clear, explicit evidence in the Full Text that one of the exclusion criteria applies.\n"
        "3. If you EXCLUDE, you must specify the EXACT 'criterion_id' (e.g. EF1, EF2, EF4) and a 'evidence_quote' that is a word-for-word verbatim quote from the text.\n"
        "4. If you INCLUDE, 'criterion_id' and 'evidence_quote' must be null/None.\n"
        "5. Output must strictly adhere to the ScreenVerdict JSON schema."
    )

    user_prompt = (
        f"Title: {doc_title}\n\n"
        f"Full Text / Sections:\n"
        f"{full_text_str}"
    )
    return system_prompt, user_prompt


# --- Helper functions ----------------------------------------------------------------

def has_full_text(doc: Document) -> bool:
    if doc.full_text and doc.full_text.strip():
        return True
    if doc.sections:
        for role, sec in doc.canonical_sections.items():
            if sec and sec.content and sec.content.strip():
                return True
    return False


def build_full_text_str(doc: Document) -> str:
    full_text_context = []
    if doc.abstract:
        full_text_context.append(f"Section: abstract\n{doc.abstract}")
    has_canonical = False
    for role, sec in doc.canonical_sections.items():
        if sec and sec.content:
            full_text_context.append(f"Section: {role.value}\n{sec.content}")
            has_canonical = True
    if not has_canonical and doc.full_text and doc.full_text.strip():
        full_text_context.append(f"Section: full_text\n{doc.full_text}")
    return "\n\n".join(full_text_context)


# --- Agent Invocation -----------------------------------------------------------------

def invoke_eligibility_agent(
    client, system_prompt: str, user_prompt: str, source_text: str, criteria: dict
) -> tuple[str, str | None, str | None, str]:
    try:
        verdict_data = client.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_model=ScreenVerdict
        )
        verdict = verdict_data.verdict
        criterion_id = verdict_data.criterion_id
        evidence_quote = verdict_data.evidence_quote
        confidence = verdict_data.confidence

        is_valid = True
        if verdict == "exclude":
            if not criterion_id or not evidence_quote:
                is_valid = False
            elif criterion_id not in ["EF1", "EF2", "EF4"]:
                is_valid = False
            elif criterion_id not in criteria:
                is_valid = False
            elif not verify_quote(source_text, evidence_quote):
                is_valid = False
        else:
            criterion_id = None
            evidence_quote = None

        if not is_valid:
            return "invalid", criterion_id, evidence_quote, confidence
        return verdict, criterion_id, evidence_quote, confidence
    except (TransientError, httpx.HTTPError, ContextOverflowError) as exc:
        raise exc
    except Exception as exc:
        logger.error(f"LLM generation failed: {exc}")
        return "invalid", None, None, "low"


# --- Batch Execution -----------------------------------------------------------------

def run_eligibility_batch(store: StagingStore, protocol: ReviewProtocol, criteria: dict, limit: int) -> int:
    from sr_agent.parser.ollama_client import OllamaClient

    # Input set: doc status='queued' CÓ event 'SCREEN_INCLUDED' và CHƯA có event 'ELIG_*'
    rows = store.conn.execute(
        """
        SELECT uid FROM documents
        WHERE status = 'queued'
          AND uid IN (SELECT uid FROM events WHERE event_type = 'SCREEN_INCLUDED')
          AND uid NOT IN (SELECT uid FROM events WHERE event_type LIKE 'ELIG_%')
        """
    ).fetchall()

    to_process = [row["uid"] for row in rows]
    if not to_process:
        print("No documents require eligibility screening.")
        return 0

    client = None
    processed_count = 0

    try:
        for uid in to_process[:limit]:
            doc = store.get(uid)
            if not doc:
                continue

            # Check if has full text
            if not has_full_text(doc):
                store.log_event(uid, "ELIG_ABSTRACT_ONLY", "No full text available")
                processed_count += 1
                continue

            # We need client only if we run LLM
            if client is None:
                client = OllamaClient()
                if not client.is_available():
                    logger.error("Ollama is not available. Cannot run eligibility screening.")
                    break

            full_text_str = build_full_text_str(doc)
            system_prompt, user_prompt = build_eligibility_prompts(doc.title, full_text_str, protocol, criteria)

            # Invoke agent and handle context overflow
            try:
                verdict, crit_id, quote, conf = invoke_eligibility_agent(client, system_prompt, user_prompt, full_text_str, criteria)

                # Record screening verdict
                store.add_screen_verdict(uid, "eligibility", client.model, verdict, crit_id, quote, conf)

                # Handle decisions
                if verdict == "exclude":
                    store.set_status(uid, DocStatus.REJECTED)
                    store.log_event(uid, "ELIG_EXCLUDED", crit_id)
                elif verdict == "include":
                    store.log_event(uid, "ELIG_INCLUDED", "LLM eligibility include")
                else:
                    # invalid
                    store.log_event(uid, "ELIG_ESCALATED", f"verdict=invalid, criterion={crit_id or ''}")
            except ContextOverflowError as exc:
                store.log_event(uid, "LLM_CONTEXT_OVERFLOW", f"stage=eligibility token_estimate={exc.token_estimate}")
                store.log_event(uid, "ELIG_ESCALATED", f"Context overflow error: {exc}")

            processed_count += 1

    except (TransientError, httpx.HTTPError) as exc:
        print(f"Transient error encountered during batch eligibility: {exc}")
        remaining = len(to_process[:limit]) - processed_count
        print(f"Processed: {processed_count}. Remaining: {remaining}.")

    return processed_count


# --- Main ----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Full-Text Eligibility Runner")
    ap.add_argument("--protocol", required=True, type=Path, help="Đường dẫn file protocol JSON")
    ap.add_argument("--limit", type=int, default=10, help="Giới hạn số lượng tài liệu xử lý")
    ap.add_argument("--db", type=Path, help="Override DB path (SQLite)")
    ap.add_argument("--criteria", type=Path, default=ROOT / "tools" / "criteria" / "default.json", help="Bộ tiêu chí loại trừ")

    args = ap.parse_args(argv)

    if not args.protocol.exists():
        print(f"Lỗi: Không tìm thấy protocol tại {args.protocol}", file=sys.stderr)
        return 1

    protocol = ReviewProtocol.model_validate_json(args.protocol.read_text(encoding="utf-8"))

    if not args.criteria.exists():
        print(f"Lỗi: Không tìm thấy criteria tại {args.criteria}", file=sys.stderr)
        return 1

    criteria = json.loads(args.criteria.read_text(encoding="utf-8"))

    store_path = args.db if args.db else None
    with StagingStore(store_path) if store_path else StagingStore() as store:
        count = run_eligibility_batch(store, protocol, criteria, args.limit)
        print(f"Đã hoàn thành eligibility cho {count} tài liệu.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Screening Tool (PRISMA Multi-Agent title/abstract screening).

Orchestrates agent-based screening for systematic reviews.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field

from sr_agent.config import OLLAMA_MODEL
from sr_agent.models.schemas import DocStatus
from sr_agent.store.staging import StagingStore
from tools.protocol_build import ReviewProtocol

logger = logging.getLogger("tools.screen_run")


# --- Contracts (D2) ------------------------------------------------------------------

class ScreenVerdict(BaseModel):
    verdict: Literal["include", "exclude"]
    criterion_id: str | None = None      # BẮT BUỘC khi exclude — một mã ET1..ET7
    evidence_quote: str | None = None    # BẮT BUỘC khi exclude — verbatim từ title/abstract
    confidence: Literal["high", "low"]


# --- Verifier (D5) -------------------------------------------------------------------

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.casefold()
    for char in "'‘’":
        text = text.replace(char, "'")
    for char in '"“”':
        text = text.replace(char, '"')
    for char in "–—":
        text = text.replace(char, "-")
    # Collapse multiple whitespaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def verify_quote(source_text: str, quote: str) -> bool:
    if not quote or not source_text:
        return False
    norm_source = normalize_text(source_text)
    norm_quote = normalize_text(quote)
    return norm_quote in norm_source


# --- Cohen's Kappa (D4) --------------------------------------------------------------

def compute_cohen_kappa(verdicts: list[tuple[str, str]]) -> float | None:
    valid_verdicts = [(a, b) for a, b in verdicts if a in ("include", "exclude") and b in ("include", "exclude")]
    N = len(valid_verdicts)
    if N < 2:
        return None
    
    n_11 = sum(1 for a, b in valid_verdicts if a == "include" and b == "include")
    n_12 = sum(1 for a, b in valid_verdicts if a == "include" and b == "exclude")
    n_21 = sum(1 for a, b in valid_verdicts if a == "exclude" and b == "include")
    n_22 = sum(1 for a, b in valid_verdicts if a == "exclude" and b == "exclude")
    
    p_o = (n_11 + n_22) / N
    p_inc_a = (n_11 + n_12) / N
    p_inc_b = (n_11 + n_21) / N
    p_exc_a = (n_21 + n_22) / N
    p_exc_b = (n_12 + n_22) / N
    
    p_e = p_inc_a * p_inc_b + p_exc_a * p_exc_b
    if abs(1.0 - p_e) < 1e-9:
        return 1.0 if p_o == 1.0 else 0.0
    return (p_o - p_e) / (1.0 - p_e)


# --- Prompt Builders ------------------------------------------------------------------

def build_screener_a_prompts(doc_title: str, doc_abstract: str, protocol: ReviewProtocol, criteria: dict) -> tuple[str, str]:
    # Thiên-giữ prompt context (burden of proof on exclusion)
    criteria_lines = []
    for cid in protocol.exclusion_criteria:
        if cid in criteria:
            criteria_lines.append(f"- {cid}: {criteria[cid]['label_vi']} ({criteria[cid]['description_en']})")
            
    system_prompt = (
        "You are an academic screening agent (screener_a) conducting a systematic literature review. "
        "Your task is to decide whether a study should be INCLUDED or EXCLUDED based on its Title and Abstract. "
        "Review Protocol:\n"
        f"- Target Population: {protocol.population.concept} (Synonyms: {', '.join(protocol.population.synonyms)})\n"
        f"- Target Intervention: {protocol.intervention.concept} (Synonyms: {', '.join(protocol.intervention.synonyms)})\n"
        f"- Allowed Languages: {', '.join(protocol.languages)}\n"
        f"- Year Range: {protocol.year_range if protocol.year_range else 'Any'}\n\n"
        "Exclusion Criteria:\n"
        + "\n".join(criteria_lines) + "\n\n"
        "Decision Rule (Burden of Proof is on Exclusion):\n"
        "1. Start with the assumption that the study should be INCLUDED.\n"
        "2. EXCLUDE only if you find clear, explicit evidence in the Title/Abstract that one of the exclusion criteria applies.\n"
        "3. If you EXCLUDE, you must specify the EXACT 'criterion_id' (e.g. ET1) and a 'evidence_quote' that is a word-for-word verbatim quote from the text.\n"
        "4. If you INCLUDE, 'criterion_id' and 'evidence_quote' must be null/None.\n"
        "5. Output must strictly adhere to the ScreenVerdict JSON schema."
    )
    
    user_prompt = (
        f"Title: {doc_title}\n"
        f"Abstract: {doc_abstract}"
    )
    return system_prompt, user_prompt


def build_screener_b_prompts(doc_title: str, doc_abstract: str, protocol: ReviewProtocol, criteria: dict) -> tuple[str, str]:
    # Thiên-loại prompt context (checklist-based)
    criteria_lines = []
    for cid in protocol.exclusion_criteria:
        if cid in criteria:
            criteria_lines.append(f"- {cid}: {criteria[cid]['label_vi']} ({criteria[cid]['description_en']})")
            
    system_prompt = (
        "You are an academic screening agent (screener_b) conducting a systematic literature review. "
        "Your task is to decide whether a study should be INCLUDED or EXCLUDED by checking each exclusion criterion sequentially. "
        "Review Protocol:\n"
        f"- Target Population: {protocol.population.concept} (Synonyms: {', '.join(protocol.population.synonyms)})\n"
        f"- Target Intervention: {protocol.intervention.concept} (Synonyms: {', '.join(protocol.intervention.synonyms)})\n"
        f"- Allowed Languages: {', '.join(protocol.languages)}\n"
        f"- Year Range: {protocol.year_range if protocol.year_range else 'Any'}\n\n"
        "Exclusion Criteria Checklist:\n"
        + "\n".join(criteria_lines) + "\n\n"
        "Decision Checklist (Burden of Proof is on Exclusion Checklist):\n"
        "Check each exclusion criterion in the checklist against the Title and Abstract:\n"
        "1. Does ET1 apply? If yes, exclude immediately and quote evidence.\n"
        "2. Does ET2 apply? If yes, exclude immediately and quote evidence.\n"
        "3. Repeat for all criteria.\n"
        "4. If and only if NONE of the exclusion criteria apply, you must output INCLUDE.\n"
        "5. If you EXCLUDE, you must specify the EXACT 'criterion_id' and a verbatim 'evidence_quote'.\n"
        "6. Output must strictly adhere to the ScreenVerdict JSON schema."
    )
    
    user_prompt = (
        f"Title: {doc_title}\n"
        f"Abstract: {doc_abstract}"
    )
    return system_prompt, user_prompt


def build_tiebreaker_prompts(doc_title: str, doc_abstract: str, protocol: ReviewProtocol, criteria: dict,
                             v1_desc: str, v2_desc: str) -> tuple[str, str]:
    criteria_lines = []
    for cid in protocol.exclusion_criteria:
        if cid in criteria:
            criteria_lines.append(f"- {cid}: {criteria[cid]['label_vi']} ({criteria[cid]['description_en']})")
            
    system_prompt = (
        "You are a senior referee (tiebreaker) for a systematic literature review. "
        "Two screeners have reviewed a study against the protocol but reached different conclusions. "
        "Your task is to resolve their disagreement and make a final recommendation (INCLUDE or EXCLUDE).\n\n"
        "Review Protocol:\n"
        f"- Target Population: {protocol.population.concept} (Synonyms: {', '.join(protocol.population.synonyms)})\n"
        f"- Target Intervention: {protocol.intervention.concept} (Synonyms: {', '.join(protocol.intervention.synonyms)})\n\n"
        "Exclusion Criteria:\n"
        + "\n".join(criteria_lines) + "\n\n"
        "Anonymized Screener Feedback:\n"
        f"- Screener 1: {v1_desc}\n"
        f"- Screener 2: {v2_desc}\n\n"
        "Instructions:\n"
        "1. Review the Title and Abstract carefully.\n"
        "2. Make the final decision. If you choose to EXCLUDE, you must provide a valid 'criterion_id' and verbatim 'evidence_quote' from the text.\n"
        "3. If the decision is highly ambiguous and you cannot be certain, you may set 'confidence' to 'low'. Otherwise set 'confidence' to 'high'.\n"
        "4. Output must strictly match the ScreenVerdict JSON schema."
    )
    
    user_prompt = (
        f"Title: {doc_title}\n"
        f"Abstract: {doc_abstract}"
    )
    return system_prompt, user_prompt


# --- Agent Invoker Helpers -------------------------------------------------------------

def invoke_screener_agent(client, system_prompt: str, user_prompt: str, source_text: str, protocol: ReviewProtocol) -> tuple[str, str | None, str | None, str]:
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
            elif criterion_id not in protocol.exclusion_criteria:
                is_valid = False
            elif not verify_quote(source_text, evidence_quote):
                is_valid = False
        else:
            criterion_id = None
            evidence_quote = None
            
        if not is_valid:
            return "invalid", criterion_id, evidence_quote, confidence
        return verdict, criterion_id, evidence_quote, confidence
    except Exception as exc:
        logger.error(f"LLM generation failed: {exc}")
        return "invalid", None, None, "low"


def run_screening_a(store: StagingStore, protocol: ReviewProtocol, criteria: dict, limit: int) -> int:
    from sr_agent.parser.ollama_client import OllamaClient
    
    client = OllamaClient()
    if not client.is_available():
        logger.error("Ollama is not available. Cannot run LLM screening.")
        return 0
        
    rows = store.conn.execute(
        "SELECT uid, payload FROM documents WHERE status = 'queued'"
    ).fetchall()
    
    to_screen = []
    for r in rows:
        uid = r["uid"]
        has_verdict = store.conn.execute(
            "SELECT 1 FROM screening WHERE uid = ? AND agent = 'screener_a'", (uid,)
        ).fetchone()
        if not has_verdict:
            to_screen.append(uid)
            
    if not to_screen:
        print("No documents require screening.")
        return 0
        
    screened_count = 0
    for uid in to_screen[:limit]:
        doc = store.get(uid)
        if not doc:
            continue
            
        source_text = f"{doc.title}\n{doc.abstract or ''}"
        system_prompt, user_prompt = build_screener_a_prompts(
            doc.title, doc.abstract or "", protocol, criteria
        )
        
        verdict, crit_id, quote, conf = invoke_screener_agent(client, system_prompt, user_prompt, source_text, protocol)
        store.add_screen_verdict(uid, "screener_a", OLLAMA_MODEL, verdict, crit_id, quote, conf)
        store.log_event(uid, "SCREENED", f"agent=screener_a, verdict={verdict}, criterion={crit_id or ''}")
        screened_count += 1
    return screened_count


# --- Main Logic ----------------------------------------------------------------------

def run_screening_batch(store: StagingStore, protocol: ReviewProtocol, criteria: dict, limit: int) -> dict:
    from sr_agent.parser.ollama_client import OllamaClient
    
    model_a = OLLAMA_MODEL
    model_b = os.getenv("SR_SCREEN_MODEL_B", "gemma3:4b")
    
    client_a = OllamaClient(model=model_a)
    client_b = OllamaClient(model=model_b)
    
    if not client_a.is_available():
        logger.error("Ollama is not available. Cannot run multi-agent screening.")
        return {"processed": 0, "kappa": None}
        
    # Get queued documents
    rows = store.conn.execute(
        "SELECT uid, payload FROM documents WHERE status = 'queued'"
    ).fetchall()
    
    to_screen = []
    for r in rows:
        uid = r["uid"]
        # Check if consensus has been reached (i.e. status is no longer queued or we have events showing it is processed)
        # Actually, if a doc is rejected, it is not queued anymore.
        # But if it is queued, we check if it has a final consensus verdict.
        # A doc is fully processed if either:
        # - it has SCREEN_EXCLUDED, SCREEN_INCLUDED, or SCREEN_ESCALATED event.
        has_consensus = store.conn.execute(
            "SELECT 1 FROM events WHERE uid = ? AND event_type IN ('SCREEN_EXCLUDED', 'SCREEN_INCLUDED', 'SCREEN_ESCALATED')",
            (uid,)
        ).fetchone()
        if not has_consensus:
            to_screen.append(uid)
            
    if not to_screen:
        print("No documents require screening.")
        # Still compute kappa on existing data
        all_verdicts = store.conn.execute(
            """SELECT uid, agent, verdict FROM screening 
               WHERE agent IN ('screener_a', 'screener_b') AND verdict IN ('include', 'exclude')"""
        ).fetchall()
        grouped = {}
        for r in all_verdicts:
            grouped.setdefault(r["uid"], {})[r["agent"]] = r["verdict"]
        pairs = [(grouped[u]["screener_a"], grouped[u]["screener_b"]) for u in grouped if "screener_a" in grouped[u] and "screener_b" in grouped[u]]
        return {"processed": 0, "kappa": compute_cohen_kappa(pairs)}
        
    screened_count = 0
    for uid in to_screen[:limit]:
        doc = store.get(uid)
        if not doc:
            continue
            
        print(f"Screening: {uid} - {doc.title[:60]}")
        source_text = f"{doc.title}\n{doc.abstract or ''}"
        
        # 1. Run Screener A
        verdict_a_row = store.conn.execute(
            "SELECT verdict, criterion_id, evidence_quote, confidence FROM screening WHERE uid = ? AND agent = 'screener_a'",
            (uid,)
        ).fetchone()
        
        if verdict_a_row:
            verdict_a = verdict_a_row["verdict"]
            crit_a = verdict_a_row["criterion_id"]
            quote_a = verdict_a_row["evidence_quote"]
            conf_a = verdict_a_row["confidence"]
        else:
            sys_a, usr_a = build_screener_a_prompts(doc.title, doc.abstract or "", protocol, criteria)
            verdict_a, crit_a, quote_a, conf_a = invoke_screener_agent(client_a, sys_a, usr_a, source_text, protocol)
            store.add_screen_verdict(uid, "screener_a", model_a, verdict_a, crit_a, quote_a, conf_a)
            store.log_event(uid, "SCREENED", f"agent=screener_a, verdict={verdict_a}, criterion={crit_a or ''}")
            
        # 2. Run Screener B
        verdict_b_row = store.conn.execute(
            "SELECT verdict, criterion_id, evidence_quote, confidence FROM screening WHERE uid = ? AND agent = 'screener_b'",
            (uid,)
        ).fetchone()
        
        if verdict_b_row:
            verdict_b = verdict_b_row["verdict"]
            crit_b = verdict_b_row["criterion_id"]
            quote_b = verdict_b_row["evidence_quote"]
            conf_b = verdict_b_row["confidence"]
        else:
            sys_b, usr_b = build_screener_b_prompts(doc.title, doc.abstract or "", protocol, criteria)
            # Screener B might use a different model, check if available or fallback to client_a
            # Since client_b model might not be pulled, client_b.is_available() checks tags.
            # If client_b model is not available in local ollama tags, it falls back to model_a
            active_client_b = client_b if client_b.model in client_a.list_models() else client_a
            verdict_b, crit_b, quote_b, conf_b = invoke_screener_agent(active_client_b, sys_b, usr_b, source_text, protocol)
            store.add_screen_verdict(uid, "screener_b", active_client_b.model, verdict_b, crit_b, quote_b, conf_b)
            store.log_event(uid, "SCREENED", f"agent=screener_b, verdict={verdict_b}, criterion={crit_b or ''}")

        # 3. Consensus & Tie-breaker
        if verdict_a == "invalid" or verdict_b == "invalid":
            # Direct tie-breaker due to invalid verdict
            v1_desc = f"Verdict: {verdict_a} (Criterion: {crit_a}, Quote: {quote_a})"
            v2_desc = f"Verdict: {verdict_b} (Criterion: {crit_b}, Quote: {quote_b})"
            run_tiebreaker_flow(store, client_a, uid, doc, protocol, criteria, v1_desc, v2_desc)
        elif verdict_a == verdict_b:
            if verdict_a == "exclude":
                store.set_status(uid, DocStatus.REJECTED)
                store.log_event(uid, "SCREEN_EXCLUDED", f"Consensus exclude. screener_a={crit_a}, screener_b={crit_b}")
            else:
                store.log_event(uid, "SCREEN_INCLUDED", "Consensus include.")
        else:
            # Disagreement!
            v1_desc = f"Verdict: {verdict_a} (Criterion: {crit_a}, Quote: {quote_a})"
            v2_desc = f"Verdict: {verdict_b} (Criterion: {crit_b}, Quote: {quote_b})"
            run_tiebreaker_flow(store, client_a, uid, doc, protocol, criteria, v1_desc, v2_desc)
            
        screened_count += 1

    # Calculate Kappa
    all_verdicts = store.conn.execute(
        """SELECT uid, agent, verdict FROM screening 
           WHERE agent IN ('screener_a', 'screener_b') AND verdict IN ('include', 'exclude')"""
    ).fetchall()
    grouped = {}
    for r in all_verdicts:
        grouped.setdefault(r["uid"], {})[r["agent"]] = r["verdict"]
    pairs = [(grouped[u]["screener_a"], grouped[u]["screener_b"]) for u in grouped if "screener_a" in grouped[u] and "screener_b" in grouped[u]]
    kappa = compute_cohen_kappa(pairs)
    
    return {"processed": screened_count, "kappa": kappa}


def run_tiebreaker_flow(store: StagingStore, client, uid: str, doc, protocol: ReviewProtocol, criteria: dict, v1_desc: str, v2_desc: str):
    source_text = f"{doc.title}\n{doc.abstract or ''}"
    sys_tb, usr_tb = build_tiebreaker_prompts(doc.title, doc.abstract or "", protocol, criteria, v1_desc, v2_desc)
    
    verdict_tb, crit_tb, quote_tb, conf_tb = invoke_screener_agent(client, sys_tb, usr_tb, source_text, protocol)
    store.add_screen_verdict(uid, "tiebreaker", client.model, verdict_tb, crit_tb, quote_tb, conf_tb)
    store.log_event(uid, "SCREENED", f"agent=tiebreaker, verdict={verdict_tb}, criterion={crit_tb or ''}")
    
    if verdict_tb == "invalid" or conf_tb == "low":
        # Escalate to human
        store.log_event(uid, "SCREEN_ESCALATED", f"Tiebreaker low-confidence or invalid. tb_verdict={verdict_tb}")
    else:
        # High confidence resolved
        if verdict_tb == "exclude":
            store.set_status(uid, DocStatus.REJECTED)
            store.log_event(uid, "SCREEN_EXCLUDED", f"Tiebreaker resolved to exclude. criterion={crit_tb}")
        else:
            store.log_event(uid, "SCREEN_INCLUDED", "Tiebreaker resolved to include.")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Multi-Agent Screening Runner")
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
        res = run_screening_batch(store, protocol, criteria, args.limit)
        print(f"Đã hoàn thành screening cho {res['processed']} tài liệu.")
        if res['kappa'] is not None:
            print(f"Cohen's Kappa (κ) của hệ thống: {res['kappa']:.4f}")
        else:
            print("Chưa đủ dữ liệu để tính Cohen's Kappa.")
        
    return 0


if __name__ == "__main__":
    sys.exit(main())

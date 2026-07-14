"""Risk-of-Bias Assessment Agent (RoB2 + MINORS).

Evaluates systematic review documents for risk of bias using Cochrane RoB2 and MINORS criteria.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional, Dict, Any, List, Tuple

from pydantic import BaseModel, Field
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sr_agent.config import OLLAMA_MODEL
from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from sr_agent.errors import TransientError, SchemaValidationError
from sr_agent.parser.ollama_client import OllamaClient
from tools.screen_run import verify_quote
from tools.eligibility_run import has_full_text, build_full_text_str

logger = logging.getLogger("tools.rob_run")

SR_SCREEN_MODEL_A = os.getenv("SR_SCREEN_MODEL_A", "llama3.1:8b")
SR_SCREEN_MODEL_B = os.getenv("SR_SCREEN_MODEL_B", "gemma4:e4b")


# --- Structured Output Schemas --------------------------------------------------------

class StudyTypeClassification(BaseModel):
    study_type: Literal["RCT", "Non-RCT"] = Field(
        description="RCT if randomized controlled trial, Non-RCT if observational or non-randomized study."
    )
    evidence_quote: str = Field(
        description="A direct word-for-word quote from the text supporting this classification."
    )


class RoB2DomainAssessment(BaseModel):
    verdict: Literal["Low", "Some concerns", "High"] = Field(
        description="Verdict for this domain. Choose Low, Some concerns, or High."
    )
    evidence_quote: str = Field(
        description="A direct word-for-word quote from the text supporting this verdict."
    )


class RoB2LLMResponse(BaseModel):
    study_type: Literal["RCT", "Non-RCT"] = Field(
        description="Must be RCT to use RoB2 schema"
    )
    d1_randomization: RoB2DomainAssessment = Field(
        description="Bias arising from the randomization process"
    )
    d2_deviations: RoB2DomainAssessment = Field(
        description="Bias due to deviations from intended interventions"
    )
    d3_missing_outcome: RoB2DomainAssessment = Field(
        description="Bias due to missing outcome data"
    )
    d4_measurement: RoB2DomainAssessment = Field(
        description="Bias in measurement of the outcome"
    )
    d5_selection: RoB2DomainAssessment = Field(
        description="Bias in selection of the reported result"
    )


class MinorsItemAssessment(BaseModel):
    score: Literal[0, 1, 2] = Field(
        description="Score: 0 for not reported; 1 for reported but inadequate; 2 for reported and adequate."
    )
    evidence_quote: str = Field(
        description="A direct word-for-word quote from the text supporting this score."
    )


class MinorsLLMResponse(BaseModel):
    study_type: Literal["RCT", "Non-RCT"] = Field(
        description="Must be Non-RCT to use MINORS schema"
    )
    has_control_group: bool = Field(
        description="True if there is a control group (comparative study), False if non-comparative (single-arm)."
    )
    item1_aim: MinorsItemAssessment = Field(
        description="1. A clearly stated aim"
    )
    item2_patients: MinorsItemAssessment = Field(
        description="2. Inclusion of consecutive patients"
    )
    item3_prospective: MinorsItemAssessment = Field(
        description="3. Prospective collection of data"
    )
    item4_endpoints: MinorsItemAssessment = Field(
        description="4. Endpoints appropriate to the aim of the study"
    )
    item5_unbiased: MinorsItemAssessment = Field(
        description="5. Unbiased assessment of the study endpoints"
    )
    item6_followup: MinorsItemAssessment = Field(
        description="6. Follow-up period appropriate to the aim of the study"
    )
    item7_loss: MinorsItemAssessment = Field(
        description="7. Loss to follow-up less than 5%"
    )
    item8_size: MinorsItemAssessment = Field(
        description="8. Prospective calculation of the study size"
    )
    # Comparative domains (optional, default to None)
    item9_control: Optional[MinorsItemAssessment] = Field(
        default=None, description="9. An adequate control group (required if comparative)"
    )
    item10_contemporary: Optional[MinorsItemAssessment] = Field(
        default=None, description="10. Contemporary groups (required if comparative)"
    )
    item11_equivalence: Optional[MinorsItemAssessment] = Field(
        default=None, description="11. Baseline equivalence of groups (required if comparative)"
    )
    item12_statistics: Optional[MinorsItemAssessment] = Field(
        default=None, description="12. Adequate statistical analyses (required if comparative)"
    )


MINORS_ITEM_FIELDS = {
    "item1": "item1_aim",
    "item2": "item2_patients",
    "item3": "item3_prospective",
    "item4": "item4_endpoints",
    "item5": "item5_unbiased",
    "item6": "item6_followup",
    "item7": "item7_loss",
    "item8": "item8_size",
    "item9": "item9_control",
    "item10": "item10_contemporary",
    "item11": "item11_equivalence",
    "item12": "item12_statistics",
}


# --- Pure Functions (All Algorithm Logic) ---------------------------------------------

def compute_rob2_overall(d1: str, d2: str, d3: str, d4: str, d5: str, rule: str = "rob2_standard") -> str:
    """Pure function to determine overall Cochrane RoB2 verdict.
    - VOID: If any domain is VOID.
    - High: If at least one domain is High.
    - Some concerns: Otherwise (i.e. no High/VOID, and at least one Some concerns).
    - Low: If all 5 domains are Low.
    """
    domains = [d1, d2, d3, d4, d5]
    if "VOID" in domains:
        return "VOID"
    if rule == "rob2_standard":
        if "High" in domains:
            return "High"
        if "Some concerns" in domains:
            return "Some concerns"
        return "Low"
    return "Low"


def compute_minors_overall(scores: Dict[str, str | int]) -> str:
    """Pure function to calculate total score of MINORS items. Returns "VOID" if any item is VOID."""
    if any(s == "VOID" for s in scores.values()):
        return "VOID"
    return str(sum(int(s) for s in scores.values()))


def compute_agreement_stats(ratings_a: List[str], ratings_b: List[str]) -> Tuple[float, float, List[int]]:
    """Computes percentage agreement, Cohen's Kappa, and a list of mismatched indices."""
    n = len(ratings_a)
    if n == 0:
        return 1.0, 1.0, []
    agree_count = sum(1 for a, b in zip(ratings_a, ratings_b) if a == b)
    po = agree_count / n
    
    categories = sorted(list(set(ratings_a + ratings_b)))
    pe = 0.0
    for cat in categories:
        pa = ratings_a.count(cat) / n
        pb = ratings_b.count(cat) / n
        pe += pa * pb
    
    if pe >= 1.0:
        kappa = 1.0 if po == 1.0 else 0.0
    else:
        kappa = (po - pe) / (1.0 - pe)
    
    mismatches = [i for i, (a, b) in enumerate(zip(ratings_a, ratings_b)) if a != b]
    return po, kappa, mismatches


# --- Prompts Builder ------------------------------------------------------------------

def build_classification_prompts(doc_title: str, text: str) -> tuple[str, str]:
    system_prompt = (
        "You are an academic screening expert. Your task is to classify the study type as either "
        "'RCT' (Randomized Controlled Trial) or 'Non-RCT' (observational study, cohort, case-control, "
        "or non-randomized trial).\n\n"
        "You must output a 'study_type' ('RCT' or 'Non-RCT') and a mandatory 'evidence_quote' "
        "which is a word-for-word verbatim quote from the text supporting your classification.\n\n"
        "Output must strictly adhere to the StudyTypeClassification JSON schema."
    )
    user_prompt = f"Title: {doc_title}\n\nText:\n{text[:8000]}"
    return system_prompt, user_prompt


def build_rob2_prompts(doc_title: str, text: str) -> tuple[str, str]:
    system_prompt = (
        "You are an academic clinical trial auditor. Your task is to perform a Risk of Bias (RoB2) assessment "
        "for a Randomized Controlled Trial (RCT) based on Cochrane guidelines. Assess the following 5 domains:\n"
        "- d1_randomization: Bias arising from the randomization process\n"
        "- d2_deviations: Bias due to deviations from intended interventions\n"
        "- d3_missing_outcome: Bias due to missing outcome data\n"
        "- d4_measurement: Bias in measurement of the outcome\n"
        "- d5_selection: Bias in selection of the reported result\n\n"
        "For each domain, you must output a 'verdict' ('Low', 'Some concerns', or 'High') and a mandatory "
        "'evidence_quote' which is a word-for-word verbatim quote from the text supporting your verdict.\n"
        "Decision rule (Burden of proof on Low bias): Do not default to 'Low'. If there is insufficient "
        "evidence, choose 'Some concerns' or 'High'.\n"
        "Output must strictly adhere to the RoB2LLMResponse JSON schema."
    )
    user_prompt = f"Title: {doc_title}\n\nText:\n{text}"
    return system_prompt, user_prompt


def build_minors_prompts(doc_title: str, text: str) -> tuple[str, str]:
    system_prompt = (
        "You are an academic clinical study auditor. Your task is to perform a MINORS (Methodological Index "
        "for Non-Randomized Studies) assessment. First determine if there is a control group ('has_control_group').\n"
        "For each item, output a 'score' (0 for not reported; 1 for reported but inadequate; 2 for reported and adequate) "
        "and a mandatory 'evidence_quote' which is a word-for-word verbatim quote from the text.\n"
        "MINORS Items:\n"
        "1. A clearly stated aim (item1_aim)\n"
        "2. Inclusion of consecutive patients (item2_patients)\n"
        "3. Prospective collection of data (item3_prospective)\n"
        "4. Endpoints appropriate to the aim of the study (item4_endpoints)\n"
        "5. Unbiased assessment of the study endpoints (item5_unbiased)\n"
        "6. Follow-up period appropriate to the aim of the study (item6_followup)\n"
        "7. Loss to follow-up less than 5% (item7_loss)\n"
        "8. Prospective calculation of the study size (item8_size)\n\n"
        "If 'has_control_group' is True, you must also assess:\n"
        "9. An adequate control group (item9_control)\n"
        "10. Contemporary groups (item10_contemporary)\n"
        "11. Baseline equivalence of groups (item11_equivalence)\n"
        "12. Adequate statistical analyses (item12_statistics)\n\n"
        "Decision rule: If there is no proof or verbatim quote, score must be 0.\n"
        "Output must strictly adhere to the MinorsLLMResponse JSON schema."
    )
    user_prompt = f"Title: {doc_title}\n\nText:\n{text}"
    return system_prompt, user_prompt


# --- Ingestion & Batch Runner ---------------------------------------------------------

def run_rob_batch(store: StagingStore, protocol: Any, limit: int) -> int:
    # 1. Fetch input set: status='queued', ELIG_INCLUDED event, no active ROB_COMPLETED or ROB_ESCALATED events
    rows = store.conn.execute(
        """
        SELECT uid FROM documents
        WHERE status = 'queued'
          AND uid IN (SELECT uid FROM events WHERE event_type = 'ELIG_INCLUDED')
          AND uid NOT IN (SELECT uid FROM events WHERE event_type IN ('ROB_COMPLETED', 'ROB_ESCALATED'))
        """
    ).fetchall()

    to_process = [row["uid"] for row in rows]
    if not to_process:
        print("No documents require risk-of-bias assessment.")
        return 0

    processed_count = 0
    client_a = OllamaClient(model=SR_SCREEN_MODEL_A)
    client_b = OllamaClient(model=SR_SCREEN_MODEL_B)

    if not client_a.is_available() or not client_b.is_available():
        logger.error("One or both Ollama models are unavailable. Cannot run RoB assessment.")
        return 0

    # Read config from protocol dynamically
    overall_rule = getattr(protocol, "overall_rule", "rob2_standard")
    minors_threshold = getattr(protocol, "minors_threshold", None)

    for uid in to_process[:limit]:
        doc = store.get(uid)
        if not doc:
            continue

        if not has_full_text(doc):
            store.log_event(uid, "ROB_SKIPPED_NO_FULLTEXT", "Missing full-text or canonical sections")
            processed_count += 1
            continue

        # Idempotency: clear previous rob_assessment rows for this document
        store.conn.execute(
            "DELETE FROM rob_assessment WHERE uid = ? AND agent IN ('rob_a', 'rob_b')",
            (uid,)
        )
        store.conn.commit()

        full_text_str = build_full_text_str(doc)
        
        try:
            # Step 1: Classify Study Type
            sys_cls, user_cls = build_classification_prompts(doc.title, full_text_str)
            try:
                cls_a = client_a.generate_structured(sys_cls, user_cls, StudyTypeClassification)
                cls_b = client_b.generate_structured(sys_cls, user_cls, StudyTypeClassification)
            except SchemaValidationError as e:
                store.log_event(uid, "ROB_ESCALATED", f"Classification schema error: {e}")
                processed_count += 1
                continue

            # Verify study classification quotes
            if not cls_a.evidence_quote or not verify_quote(full_text_str, cls_a.evidence_quote):
                study_type_a = "VOID"
            else:
                study_type_a = cls_a.study_type

            if not cls_b.evidence_quote or not verify_quote(full_text_str, cls_b.evidence_quote):
                study_type_b = "VOID"
            else:
                study_type_b = cls_b.study_type

            if study_type_a == "VOID" or study_type_b == "VOID" or study_type_a != study_type_b:
                store.log_event(uid, "ROB_ESCALATED", f"Study type mismatch or VOID: A={study_type_a}, B={study_type_b}")
                processed_count += 1
                continue

            study_type = study_type_a

            # Step 2: Assessment based on Study Type
            if study_type == "RCT":
                sys_eval, user_eval = build_rob2_prompts(doc.title, full_text_str)
                try:
                    res_a = client_a.generate_structured(sys_eval, user_eval, RoB2LLMResponse)
                    res_b = client_b.generate_structured(sys_eval, user_eval, RoB2LLMResponse)
                except SchemaValidationError as e:
                    store.log_event(uid, "ROB_ESCALATED", f"RoB2 schema error: {e}")
                    processed_count += 1
                    continue

                domains_a = {}
                domains_b = {}
                domain_list = ["d1_randomization", "d2_deviations", "d3_missing_outcome", "d4_measurement", "d5_selection"]

                for domain_name in domain_list:
                    da = getattr(res_a, domain_name)
                    db = getattr(res_b, domain_name)

                    # Model A check
                    if not da.evidence_quote or not verify_quote(full_text_str, da.evidence_quote):
                        domains_a[domain_name] = ("VOID", da.evidence_quote)
                    else:
                        domains_a[domain_name] = (da.verdict, da.evidence_quote)

                    # Model B check
                    if not db.evidence_quote or not verify_quote(full_text_str, db.evidence_quote):
                        domains_b[domain_name] = ("VOID", db.evidence_quote)
                    else:
                        domains_b[domain_name] = (db.verdict, db.evidence_quote)

                # Compute overall verdicts
                overall_a = compute_rob2_overall(*(v[0] for v in domains_a.values()), rule=overall_rule)
                overall_b = compute_rob2_overall(*(v[0] for v in domains_b.values()), rule=overall_rule)

                # Save all domain results and overall rows to database
                for domain_name, (verdict, quote) in domains_a.items():
                    store.add_rob_assessment(uid, "rob_a", client_a.model, "RCT", domain_name, verdict, quote)
                store.add_rob_assessment(uid, "rob_a", client_a.model, "RCT", "__overall__", overall_a, None)

                for domain_name, (verdict, quote) in domains_b.items():
                    store.add_rob_assessment(uid, "rob_b", client_b.model, "RCT", domain_name, verdict, quote)
                store.add_rob_assessment(uid, "rob_b", client_b.model, "RCT", "__overall__", overall_b, None)

                # Calculate agreement stats (excluding overall)
                list_a = [domains_a[d][0] for d in domain_list]
                list_b = [domains_b[d][0] for d in domain_list]
                po, kappa, mismatches_idx = compute_agreement_stats(list_a, list_b)
                mismatched_domains = [domain_list[i] for i in mismatches_idx]

                # Check consensus
                has_void = "VOID" in list_a or "VOID" in list_b
                has_mismatch = len(mismatched_domains) > 0

                if has_void or has_mismatch:
                    store.log_event(
                        uid,
                        "ROB_ESCALATED",
                        f"RCT domain level conflict/VOID. Stats: agreement={po:.1%}, kappa={kappa:.3f}. Mismatches: {mismatched_domains}"
                    )
                else:
                    store.log_event(
                        uid,
                        "ROB_COMPLETED",
                        f"RCT consensus verdict: {overall_a}. Stats: agreement={po:.1%}, kappa={kappa:.3f}"
                    )
                    # ROB_OVERALL_REVIEW check
                    some_concerns_count = sum(1 for v in list_a if v == "Some concerns")
                    if overall_a == "Some concerns" and some_concerns_count >= 2:
                        store.log_event(
                            uid,
                            "ROB_OVERALL_REVIEW",
                            f"Overall 'Some concerns' with {some_concerns_count} domains having Some concerns."
                        )

            else:  # Non-RCT (MINORS)
                sys_eval, user_eval = build_minors_prompts(doc.title, full_text_str)
                try:
                    res_a = client_a.generate_structured(sys_eval, user_eval, MinorsLLMResponse)
                    res_b = client_b.generate_structured(sys_eval, user_eval, MinorsLLMResponse)
                except SchemaValidationError as e:
                    store.log_event(uid, "ROB_ESCALATED", f"MINORS schema error: {e}")
                    processed_count += 1
                    continue

                if res_a.has_control_group != res_b.has_control_group:
                    store.log_event(uid, "ROB_ESCALATED", f"MINORS control group mismatch: A={res_a.has_control_group}, B={res_b.has_control_group}")
                    processed_count += 1
                    continue

                comparative = res_a.has_control_group
                items_to_check = [f"item{i}" for i in range(1, 9)]
                if comparative:
                    items_to_check += [f"item{i}" for i in range(9, 13)]

                scores_a = {}
                scores_b = {}
                quotes_a = {}
                quotes_b = {}

                for item_name in items_to_check:
                    field_name = MINORS_ITEM_FIELDS[item_name]
                    ia = getattr(res_a, field_name, None)
                    ib = getattr(res_b, field_name, None)

                    # Model A verify
                    if not ia or not ia.evidence_quote or not verify_quote(full_text_str, ia.evidence_quote):
                        scores_a[item_name] = "VOID"
                        quotes_a[item_name] = ia.evidence_quote if ia else ""
                    else:
                        scores_a[item_name] = str(ia.score)
                        quotes_a[item_name] = ia.evidence_quote

                    # Model B verify
                    if not ib or not ib.evidence_quote or not verify_quote(full_text_str, ib.evidence_quote):
                        scores_b[item_name] = "VOID"
                        quotes_b[item_name] = ib.evidence_quote if ib else ""
                    else:
                        scores_b[item_name] = str(ib.score)
                        quotes_b[item_name] = ib.evidence_quote

                total_a = compute_minors_overall(scores_a)
                total_b = compute_minors_overall(scores_b)

                # Save all domain results and overall rows to database
                for item_name in items_to_check:
                    store.add_rob_assessment(uid, "rob_a", client_a.model, "Non-RCT", item_name, scores_a[item_name], quotes_a[item_name])
                store.add_rob_assessment(uid, "rob_a", client_a.model, "Non-RCT", "__overall__", total_a, None)

                for item_name in items_to_check:
                    store.add_rob_assessment(uid, "rob_b", client_b.model, "Non-RCT", item_name, scores_b[item_name], quotes_b[item_name])
                store.add_rob_assessment(uid, "rob_b", client_b.model, "Non-RCT", "__overall__", total_b, None)

                # Calculate agreement stats (excluding overall)
                list_a = [scores_a[item] for item in items_to_check]
                list_b = [scores_b[item] for item in items_to_check]
                po, kappa, mismatches_idx = compute_agreement_stats(list_a, list_b)
                mismatched_items = [items_to_check[i] for i in mismatches_idx]

                # Check consensus
                has_void = "VOID" in list_a or "VOID" in list_b
                has_mismatch = len(mismatched_items) > 0

                if has_void or has_mismatch:
                    store.log_event(
                        uid,
                        "ROB_ESCALATED",
                        f"MINORS domain level conflict/VOID. Stats: agreement={po:.1%}, kappa={kappa:.3f}. Mismatches: {mismatched_items}"
                    )
                else:
                    threshold_msg = ""
                    if minors_threshold is not None:
                        threshold_msg = f" (threshold={minors_threshold})"
                    store.log_event(
                        uid,
                        "ROB_COMPLETED",
                        f"MINORS consensus score: {total_a}{threshold_msg}. Stats: agreement={po:.1%}, kappa={kappa:.3f}"
                    )

            processed_count += 1

        except (TransientError, httpx.HTTPError) as exc:
            logger.error(f"Transient error during RoB assessment for {uid}: {exc}")
            break
        except Exception as exc:
            logger.error(f"Failed RoB assessment for {uid}: {exc}")
            store.log_event(uid, "ROB_ESCALATED", f"Fatal error: {exc}")
            processed_count += 1

    return processed_count


# --- Main CLI -------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Risk-of-Bias (RoB) Assessment Runner")
    ap.add_argument("--protocol", required=True, type=Path, help="Path to protocol JSON")
    ap.add_argument("--limit", type=int, default=10, help="Max documents to process")
    ap.add_argument("--db", type=Path, help="Override DB path (SQLite)")

    args = ap.parse_args(argv)

    if not args.protocol.exists():
        print(f"Error: Protocol not found at {args.protocol}", file=sys.stderr)
        return 1

    from tools.protocol_build import ReviewProtocol
    protocol = ReviewProtocol.model_validate_json(args.protocol.read_text(encoding="utf-8"))

    store_path = args.db if args.db else None
    with StagingStore(store_path) if store_path else StagingStore() as store:
        count = run_rob_batch(store, protocol, args.limit)
        print(f"Completed RoB assessment for {count} documents.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

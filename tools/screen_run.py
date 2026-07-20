"""Screening Tool (PRISMA Multi-Agent title/abstract screening).

Orchestrates agent-based screening for systematic reviews.

Hiệu chuẩn M7.2 (docs/specs/M7.2-screening-calibration.md):
- Thuế bằng chứng ĐỐI XỨNG: include lẫn exclude đều phải kèm quote verbatim qua được
  verify_quote — không tồn tại verdict miễn phí (bài học κ=0, First Light 2026-07-11);
- Cặp screener ĐỐI KHÁNG: A xuất phát từ giả định giữ, B từ giả định loại — hai góc
  nhìn thật, không phải hai cách diễn đạt của cùng một thiên kiến;
- Guard thoái hóa: vote một chiều 100% trên batch đủ lớn ⇒ event SCREEN_DEGENERATE.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field

from sr_agent.config import OLLAMA_MODEL
from sr_agent.models.schemas import DocStatus
from sr_agent.store.staging import StagingStore
from sr_agent.errors import TransientError
from sr_agent.monitor.health import compute_cohen_kappa
import httpx
from tools.protocol_build import ReviewProtocol

logger = logging.getLogger("tools.screen_run")


# --- Contracts (D2) ------------------------------------------------------------------

class ScreenVerdict(BaseModel):
    verdict: Literal["include", "exclude"]
    criterion_id: str | None = None      # BẮT BUỘC khi exclude — một mã ET1..ET7
    evidence_quote: str | None = None    # BẮT BUỘC khi exclude — verbatim từ title/abstract
    relevance_quote: str | None = None   # BẮT BUỘC khi include — verbatim chứng minh khớp protocol
    confidence: Literal["high", "low"]


# M7.2 §3 Phase 1: guard thoái hóa — screener vote một chiều 100% trên batch đủ lớn
# là trạng thái bệnh (κ = 0 kinh điển), phải tự phát event thay vì đợi người soi κ.
DEGENERATE_MIN_VALID = 10

# FL-1 2026-07-19: κ=0.0000 lọt qua guard thoái hóa (guard chỉ nổ khi vote đúng
# 100%/0%; batch prevalence cao làm κ sập mà không rater nào tuyệt đối một chiều —
# kappa paradox). Sàn κ bắt phần còn lại: κ đo được dưới sàn trên batch đủ lớn
# ⇒ song thẩm không đóng góp thông tin ⇒ fail-loud (event, không chặn batch).
# Mốc 0.4 = ranh "moderate agreement" (Landis–Koch), dưới đó κ hiệu chuẩn
# 0.9042 (M7.2) coi như mất hiệu lực trên batch này.
KAPPA_FLOOR = 0.4


def kappa_below_floor(kappa: float | None, n_docs: int) -> bool:
    """κ đo được (không phải None/single-model) dưới sàn trên batch đủ lớn."""
    return kappa is not None and n_docs >= DEGENERATE_MIN_VALID and kappa < KAPPA_FLOOR


def flag_low_kappa(store, kappa, n_docs, include_rate_a, include_rate_b) -> bool:
    """Phát event SCREEN_KAPPA_LOW nếu κ dưới sàn. Fail-loud, không chặn batch."""
    if not kappa_below_floor(kappa, n_docs):
        return False
    store.log_event(
        "screening:batch", "SCREEN_KAPPA_LOW",
        f"κ={kappa:.4f} < sàn {KAPPA_FLOOR} trên {n_docs} doc "
        f"(include_rate A={include_rate_a:.0%}, B={include_rate_b:.0%}) — "
        "song thẩm mất hiệu lực trên batch này, cần người soi trước khi tin verdict",
    )
    return True


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
    text = unicodedata.normalize("NFKC", text)      # ligature ﬁ→fi, µ→μ, ¹→1
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)   # nối từ bị ngắt-gạch cuối dòng PDF
    # Collapse multiple whitespaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def verify_quote(source_text: str, quote: str) -> bool:
    if not quote or not source_text:
        return False
    norm_source = normalize_text(source_text)
    norm_quote = normalize_text(quote)
    return norm_quote in norm_source


# Deleted local compute_cohen_kappa (imported from health.py)


# --- Prompt Builders ------------------------------------------------------------------

# M7.2 Phase 1b: kỷ luật chép quote — Phase 2 đo được screener A invalid 50.6% vì lý do
# CƠ HỌC (chèn '...', sửa ký tự LaTeX \, $) chứ không phải nhận thức. Luật chép được nêu
# tường minh trong CẢ BA prompt; verifier giữ nguyên — nới verifier là nới firewall.
QUOTE_COPY_RULES = (
    "Quote copying rules (apply to BOTH 'evidence_quote' and 'relevance_quote'):\n"
    "- Copy ONE contiguous span character-for-character from the Title/Abstract.\n"
    "- NEVER shorten with '...' or '…', never paraphrase, never merge two sentences.\n"
    "- NEVER add, remove or alter characters — backslashes (\\), '$', '{', '}' and other "
    "LaTeX markup must be copied exactly as written in the text.\n"
    "- Prefer a SHORT span (5-20 words) that contains the decisive evidence; a short exact "
    "quote is always better than a long modified one.\n"
)

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
        "3. If you EXCLUDE, you must specify 'criterion_id' — EXACTLY one of the codes listed "
        "in the Exclusion Criteria above (e.g. ET1) — and an 'evidence_quote' that is a "
        "word-for-word verbatim quote from the text. Both fields are mandatory for EXCLUDE.\n"
        "4. If you INCLUDE, you must provide a 'relevance_quote': a word-for-word verbatim quote "
        "from the Title/Abstract showing the study matches the Target Population or the Target "
        "Intervention; 'criterion_id' and 'evidence_quote' must be null/None.\n"
        "5. Output must strictly adhere to the ScreenVerdict JSON schema.\n\n"
        + QUOTE_COPY_RULES
    )
    
    user_prompt = (
        f"Title: {doc_title}\n"
        f"Abstract: {doc_abstract}"
    )
    return system_prompt, user_prompt


def build_screener_b_prompts(doc_title: str, doc_abstract: str, protocol: ReviewProtocol, criteria: dict) -> tuple[str, str]:
    # Đối kháng thật với screener A (M7.2 §2.2): A xuất phát từ giả định GIỮ, B xuất phát
    # từ giả định LOẠI. Framing checklist cũ vẫn kết luận "NONE apply → INCLUDE" nên cả
    # cặp đều thiên-giữ — model nhỏ thoái hóa 100% include (First Light 2026-07-11).
    criteria_lines = []
    for cid in protocol.exclusion_criteria:
        if cid in criteria:
            criteria_lines.append(f"- {cid}: {criteria[cid]['label_vi']} ({criteria[cid]['description_en']})")
            
    system_prompt = (
        "You are a skeptical academic screening agent (screener_b) conducting a systematic literature review. "
        "Your task is to decide whether a study should be INCLUDED or EXCLUDED based on its Title and Abstract. "
        "Review Protocol:\n"
        f"- Target Population: {protocol.population.concept} (Synonyms: {', '.join(protocol.population.synonyms)})\n"
        f"- Target Intervention: {protocol.intervention.concept} (Synonyms: {', '.join(protocol.intervention.synonyms)})\n"
        f"- Allowed Languages: {', '.join(protocol.languages)}\n"
        f"- Year Range: {protocol.year_range if protocol.year_range else 'Any'}\n\n"
        "Exclusion Criteria Checklist:\n"
        + "\n".join(criteria_lines) + "\n\n"
        "Decision Rule (Burden of Proof is on Inclusion):\n"
        "1. Start with the assumption that the study is IRRELEVANT and should be EXCLUDED.\n"
        "2. INCLUDE only if you find clear, explicit evidence in the Title/Abstract that the study "
        "matches BOTH the Target Population AND the Target Intervention.\n"
        "3. If you INCLUDE, you must provide a 'relevance_quote': a word-for-word verbatim quote "
        "from the text demonstrating that match.\n"
        "4. If you EXCLUDE, you must specify 'criterion_id' — EXACTLY one of the codes listed in "
        "the checklist above (e.g. ET1 for wrong population, ET2 for missing intervention) — and "
        "an 'evidence_quote' that is a word-for-word verbatim quote from the text.\n"
        "5. Output must strictly adhere to the ScreenVerdict JSON schema.\n\n"
        + QUOTE_COPY_RULES
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
        "2. Make the final decision. If you choose to EXCLUDE, you must provide a valid 'criterion_id' and verbatim 'evidence_quote' from the text. "
        "If you choose to INCLUDE, you must provide a 'relevance_quote': a word-for-word verbatim quote from the text showing the study matches the protocol.\n"
        "3. If the decision is highly ambiguous and you cannot be certain, you may set 'confidence' to 'low'. Otherwise set 'confidence' to 'high'.\n"
        "4. Output must strictly match the ScreenVerdict JSON schema.\n\n"
        + QUOTE_COPY_RULES
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
            # Thuế bằng chứng đối xứng (M7.2 §2.1): include cũng phải trả phí kiểm chứng
            # như exclude — thiếu quote hoặc quote bịa ⇒ invalid ⇒ tiebreaker (bảo thủ,
            # không bao giờ tự lật thành exclude). Trước đây include miễn phí tuyệt đối
            # nên model nhỏ thoái hóa 100% include (κ = 0, First Light 2026-07-11).
            relevance_quote = verdict_data.relevance_quote
            if not relevance_quote or not verify_quote(source_text, relevance_quote):
                is_valid = False
            criterion_id = None
            evidence_quote = relevance_quote   # lưu chung cột evidence_quote — không đổi schema DB

        if not is_valid:
            return "invalid", criterion_id, evidence_quote, confidence
        return verdict, criterion_id, evidence_quote, confidence
    except (TransientError, httpx.HTTPError) as exc:
        raise exc
    except Exception as exc:
        logger.error(f"LLM generation failed: {exc}")
        return "invalid", None, None, "low"


def _screen_model_a() -> str:
    """Model của screener A — tách khỏi OLLAMA_MODEL toàn cục (M7.2 Phase 2R).

    Trước đây model_a ghim cứng OLLAMA_MODEL: muốn đổi screener A là phải đổi model
    của TOÀN pipeline (parser/enrich đi theo). Env riêng cho phép hiệu chuẩn cặp
    screener độc lập với phần còn lại của hệ."""
    return os.getenv("SR_SCREEN_MODEL_A") or OLLAMA_MODEL


def run_screening_a(store: StagingStore, protocol: ReviewProtocol, criteria: dict, limit: int) -> int:
    from sr_agent.parser.ollama_client import OllamaClient

    model_a = _screen_model_a()
    client = OllamaClient(model=model_a)
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
        store.add_screen_verdict(uid, "screener_a", model_a, verdict, crit_id, quote, conf)
        store.log_event(uid, "SCREENED", f"agent=screener_a, verdict={verdict}, criterion={crit_id or ''}")
        screened_count += 1
    return screened_count


# --- Main Logic ----------------------------------------------------------------------

def _batch_rates(verdicts: list[str]) -> tuple[float | None, float | None, int]:
    """(include_rate trên verdict hợp lệ, invalid_rate trên toàn bộ, số verdict hợp lệ).

    include_rate = None khi không có verdict hợp lệ nào — không bịa số từ tập rỗng.
    """
    if not verdicts:
        return None, None, 0
    valid = [v for v in verdicts if v in ("include", "exclude")]
    invalid_rate = (len(verdicts) - len(valid)) / len(verdicts)
    include_rate = (sum(1 for v in valid if v == "include") / len(valid)) if valid else None
    return include_rate, invalid_rate, len(valid)


def run_screening_batch(store: StagingStore, protocol: ReviewProtocol, criteria: dict, limit: int) -> dict:
    from sr_agent.parser.ollama_client import OllamaClient
    from sr_agent.doctor import check_model_drift
    
    started_at = datetime.now(timezone.utc).isoformat()
    model_a = _screen_model_a()
    model_b = os.getenv("SR_SCREEN_MODEL_B", "gemma4:e4b")

    client_a = OllamaClient(model=model_a)
    client_b = OllamaClient(model=model_b)

    if not client_a.is_available():
        logger.error("Ollama is not available. Cannot run multi-agent screening.")
        return {"processed": 0, "kappa": None}

    check_model_drift(store, "screening:batch", client_a)

    available_models = client_a.list_models()

    # Guard cho model A tùy biến: tag không tồn tại ⇒ quay về OLLAMA_MODEL ỒN ÀO
    # (event + warning) thay vì để mọi verdict A chết lặng lẽ thành invalid.
    if model_a != OLLAMA_MODEL and model_a not in available_models:
        store.log_event("screening:batch", "SCREEN_MODEL_A_FALLBACK",
                        f"model_a={model_a} không có trong ollama tags — screener_a quay về {OLLAMA_MODEL}")
        print(f"WARNING: model_a={model_a} is not available in Ollama tags. Falling back to {OLLAMA_MODEL}.")
        model_a = OLLAMA_MODEL
        client_a = OllamaClient(model=model_a)

    # T1: check if model_b is in list_models()
    single_model_mode = False
    if model_b not in available_models:
        single_model_mode = True
        store.log_event("screening:batch", "SCREEN_SINGLE_MODEL",
                        f"model_b={model_b} không có trong ollama tags — screener_b chạy tạm trên {model_a}")
        print(f"WARNING: model_b={model_b} is not available in Ollama tags. Fallback to single_model_mode using {model_a}.")
        
    # Get queued documents
    rows = store.conn.execute(
        "SELECT uid, payload FROM documents WHERE status = 'queued'"
    ).fetchall()
    
    to_screen = []
    for r in rows:
        uid = r["uid"]
        has_consensus = store.conn.execute(
            "SELECT 1 FROM events WHERE uid = ? AND event_type IN ('SCREEN_EXCLUDED', 'SCREEN_INCLUDED', 'SCREEN_ESCALATED')",
            (uid,)
        ).fetchone()
        if not has_consensus:
            to_screen.append(uid)
            
    if not to_screen:
        print("No documents require screening.")
        report_data = {
            "processed": 0,
            "kappa": None,
            "kappa_docs": 0,
            "single_model_mode": single_model_mode,
            "escalated": 0
        }
        if single_model_mode:
            report_data["kappa_reason"] = "single_model"
        store.record_run(
            query=f"screening:{protocol.topic_vi}",
            started_at=started_at,
            report_json=json.dumps(report_data)
        )
        return {"processed": 0, "kappa": None, "single_model_mode": single_model_mode}
        
    screened_count = 0
    batch_verdicts = []
    verdicts_a_all: list[str] = []       # mọi verdict A trong batch (kể cả invalid) — cho guard thoái hóa
    verdicts_b_all: list[str] = []
    escalated_count = 0

    try:
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
                active_client_b = client_a if single_model_mode else client_b
                verdict_b, crit_b, quote_b, conf_b = invoke_screener_agent(active_client_b, sys_b, usr_b, source_text, protocol)
                store.add_screen_verdict(uid, "screener_b", active_client_b.model, verdict_b, crit_b, quote_b, conf_b)
                store.log_event(uid, "SCREENED", f"agent=screener_b, verdict={verdict_b}, criterion={crit_b or ''}")

            verdicts_a_all.append(verdict_a)
            verdicts_b_all.append(verdict_b)
            if verdict_a in ("include", "exclude") and verdict_b in ("include", "exclude"):
                batch_verdicts.append((verdict_a, verdict_b))

            # 3. Consensus & Tie-breaker
            if verdict_a == "invalid" or verdict_b == "invalid":
                # Direct tie-breaker due to invalid verdict
                v1_desc = f"Verdict: {verdict_a} (Criterion: {crit_a}, Quote: {quote_a})"
                v2_desc = f"Verdict: {verdict_b} (Criterion: {crit_b}, Quote: {quote_b})"
                is_esc = run_tiebreaker_flow(store, client_a, uid, doc, protocol, criteria, v1_desc, v2_desc)
                if is_esc:
                    escalated_count += 1
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
                is_esc = run_tiebreaker_flow(store, client_a, uid, doc, protocol, criteria, v1_desc, v2_desc)
                if is_esc:
                    escalated_count += 1
                
            screened_count += 1
    except (TransientError, httpx.HTTPError) as exc:
        print(f"Transient error encountered during batch screening: {exc}")
        remaining = len(to_screen[:limit]) - screened_count
        print(f"Processed: {screened_count}. Remaining: {remaining}.")

    # Calculate Kappa
    if single_model_mode:
        kappa = None
    else:
        kappa = compute_cohen_kappa(batch_verdicts)

    # Guard thoái hóa (M7.2 §3 Phase 1): screener vote một chiều 100%/0% trên batch
    # đủ lớn ⇒ không đóng góp thông tin phân biệt (κ = 0 kinh điển) — phát event ngay,
    # không đợi người soi κ. Fail-loud, không chặn batch: kết quả vẫn ghi, người quyết.
    include_rate_a, invalid_rate_a, valid_a = _batch_rates(verdicts_a_all)
    include_rate_b, invalid_rate_b, valid_b = _batch_rates(verdicts_b_all)
    for agent_name, rate, valid_n in (
        ("screener_a", include_rate_a, valid_a),
        ("screener_b", include_rate_b, valid_b),
    ):
        if valid_n >= DEGENERATE_MIN_VALID and rate in (0.0, 1.0):
            store.log_event(
                "screening:batch", "SCREEN_DEGENERATE",
                f"agent={agent_name} include_rate={rate:.0%} trên {valid_n} verdict hợp lệ "
                "— screener vote một chiều, không đóng góp thông tin phân biệt",
            )

    # Sàn κ (FL-1): bắt trường hợp κ sập mà không rater nào một chiều tuyệt đối.
    flag_low_kappa(store, kappa, len(batch_verdicts), include_rate_a, include_rate_b)

    report_data = {
        "processed": screened_count,
        "kappa": kappa,
        "kappa_docs": len(batch_verdicts),
        "single_model_mode": single_model_mode,
        "escalated": escalated_count,
        "include_rate_a": include_rate_a,
        "include_rate_b": include_rate_b,
        "invalid_rate_a": invalid_rate_a,
        "invalid_rate_b": invalid_rate_b,
    }
    if single_model_mode:
        report_data["kappa_reason"] = "single_model"

    store.record_run(
        query=f"screening:{protocol.topic_vi}",
        started_at=started_at,
        report_json=json.dumps(report_data)
    )

    res = {
        "processed": screened_count,
        "kappa": kappa,
        "single_model_mode": single_model_mode,
        "include_rate_a": include_rate_a,
        "include_rate_b": include_rate_b,
        "invalid_rate_a": invalid_rate_a,
        "invalid_rate_b": invalid_rate_b,
    }
    if single_model_mode:
        res["kappa_reason"] = "single_model"
    return res


def run_tiebreaker_flow(store: StagingStore, client, uid: str, doc, protocol: ReviewProtocol, criteria: dict, v1_desc: str, v2_desc: str) -> bool:
    source_text = f"{doc.title}\n{doc.abstract or ''}"
    sys_tb, usr_tb = build_tiebreaker_prompts(doc.title, doc.abstract or "", protocol, criteria, v1_desc, v2_desc)
    
    verdict_tb, crit_tb, quote_tb, conf_tb = invoke_screener_agent(client, sys_tb, usr_tb, source_text, protocol)
    store.add_screen_verdict(uid, "tiebreaker", client.model, verdict_tb, crit_tb, quote_tb, conf_tb)
    store.log_event(uid, "SCREENED", f"agent=tiebreaker, verdict={verdict_tb}, criterion={crit_tb or ''}")
    
    if verdict_tb == "invalid" or conf_tb == "low":
        # Escalate to human
        store.log_event(uid, "SCREEN_ESCALATED", f"Tiebreaker low-confidence or invalid. tb_verdict={verdict_tb}")
        return True
    else:
        # High confidence resolved
        if verdict_tb == "exclude":
            store.set_status(uid, DocStatus.REJECTED)
            store.log_event(uid, "SCREEN_EXCLUDED", f"Tiebreaker resolved to exclude. criterion={crit_tb}")
        else:
            store.log_event(uid, "SCREEN_INCLUDED", "Tiebreaker resolved to include.")
        return False


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

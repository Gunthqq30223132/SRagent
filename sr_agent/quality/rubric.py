"""Automated Filtering Rubric — chấm chất lượng tài liệu thô, tất định 100%.

Rubric là dữ liệu khai báo (dict/JSON, validate bằng RUBRIC_JSON_SCHEMA);
mỗi `rule` là một hàm pure Python trong RULE_REGISTRY. Điểm tổng thang 0-100
= Σ(weight × sub_score)/Σ(weight). Điểm quyết định:
  1. Gate: dưới `pass_threshold` -> loại trước khi tốn LLM parse.
  2. Rank: thứ tự vào hàng đợi WIP (top-5/ngày) ở QC UI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sr_agent.config import RUBRIC_PASS_THRESHOLD
from sr_agent.models.schemas import Document, RubricCriterionScore, RubricResult

# JSON Schema để validate file rubric config tùy biến (draft 2020-12)
RUBRIC_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SR-Agent Filtering Rubric",
    "type": "object",
    "required": ["version", "pass_threshold", "criteria"],
    "properties": {
        "version": {"type": "string"},
        "pass_threshold": {"type": "number", "minimum": 0, "maximum": 100},
        "criteria": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["key", "weight", "rule", "params"],
                "properties": {
                    "key": {"type": "string"},
                    "weight": {"type": "number", "exclusiveMinimum": 0},
                    "rule": {
                        "enum": [
                            "tier_lookup",
                            "linear_decay_years",
                            "keyword_flags",
                            "length_range",
                            "required_fields",
                        ]
                    },
                    "params": {"type": "object"},
                },
            },
        },
    },
}

DEFAULT_RUBRIC: dict[str, Any] = {
    "version": "1.0",
    "pass_threshold": RUBRIC_PASS_THRESHOLD,
    "criteria": [
        {
            "key": "source_authority",
            "weight": 30,
            "rule": "tier_lookup",
            "params": {"1": 100, "2": 70},
        },
        {
            "key": "recency",
            "weight": 20,
            "rule": "linear_decay_years",
            "params": {"full_score_within": 2, "zero_at": 10},
        },
        {
            "key": "artifact_availability",
            "weight": 25,
            "rule": "keyword_flags",
            "params": {
                "code": ["github.com", "gitlab.com", "bitbucket.org"],
                "dataset": ["zenodo", "huggingface.co/datasets", "figshare", "dryad"],
            },
        },
        {
            "key": "abstract_completeness",
            "weight": 15,
            "rule": "length_range",
            "params": {"min_words": 80, "ideal_words": 200},
        },
        {
            "key": "metadata_integrity",
            "weight": 10,
            "rule": "required_fields",
            "params": {"fields": ["title", "authors", "published_date"]},
        },
    ],
}


# --- Rule functions: (Document, params) -> (sub_score 0-100, lý do) -------------

def _rule_tier_lookup(doc: Document, params: dict) -> tuple[float, str]:
    score = float(params.get(str(doc.authority_tier), 0))
    return score, f"authority_tier={doc.authority_tier}"


def _rule_linear_decay_years(doc: Document, params: dict) -> tuple[float, str]:
    if doc.published_date is None:
        return 0.0, "thiếu published_date"
    age_years = (datetime.now(timezone.utc) - doc.published_date).days / 365.25
    full, zero = float(params["full_score_within"]), float(params["zero_at"])
    if age_years <= full:
        return 100.0, f"{age_years:.1f} năm tuổi (<= {full})"
    if age_years >= zero:
        return 0.0, f"{age_years:.1f} năm tuổi (>= {zero})"
    score = 100.0 * (zero - age_years) / (zero - full)
    return score, f"{age_years:.1f} năm tuổi (decay tuyến tính)"


def _rule_keyword_flags(doc: Document, params: dict) -> tuple[float, str]:
    """Mỗi nhóm keyword (code/dataset/...) xuất hiện trong text -> chia đều điểm."""
    haystack = " ".join(
        filter(None, [doc.abstract or "", doc.full_text or "", doc.url or ""])
    ).lower()
    groups = list(params.items())
    if not groups:
        return 0.0, "rubric không khai báo nhóm keyword"
    hits = [
        name for name, keywords in groups
        if any(kw.lower() in haystack for kw in keywords)
    ]
    score = 100.0 * len(hits) / len(groups)
    return score, f"tìm thấy: {', '.join(hits) or 'không nhóm nào'}"


def _rule_length_range(doc: Document, params: dict) -> tuple[float, str]:
    n_words = len((doc.abstract or "").split())
    min_w, ideal_w = int(params["min_words"]), int(params["ideal_words"])
    if n_words == 0:
        return 0.0, "không có abstract"
    if n_words < min_w:
        return 100.0 * n_words / min_w * 0.5, f"abstract {n_words} từ (< {min_w})"
    if n_words >= ideal_w:
        return 100.0, f"abstract {n_words} từ (>= {ideal_w})"
    score = 50.0 + 50.0 * (n_words - min_w) / (ideal_w - min_w)
    return score, f"abstract {n_words} từ"


def _rule_required_fields(doc: Document, params: dict) -> tuple[float, str]:
    fields = params["fields"]
    present = [f for f in fields if getattr(doc, f, None)]
    score = 100.0 * len(present) / len(fields)
    missing = set(fields) - set(present)
    return score, f"thiếu: {', '.join(sorted(missing)) or 'không'}"


def _rule_evidence_rank(doc: Document, params: dict) -> tuple[float, str]:
    """Chấm theo BẬC CHỨNG CỨ y khoa (1 = mạnh nhất). Tra bảng, không nội suy.

    TẠI SAO CẦN LUẬT RIÊNG: mọi luật sẵn có đều chấm trên đặc điểm bề mặt
    (tuổi bài, có repo code, độ dài abstract). Trong y học, thứ quyết định một
    bài có được đưa vào tổng quan hệ thống hay không là THIẾT KẾ NGHIÊN CỨU —
    một RCT năm 2015 có sức nặng hơn một bài tổng quan tường thuật năm nay.
    Không có luật này thì rubric xếp bài theo độ mới, tức xếp ngược.

    evidence_level=None nghĩa CHƯA PHÂN LOẠI. Trả về `unranked_score` (mặc định
    50, tức trung tính) chứ KHÔNG trả 0 — cho điểm 0 sẽ âm thầm loại mọi tài
    liệu đến từ nguồn không gán nhãn thiết kế (arXiv, IEEE), biến một khoảng
    trống dữ liệu thành một phán quyết chất lượng.
    """
    if doc.evidence_level is None:
        return float(params.get("unranked_score", 50)), "chưa phân loại thiết kế"
    table = params.get("scores", {})
    score = float(table.get(str(doc.evidence_level), 0))
    return score, f"bậc chứng cứ={doc.evidence_level}"


RULE_REGISTRY: dict[str, Callable[[Document, dict], tuple[float, str]]] = {
    "tier_lookup": _rule_tier_lookup,
    "linear_decay_years": _rule_linear_decay_years,
    "keyword_flags": _rule_keyword_flags,
    "length_range": _rule_length_range,
    "required_fields": _rule_required_fields,
    "evidence_rank": _rule_evidence_rank,
}


def score_document(doc: Document, rubric: dict[str, Any] = DEFAULT_RUBRIC) -> RubricResult:
    breakdown: list[RubricCriterionScore] = []
    total_weight = 0.0
    weighted_sum = 0.0
    for criterion in rubric["criteria"]:
        rule_fn = RULE_REGISTRY[criterion["rule"]]
        sub_score, reason = rule_fn(doc, criterion["params"])
        weight = float(criterion["weight"])
        breakdown.append(RubricCriterionScore(
            key=criterion["key"], weight=weight, sub_score=sub_score, reason=reason,
        ))
        weighted_sum += weight * sub_score
        total_weight += weight
    total = round(weighted_sum / total_weight, 2) if total_weight else 0.0
    return RubricResult(
        total=total,
        passed=total >= float(rubric["pass_threshold"]),
        breakdown=breakdown,
    )

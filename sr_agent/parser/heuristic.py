"""Tách section bằng heuristic regex TRƯỚC khi động đến LLM.

Nguyên tắc "rẻ trước, đắt sau": heading khớp từ khóa chuẩn (IMRAD/PAEC) được
gán vai trò với confidence=1.0; chỉ phần không khớp mới cần LLM phân loại.
"""

from __future__ import annotations

import re

from sr_agent.models.schemas import (
    CanonicalRole,
    Document,
    IMRADSections,
    PAECSections,
    Section,
)

# heading phổ biến -> vai trò chuẩn (so khớp lowercase, bỏ số thứ tự "1.", "II.")
_ROLE_KEYWORDS: dict[CanonicalRole, tuple[str, ...]] = {
    CanonicalRole.CONTEXT: ("introduction", "background", "problem", "motivation"),
    CanonicalRole.METHOD: ("method", "methods", "methodology", "approach",
                           "proposed", "architecture", "design"),
    CanonicalRole.FINDINGS: ("result", "results", "evaluation", "experiment",
                             "experiments", "findings"),
    CanonicalRole.IMPLICATIONS: ("discussion", "conclusion", "conclusions",
                                 "limitation", "limitations", "future work"),
}

# dòng heading: đầu dòng, có thể mang số mục lục, ngắn, KHÔNG kết thúc bằng
# dấu câu (phân biệt với câu văn thường cũng viết hoa đầu dòng)
_HEADING_RE = re.compile(
    r"^\s*(?:(?:\d+|[IVXLC]+)[\.\)]\s+)?([A-Z][^\n]{1,58}[^\s.:;,!?])\s*$",
    re.MULTILINE,
)
_MAX_HEADING_WORDS = 8


def _looks_like_heading(text: str) -> bool:
    return len(text.split()) <= _MAX_HEADING_WORDS


def classify_heading(heading: str) -> CanonicalRole | None:
    text = heading.lower().strip()
    for role, keywords in _ROLE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return role
    return None


def split_sections(full_text: str) -> list[tuple[str, str]]:
    """Cắt full-text thành [(heading, body)] theo các dòng dạng heading."""
    matches = [
        m for m in _HEADING_RE.finditer(full_text) if _looks_like_heading(m.group(1))
    ]
    if not matches:
        return [("", full_text.strip())] if full_text.strip() else []
    chunks: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        body = full_text[start:end].strip()
        if body:
            chunks.append((m.group(1).strip(), body))
    return chunks


def heuristic_sections(doc: Document) -> dict[CanonicalRole, Section]:
    """Gán vai trò cho các phần khớp heading chuẩn. Phần mơ hồ để LLM xử lý sau."""
    if not doc.full_text:
        return {}
    assigned: dict[CanonicalRole, Section] = {}
    for heading, body in split_sections(doc.full_text):
        role = classify_heading(heading)
        if role is not None and role not in assigned:
            assigned[role] = Section(heading_raw=heading, content=body, confidence=1.0)
    return assigned


def build_sections(doc: Document, roles: dict[CanonicalRole, Section]):
    """Đổ dict vai trò chuẩn về đúng union type theo nguồn (A=IMRAD, B=PAEC)."""
    if doc.source == "ieee":
        return IMRADSections(
            introduction=roles.get(CanonicalRole.CONTEXT),
            methods=roles.get(CanonicalRole.METHOD),
            results=roles.get(CanonicalRole.FINDINGS),
            discussion=roles.get(CanonicalRole.IMPLICATIONS),
        )
    return PAECSections(
        problem=roles.get(CanonicalRole.CONTEXT),
        approach=roles.get(CanonicalRole.METHOD),
        evaluation=roles.get(CanonicalRole.FINDINGS),
        conclusion=roles.get(CanonicalRole.IMPLICATIONS),
    )

"""Pydantic schema cho Parser Đa Cấu Trúc.

Chiến lược: MỘT model `Document` duy nhất, phần sections là discriminated
union (IMRAD cho tài liệu Loại A / PAEC cho Loại B, phân biệt bằng
`doc_type`). Downstream (rubric, UI, Notion) không đọc union trực tiếp mà
đọc qua `canonical_sections` — view 4 vai trò chuẩn — nên thêm cấu trúc
phân đoạn mới sau này không phải sửa consumer.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from sr_agent.config import AUTHORITY_TIERS, ID_PATTERNS


class DocStatus(str, Enum):
    """State machine của một bản ghi trong staging DB."""

    FETCHED = "fetched"
    DEDUPED = "deduped"
    SCORED = "scored"
    PARSED = "parsed"
    QUEUED = "queued"       # đang nằm trong hàng đợi WIP chờ người duyệt
    APPROVED = "approved"   # đã đẩy sang Notion — giữ vĩnh viễn (audit)
    REJECTED = "rejected"   # người dùng loại — giữ vĩnh viễn (audit)
    EXPIRED = "expired"     # quá TTL 72h không tương tác — auto-purge
    DLQ = "dlq"             # lỗi, chờ xử lý lại thủ công


class CanonicalRole(str, Enum):
    """4 vai trò phân đoạn chuẩn, giao của IMRAD và PAEC."""

    CONTEXT = "context"            # A: Introduction | B: Problem
    METHOD = "method"              # A: Methods      | B: Approach
    FINDINGS = "findings"          # A: Results      | B: Evaluation
    IMPLICATIONS = "implications"  # A: Discussion   | B: Conclusion


class Section(BaseModel):
    heading_raw: str = ""
    content: str
    # 1.0 = heuristic match theo heading; <1.0 = LLM gán vai trò
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class IMRADSections(BaseModel):
    """Tài liệu Loại A (PubMed) — Introduction/Methods/Results/Discussion."""

    doc_type: Literal["A"] = "A"
    introduction: Section | None = None
    methods: Section | None = None
    results: Section | None = None
    discussion: Section | None = None

    def to_canonical(self) -> dict[CanonicalRole, Section | None]:
        return {
            CanonicalRole.CONTEXT: self.introduction,
            CanonicalRole.METHOD: self.methods,
            CanonicalRole.FINDINGS: self.results,
            CanonicalRole.IMPLICATIONS: self.discussion,
        }


class PAECSections(BaseModel):
    """Tài liệu Loại B (arXiv) — Problem/Approach/Evaluation/Conclusion."""

    doc_type: Literal["B"] = "B"
    problem: Section | None = None
    approach: Section | None = None
    evaluation: Section | None = None
    conclusion: Section | None = None

    def to_canonical(self) -> dict[CanonicalRole, Section | None]:
        return {
            CanonicalRole.CONTEXT: self.problem,
            CanonicalRole.METHOD: self.approach,
            CanonicalRole.FINDINGS: self.evaluation,
            CanonicalRole.IMPLICATIONS: self.conclusion,
        }


AnySections = Annotated[
    Union[IMRADSections, PAECSections], Field(discriminator="doc_type")
]


class RubricCriterionScore(BaseModel):
    key: str
    weight: float
    sub_score: float = Field(ge=0.0, le=100.0)
    reason: str = ""


class RubricResult(BaseModel):
    total: float = Field(ge=0.0, le=100.0)
    passed: bool
    breakdown: list[RubricCriterionScore] = []


class CritiqueQuestion(BaseModel):
    """Câu hỏi phản biện sinh lúc parse, đổ vào Phần 2 trang Notion."""

    question: str
    # Người dùng gắn nhãn nguồn gốc thông tin khi trả lời trên Notion
    labels: list[str] = ["[CONFIRMED]", "[INFERRED]", "[UNKNOWN]"]


_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Chuẩn hóa tiêu đề cho so khớp mờ D34: bỏ dấu, lowercase, gọn whitespace."""
    text = unicodedata.normalize("NFKD", title)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _PUNCT_RE.sub(" ", text.lower())
    return _WS_RE.sub(" ", text).strip()


class Document(BaseModel):
    """Bản ghi chuẩn hóa duy nhất chảy xuyên suốt pipeline."""

    uid: str  # "pubmed:12345678" | "arxiv:2401.12345" — computed từ source+source_id
    source: Literal["pubmed", "arxiv"]
    source_id: str
    authority_tier: int = Field(ge=1)
    alternate_uids: list[str] = []  # bản trùng bị merge (giữ vết, không vứt)

    title: str
    title_normalized: str = ""
    abstract: str | None = None
    authors: list[str] = []
    published_date: datetime | None = None
    url: str | None = None
    full_text: str | None = None

    sections: AnySections | None = None
    critique_questions: list[CritiqueQuestion] = []
    rubric: RubricResult | None = None

    status: DocStatus = DocStatus.FETCHED
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notion_page_id: str | None = None

    @field_validator("source_id")
    @classmethod
    def _validate_source_id_format(cls, v: str, info) -> str:
        source = info.data.get("source")
        pattern = ID_PATTERNS.get(source or "")
        if pattern and not pattern.match(v):
            raise ValueError(
                f"source_id {v!r} không khớp quy tắc ID tĩnh của nguồn {source!r} "
                f"(pattern: {pattern.pattern})"
            )
        return v

    @model_validator(mode="after")
    def _derive_fields(self) -> "Document":
        expected_uid = make_uid(self.source, self.source_id)
        if not self.uid:
            self.uid = expected_uid
        elif self.uid != expected_uid:
            raise ValueError(f"uid {self.uid!r} không khớp {expected_uid!r}")
        if not self.title_normalized:
            self.title_normalized = normalize_title(self.title)
        return self

    @property
    def canonical_sections(self) -> dict[CanonicalRole, Section | None]:
        if self.sections is None:
            return {role: None for role in CanonicalRole}
        return self.sections.to_canonical()


def make_uid(source: str, source_id: str) -> str:
    """Khóa nội bộ đồng nhất: arXiv đã tự mang prefix, PubMed thì thêm."""
    return source_id if source_id.startswith(f"{source}:") else f"{source}:{source_id}"


def default_tier(source: str) -> int:
    return AUTHORITY_TIERS[source]

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

from sr_agent.config import AUTHORITY_TIERS, ID_PATTERNS, UNKNOWN_SOURCE_TIER


class DocStatus(str, Enum):
    """State machine của một bản ghi trong staging DB."""

    FETCHED = "fetched"
    DEDUPED = "deduped"
    SCORED = "scored"
    PARSED = "parsed"
    QUEUED = "queued"       # đang nằm trong hàng đợi WIP chờ người duyệt
    APPROVED = "approved"   # đã đẩy sang Notion — giữ vĩnh viễn (audit)
    APPROVED_LOCAL = "approved_local"  # approve ở dry-run (thiếu NOTION_TOKEN)
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
    """Tài liệu Loại A (IEEE/CS Transactions) — Introduction/Methods/Results/Discussion."""

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


class TechnicalMetadata(BaseModel):
    """Siêu dữ liệu chất lượng kỹ thuật CS — LLM trích xuất NGHIÊM NGẶT
    (extract-only, không suy diễn) từ Abstract/Introduction.

    Schema này được đưa thẳng vào Ollama structured output (format=json schema)
    nên mô tả field viết tiếng Anh cho model đọc.
    """

    has_code_repo: bool = Field(
        description="True only if the authors explicitly provide a code repository link"
    )
    code_repo_url: str | None = Field(
        default=None,
        description="The exact repository URL (GitHub/GitLab/...) if stated, else null",
    )
    dataset_specification: str | None = Field(
        default=None,
        description='Dataset size/name stated verbatim (e.g. "10,000 samples", "ImageNet-1k"), else null',
    )
    evaluated_benchmarks: list[str] = Field(
        default_factory=list,
        description="Standard benchmark names the paper explicitly evaluates on",
    )
    declared_limitations: str | None = Field(
        default=None,
        description="Technical limitations the authors themselves acknowledge, else null",
    )


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

    uid: str  # "ieee:12345678" | "arxiv:2401.12345" — computed từ source+source_id
    # MỞ KHÓA 2026-08-23: trước đây là Literal["ieee","arxiv"] — danh sách trắng
    # đóng, thêm nguồn phải sửa mã lõi. Nay là chuỗi tự do có chuẩn hóa, còn
    # quy tắc riêng của từng nguồn nằm ở sổ đăng ký config.register_source().
    # Lý do: SR-Agent phải tái dùng được cho mọi lĩnh vực, không riêng CS/y khoa.
    source: str
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

    # NGOẠI LỆ VÙNG CẤM (2026-08-23), phần 2: bậc chứng cứ y khoa.
    # Số NHỎ = mạnh hơn (1 = meta-analysis). None = CHƯA PHÂN LOẠI, khác hẳn
    # với "đã phân loại là yếu" — tầng trên phải hiển thị hai thứ này khác nhau.
    # Trường tuỳ chọn, mặc định None ⇒ mọi Document CS hiện có không đổi hành vi.
    evidence_level: int | None = Field(default=None, ge=1)

    sections: AnySections | None = None
    tech_meta: TechnicalMetadata | None = None
    critique_questions: list[CritiqueQuestion] = []
    rubric: RubricResult | None = None

    status: DocStatus = DocStatus.FETCHED
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notion_page_id: str | None = None

    @field_validator("source")
    @classmethod
    def _normalize_source(cls, v: str) -> str:
        """Chuẩn hóa tên nguồn. Mọi nguồn đều được nhận — nhưng phải là một tên.

        Chỉ chặn chuỗi rỗng/khoảng trắng: một Document không có nguồn thì không
        truy vết được về đâu cả, mà truy vết nguồn là điều kiện sống của hệ thống.
        """
        v = (v or "").strip().lower()
        if not v:
            raise ValueError("source rỗng — tài liệu không truy vết được nguồn gốc")
        return v

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
    """Khóa nội bộ đồng nhất: arXiv đã tự mang prefix, IEEE thì thêm."""
    return source_id if source_id.startswith(f"{source}:") else f"{source}:{source_id}"


def default_tier(source: str) -> int:
    """Tier của nguồn. Nguồn chưa đăng ký -> hạng thấp nhất, KHÔNG ném lỗi.

    Trước đây hàm này ném KeyError cho nguồn lạ, biến "chưa thẩm định" thành
    "hỏng". Nay nguồn lạ vẫn chạy được nhưng nhận tier thấp: chưa ai kiểm thì
    không được hưởng uy tín, và cũng không được chặn đường người dùng.
    """
    return AUTHORITY_TIERS.get(source.strip().lower(), UNKNOWN_SOURCE_TIER)

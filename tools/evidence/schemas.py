"""Hợp đồng dữ liệu tầng Evidence M8 (D33 §3). Thuần khai báo, không I/O.

Nguyên tắc: core topic-blind — schema này KHÔNG chứa ngữ nghĩa miền (không có từ
lâm sàng nào trong code); trường trích xuất do PROTOCOL định nghĩa lúc chạy.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, Field

# Thứ tự ưu tiên ID chuẩn khi một bản ghi có nhiều external id.
_ID_PRIORITY = ("doi", "pmid", "arxiv", "s2", "isbn")


def normalize_title(title: str) -> str:
    """Chuẩn hóa title cho so khớp mờ: casefold, bỏ dấu câu, gộp whitespace."""
    t = title.casefold()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


class RefRecord(BaseModel):
    """Một bản ghi thư mục từ bất kỳ nguồn nào (.ris/.bib/S2 API)."""

    source_db: str                                   # "pubmed" | "embase" | "europepmc" | "arxiv" | "ieee" | "s2" | ...
    external_ids: dict[str, str] = Field(default_factory=dict)  # key lowercase: doi/pmid/arxiv/s2
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    raw_type: str | None = None                      # RIS TY / BibTeX entry type
    provenance: str = ""                             # "<file>#<record_index>" hoặc "s2:<paper_id>"

    def canonical_uid(self) -> str:
        """ID chuẩn tất định: doi → pmid → arxiv → s2 → sha12(title chuẩn hóa)."""
        for key in _ID_PRIORITY:
            val = self.external_ids.get(key, "").strip()
            if val:
                return f"{key}:{val.casefold()}"
        digest = hashlib.sha256(normalize_title(self.title).encode("utf-8")).hexdigest()[:12]
        return f"title:{digest}"

    def title_normalized(self) -> str:
        return normalize_title(self.title)


class DedupReport(BaseModel):
    """Kết quả gỡ trùng đa nguồn — mọi quyết định truy vết được."""

    unique: list[RefRecord]
    duplicates: list[tuple[str, str, str]] = Field(default_factory=list)
    # (uid bị loại, uid giữ lại, tầng quyết định: "exact_id" | "fuzzy_title")
    n_input: int = 0
    n_unique: int = 0


# --- Result B: trích xuất song thẩm ------------------------------------------

class FieldSpec(BaseModel):
    """Một cột trích xuất do protocol định nghĩa (Elicit-style)."""

    name: str
    description: str
    kind: Literal["numeric", "text"]
    required: bool = False


class StatClaim(BaseModel):
    """Một khẳng định của MỘT agent về MỘT trường — giá trị byte-exact + quote verbatim."""

    field: str
    value: str | None = None          # None = "bài báo không báo cáo trường này"
    unit: str | None = None
    quote: str | None = None          # BẮT BUỘC khi value != None


class AgentExtraction(BaseModel):
    """Structured output của một extractor agent (Ollama format=schema)."""

    claims: list[StatClaim]


class ArbiterChoice(BaseModel):
    """Structured output của arbiter — ẩn danh, không biết claim nào của model nào."""

    choice: Literal["a", "b", "neither"]
    quote: str | None = None          # quote ủng hộ lựa chọn (bắt buộc khi chọn a/b)


ConsensusStatus = Literal[
    "AGREED",               # 2 agent khớp byte-exact, quote đều verify
    "RESOLVED_BY_ARBITER",  # lệch → arbiter chọn 1 bên, quote verify
    "HUMAN_REVIEW",         # không phân xử được bằng chứng cứ → người quyết
    "NOT_REPORTED",         # cả 2 agent: bài không báo cáo trường này
]


class ConsensusOutcome(BaseModel):
    field: str
    status: ConsensusStatus
    value_final: str | None = None
    unit: str | None = None
    quote_final: str | None = None
    value_a: str | None = None
    value_b: str | None = None
    detail: str = ""

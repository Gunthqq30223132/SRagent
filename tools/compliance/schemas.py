"""Pydantic schemas cho COMPLIANCE-OS (D32 §2.1).

Mọi lệnh LLM trong hệ chạy temp 0 + structured output; đầu ra KHÔNG dựng được
qua các schema này = vô hiệu (void), không bao giờ "sửa cho khớp". Đây là hợp đồng
dữ liệu chung giữa 4 agent (Orchestrator / Agent-E / Agent-V / Agent-R) — thuần khai
báo, không I/O, không phụ thuộc thứ tự merge nhánh khác.

Tên gọi bám cột "Thuật ngữ chuẩn" của bảng đổi tên §0.2 (authority_tier T1/T2/T3,
node_health_index, restricted_change_protocol).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# --- Tầng nhập & tầng tất định (Layer A) ------------------------------------

Intent = Literal["migrate", "scale", "residency", "degraded_deploy", "freeform"]


class ComplianceQuery(BaseModel):
    """Đầu vào chuẩn hóa; namespace_allowlist do Orchestrator gán, agent sau KHÔNG nới."""

    query_id: str
    intent: Intent
    environment_profile: dict = Field(default_factory=dict)
    target_packages: list[str] = Field(default_factory=list)
    namespace_allowlist: list[str] = Field(default_factory=list)


class ComputedMetric(BaseModel):
    """Một con số do Layer A tính ra; formula_id truy ngược về pure function sinh nó."""

    name: str
    value: str
    unit: str | None = None
    formula_id: str


class HardBlock(BaseModel):
    """Xung khắc cứng đã có căn cứ trong KB; source_node bắt buộc (chống citation mồ côi)."""

    block_id: str
    subject: str          # ví dụ: "pkgA==1.2 x pkgB>=3.0"
    reason: str
    source_node: str      # node_id trong KB


class HoldFlag(BaseModel):
    """Cờ HOLD/CONTINUE cho một gói/thành phần, kèm nguồn quyết định."""

    subject: str
    verdict: Literal["HOLD", "CONTINUE"]
    source_node: str


class LayerAResult(BaseModel):
    """Kết quả tất định của Agent-E TRƯỚC khi gọi LLM. Bất biến trong suốt một run."""

    query_id: str
    computed: list[ComputedMetric] = Field(default_factory=list)
    hard_blocks: list[HardBlock] = Field(default_factory=list)
    hold_flags: list[HoldFlag] = Field(default_factory=list)
    rollback_required: bool = False


# --- Tầng kiểm chứng (Agent-V / Agent-R) ------------------------------------

class AssertionTuple(BaseModel):
    """Một khẳng định bóc từ prose LLM để đối chiếu ngược về ground truth."""

    entity: str
    attribute: str
    value: str
    constraint_source: str    # node_id HOẶC "layer_a:<formula_id>"


class Violation(BaseModel):
    """Vi phạm cấp compliance (khác Violation cấp-anchor trong firewall)."""

    never_event: str          # "NE1".."NE5"
    subject: str
    detail: str


class ReconciliationVerdict(BaseModel):
    passed: bool
    violations: list[Violation] = Field(default_factory=list)
    never_events_triggered: list[str] = Field(default_factory=list)
    rewrite_count: int = 0
    final_state: Literal["CO_VERIFIED", "CO_REJECTED", "CO_ESCALATED"]


# --- Đầu ra cuối (Agent-E, sau khi qua Agent-R) -----------------------------

class ComplianceBlueprint(BaseModel):
    """Blueprint triển khai — đầu ra ở trạng thái CO_VERIFIED chờ người CO_APPROVED.

    S1 (§3): rollback_plan là trường BẮT BUỘC — thiếu = invalid tại tầng Pydantic,
    chưa cần tới firewall. "Khẩn cấp" không nới lỏng ràng buộc này.
    """

    query_id: str
    narrative: str
    rollback_plan: str = Field(min_length=1)
    plan_b: bool = False
    layer_a: LayerAResult

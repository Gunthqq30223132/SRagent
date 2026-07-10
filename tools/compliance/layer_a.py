"""Layer A — nhân tất định của COMPLIANCE-OS (D32 §2.3, §3 S1/S2/S4).

Toàn bộ module là PURE FUNCTIONS: không I/O, không LLM, không random, không thời gian
hệ thống. Cùng input ⇒ cùng output, bit-for-bit. Test không cần mock (pattern rubric.py).
Đây là "ground truth" mà Numeric Firewall V24 (NE1) đối chiếu ngược — nếu Layer A sai thì
firewall vô dụng (garbage-in), nên mỗi hàm có test giá trị biên + bất biến nghiệp vụ.

Không thêm dependency: so sánh version viết tay (cấm `packaging`/`semver`).
"""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel

from tools.compliance.schemas import ComputedMetric, HardBlock

# ============================================================================
# S1 — Solver ràng buộc version (di trú legacy khẩn cấp)
# ============================================================================

_OPS = ("==", "!=", ">=", "<=", ">", "<")


def _parse_version(v: str) -> tuple[int, ...]:
    """'1.2.10' -> (1, 2, 10). Chỉ lấy chuỗi số, giữ nguyên giá trị (không cắt cụt)."""
    parts = re.findall(r"\d+", v)
    return tuple(int(p) for p in parts) if parts else (0,)


def _cmp(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    """So sánh tuple version có đệm 0; trả -1/0/1. '1.2' == '1.2.0'."""
    n = max(len(a), len(b))
    a = a + (0,) * (n - len(a))
    b = b + (0,) * (n - len(b))
    return (a > b) - (a < b)


def _split_spec(spec: str) -> tuple[str, str]:
    """'>=3.0' -> ('>=', '3.0'). Không toán tử ⇒ mặc định '=='."""
    spec = spec.strip()
    for op in _OPS:  # thứ tự: 2 ký tự trước 1 ký tự để '>=' không bị đọc thành '>'
        if spec.startswith(op):
            return op, spec[len(op):].strip()
    return "==", spec


def _satisfies(version: str, spec: str) -> bool:
    """version có thỏa spec? So sánh tất định trên tuple số."""
    op, target = _split_spec(spec)
    c = _cmp(_parse_version(version), _parse_version(target))
    return {
        "==": c == 0, "!=": c != 0,
        ">=": c >= 0, "<=": c <= 0,
        ">": c > 0, "<": c < 0,
    }[op]


class IncompatRule(BaseModel):
    """Một hàng ma trận xung khắc, đã bóc từ KB (§1.1). Byte-exact với nguồn."""

    block_id: str
    pkg_a: str
    spec_a: str           # ví dụ "==1.2"
    pkg_b: str
    spec_b: str           # ví dụ ">=3.0"
    reason: str
    source_node: str


class ConstraintSolution(BaseModel):
    status: Literal["CLEAN", "RESOLVED", "UNRESOLVABLE"]
    hard_blocks: list[HardBlock] = []
    # resolution CHỈ có giá trị khi status != UNRESOLVABLE (bất biến S1).
    resolution: dict[str, str] | None = None


def _active_conflicts(
    manifest: dict[str, str], rules: list[IncompatRule]
) -> list[IncompatRule]:
    """Rule 'active' ⇔ manifest có CẢ hai gói và thỏa CẢ hai vế xung khắc."""
    active: list[IncompatRule] = []
    for r in rules:
        va, vb = manifest.get(r.pkg_a), manifest.get(r.pkg_b)
        if va is None or vb is None:
            continue
        if _satisfies(va, r.spec_a) and _satisfies(vb, r.spec_b):
            active.append(r)
    return active


def solve_version_constraints(
    manifest: dict[str, str],
    incompat_rules: list[IncompatRule],
    available_versions: dict[str, list[str]] | None = None,
) -> ConstraintSolution:
    """Phát hiện xung khắc active; thử gỡ bằng cách đổi pin trong available_versions.

    Bất biến S1: xung khắc không gỡ được ⇒ status=UNRESOLVABLE, resolution=None,
    hard_blocks đầy đủ — KHÔNG BAO GIỜ auto-continue. Gỡ tất định: duyệt phiên bản
    ứng viên theo thứ tự SẮP XẾP GIẢM (ưu tiên mới nhất), dừng ở nghiệm đầu tiên khử
    hết mọi xung khắc active — cùng input luôn cho cùng nghiệm.
    """
    active = _active_conflicts(manifest, incompat_rules)
    if not active:
        return ConstraintSolution(status="CLEAN", resolution=dict(manifest))

    blocks = [
        HardBlock(
            block_id=r.block_id,
            subject=f"{r.pkg_a}{r.spec_a} x {r.pkg_b}{r.spec_b}",
            reason=r.reason,
            source_node=r.source_node,
        )
        for r in active
    ]

    if available_versions:
        involved = sorted({p for r in active for p in (r.pkg_a, r.pkg_b)})
        candidate = _search_resolution(
            manifest, incompat_rules, involved, available_versions
        )
        if candidate is not None:
            return ConstraintSolution(
                status="RESOLVED", hard_blocks=blocks, resolution=candidate
            )

    return ConstraintSolution(status="UNRESOLVABLE", hard_blocks=blocks, resolution=None)


def _search_resolution(
    manifest: dict[str, str],
    rules: list[IncompatRule],
    involved: list[str],
    available: dict[str, list[str]],
) -> dict[str, str] | None:
    """Backtracking tất định: gán lần lượt phiên bản (giảm dần) cho gói liên quan,
    trả candidate đầu tiên KHÔNG còn xung khắc active nào. None nếu vô nghiệm."""

    def versions_for(pkg: str) -> list[str]:
        opts = available.get(pkg, [manifest[pkg]] if pkg in manifest else [])
        return sorted(set(opts), key=_parse_version, reverse=True)

    def recurse(i: int, current: dict[str, str]) -> dict[str, str] | None:
        if i == len(involved):
            return dict(current) if not _active_conflicts(current, rules) else None
        pkg = involved[i]
        for v in versions_for(pkg):
            current[pkg] = v
            got = recurse(i + 1, current)
            if got is not None:
                return got
        current[pkg] = manifest.get(pkg, versions_for(pkg)[0])
        return None

    return recurse(0, dict(manifest))


# ============================================================================
# S2 — Công thức sizing (scale-up đa cụm). Mỗi công thức 1 formula_id ổn định.
# ============================================================================

def size_replicas(expected_rps: float, rps_per_replica: float, ha_min: int = 2) -> ComputedMetric:
    """Số replica = ceil(rps / rps_per_replica), sàn ha_min để giữ HA."""
    if rps_per_replica <= 0:
        raise ValueError("rps_per_replica phải > 0")
    n = max(math.ceil(expected_rps / rps_per_replica), ha_min)
    return ComputedMetric(name="replicas", value=str(n), unit=None, formula_id="replicas.v1")


def size_headroom(base_units: float, headroom_pct: float) -> ComputedMetric:
    """Tài nguyên cấp phát = base × (1 + headroom%/100). Làm tròn lên đơn vị nguyên."""
    if headroom_pct < 0:
        raise ValueError("headroom_pct không âm")
    provisioned = math.ceil(base_units * (1.0 + headroom_pct / 100.0))
    return ComputedMetric(
        name="provisioned_units", value=str(provisioned), unit=None,
        formula_id="headroom.v1",
    )


def quorum_size(cluster_nodes: int) -> ComputedMetric:
    """Quorum đa số = floor(n/2) + 1 (đồng thuận kiểu Raft/etcd)."""
    if cluster_nodes < 1:
        raise ValueError("cluster_nodes >= 1")
    q = cluster_nodes // 2 + 1
    return ComputedMetric(name="quorum", value=str(q), unit=None, formula_id="quorum.v1")


# ============================================================================
# S4 — node_health_index + restricted_change_protocol (hạ tầng suy giảm)
# ============================================================================

class NodeInventory(BaseModel):
    days_to_eol: int          # âm = đã quá EOL
    kernel_age_days: int
    incidents_90d: int
    days_since_patch: int


class NodeAssessment(BaseModel):
    """degradation_index: 0-100, CÀNG CAO CÀNG SUY GIẢM (rủi ro cao)."""

    degradation_index: int
    protocol: Literal["standard", "cautious", "restricted", "blocked"]
    canary_pct: int
    maintenance_window_required: bool
    forbid_auto_restart: bool
    hard_block: HardBlock | None = None


def node_health_index(inv: NodeInventory) -> int:
    """Điểm suy giảm tất định 0-100 (cao = xấu). Trọng số cố định, clamp từng thành phần.

    - EOL: quá hạn hoặc <30 ngày → phạt nặng (35 điểm); giãn tuyến tính tới 180 ngày.
    - Kernel: >730 ngày (2 năm) → tối đa 25 điểm.
    - Incident 90 ngày: mỗi sự cố 5 điểm, trần 25.
    - Patch: >180 ngày chưa vá → tối đa 15 điểm.
    """
    eol = 35 if inv.days_to_eol < 30 else max(0, 35 - round(35 * min(inv.days_to_eol, 180) / 180))
    kernel = round(25 * min(max(inv.kernel_age_days, 0), 730) / 730)
    incidents = min(25, max(0, inv.incidents_90d) * 5)
    patch = round(15 * min(max(inv.days_since_patch, 0), 180) / 180)
    return int(min(100, eol + kernel + incidents + patch))


def assess_node(inv: NodeInventory) -> NodeAssessment:
    """Map degradation_index → restricted_change_protocol. Node quá ngưỡng đỏ ⇒ hard_block
    'thay node trước' (chịu NE2 — phải xuất hiện trong prose)."""
    idx = node_health_index(inv)
    if idx >= 85:
        return NodeAssessment(
            degradation_index=idx, protocol="blocked", canary_pct=0,
            maintenance_window_required=True, forbid_auto_restart=True,
            hard_block=HardBlock(
                block_id=f"NODE_EOL_{idx}",
                subject="degraded_node_beyond_red_threshold",
                reason=f"degradation_index={idx} >= 85: thay node trước khi triển khai",
                source_node="layer_a:node_health.v1",
            ),
        )
    if idx >= 60:
        return NodeAssessment(
            degradation_index=idx, protocol="restricted", canary_pct=5,
            maintenance_window_required=True, forbid_auto_restart=True,
        )
    if idx >= 30:
        return NodeAssessment(
            degradation_index=idx, protocol="cautious", canary_pct=10,
            maintenance_window_required=True, forbid_auto_restart=False,
        )
    return NodeAssessment(
        degradation_index=idx, protocol="standard", canary_pct=25,
        maintenance_window_required=False, forbid_auto_restart=False,
    )

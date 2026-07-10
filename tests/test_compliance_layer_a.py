"""Tests cho Layer A của COMPLIANCE-OS (D32.2). Offline 100%, pure functions — không mock.

Trọng tâm: giá trị biên + BẤT BIẾN NGHIỆP VỤ (invariants) — thứ mà Numeric Firewall (NE1)
tin tưởng làm ground truth. Nếu Layer A sai thì firewall vô dụng, nên các bất biến ở đây là
tuyến phòng thủ đầu tiên.
"""

import pytest
from pydantic import ValidationError

from tools.compliance.layer_a import (
    ConstraintSolution,
    IncompatRule,
    NodeInventory,
    _cmp,
    _parse_version,
    _satisfies,
    assess_node,
    node_health_index,
    quorum_size,
    size_headroom,
    size_replicas,
    solve_version_constraints,
)
from tools.compliance.schemas import ComplianceBlueprint, LayerAResult


# --- So sánh version (không dùng packaging/semver) --------------------------

class TestVersionCompare:
    def test_parse_keeps_full_value_no_truncation(self):
        # bất biến byte-exact: 1.2.10 KHÔNG bao giờ thành 1.2.1
        assert _parse_version("1.2.10") == (1, 2, 10)
        assert _cmp(_parse_version("1.2.10"), _parse_version("1.2.1")) == 1

    def test_padding_equivalence(self):
        assert _cmp(_parse_version("1.2"), _parse_version("1.2.0")) == 0

    @pytest.mark.parametrize("ver,spec,ok", [
        ("3.1", ">=3.0", True),
        ("2.9", ">=3.0", False),
        ("1.2", "==1.2", True),
        ("1.2.10", "==1.2.1", False),   # phân biệt được .10 vs .1
        ("2.0", "<2.0", False),
        ("1.9.9", "<2.0", True),
        ("3.0", "!=3.0", False),
    ])
    def test_satisfies(self, ver, spec, ok):
        assert _satisfies(ver, spec) is ok

    def test_two_char_operator_not_misread(self):
        # '>=' không được đọc nhầm thành '>'
        assert _satisfies("3.0", ">=3.0") is True


# --- S1: solver ràng buộc version -------------------------------------------

RULE = IncompatRule(
    block_id="B1", pkg_a="libssl", spec_a="==1.0", pkg_b="webapp", spec_b=">=3.0",
    reason="webapp>=3.0 drops libssl 1.0 ABI", source_node="rfc-x#01",
)


class TestSolver:
    def test_clean_when_no_active_conflict(self):
        sol = solve_version_constraints({"libssl": "2.0", "webapp": "3.1"}, [RULE])
        assert sol.status == "CLEAN"
        assert sol.hard_blocks == []
        assert sol.resolution == {"libssl": "2.0", "webapp": "3.1"}

    def test_active_conflict_unresolvable_has_no_resolution(self):
        # BẤT BIẾN S1: UNRESOLVABLE ⇒ resolution is None, hard_blocks đầy đủ
        sol = solve_version_constraints({"libssl": "1.0", "webapp": "3.5"}, [RULE])
        assert sol.status == "UNRESOLVABLE"
        assert sol.resolution is None
        assert len(sol.hard_blocks) == 1
        assert sol.hard_blocks[0].source_node == "rfc-x#01"

    def test_resolution_actually_clears_all_conflicts(self):
        sol = solve_version_constraints(
            {"libssl": "1.0", "webapp": "3.5"}, [RULE],
            available_versions={"libssl": ["1.0", "2.0", "2.1"], "webapp": ["3.5"]},
        )
        assert sol.status == "RESOLVED"
        assert sol.resolution is not None
        # nghiệm trả về không được còn xung khắc active nào
        from tools.compliance.layer_a import _active_conflicts
        assert _active_conflicts(sol.resolution, [RULE]) == []

    def test_resolution_is_deterministic(self):
        args = (
            {"libssl": "1.0", "webapp": "3.5"}, [RULE],
            {"libssl": ["1.0", "2.0", "2.1"], "webapp": ["3.5"]},
        )
        a = solve_version_constraints(*args)
        b = solve_version_constraints(*args)
        assert a.resolution == b.resolution

    def test_no_available_versions_stays_unresolvable(self):
        sol = solve_version_constraints({"libssl": "1.0", "webapp": "3.5"}, [RULE])
        assert sol.status == "UNRESOLVABLE" and sol.resolution is None


# --- S2: sizing formulas ----------------------------------------------------

class TestSizing:
    def test_replicas_ceils_and_respects_ha_floor(self):
        assert size_replicas(100, 30, ha_min=2).value == "4"   # ceil(3.33)=4
        assert size_replicas(10, 30, ha_min=2).value == "2"    # sàn HA
        assert size_replicas(100, 30).formula_id == "replicas.v1"

    def test_replicas_rejects_zero_capacity(self):
        with pytest.raises(ValueError):
            size_replicas(100, 0)

    def test_headroom_rounds_up(self):
        assert size_headroom(100, 20).value == "120"
        assert size_headroom(100, 25).value == "125"
        assert size_headroom(3, 10).value == "4"               # ceil(3.3)

    def test_quorum_majority(self):
        assert quorum_size(3).value == "2"
        assert quorum_size(5).value == "3"
        assert quorum_size(1).value == "1"

    def test_formula_ids_stable_across_calls(self):
        # BẤT BIẾN NE1: formula_id ổn định giữa 2 lần gọi cùng input
        assert size_replicas(100, 30).formula_id == size_replicas(100, 30).formula_id
        assert quorum_size(5).formula_id == "quorum.v1"


# --- S4: node_health_index + protocol ---------------------------------------

HEALTHY = NodeInventory(days_to_eol=900, kernel_age_days=30, incidents_90d=0, days_since_patch=5)
DEAD = NodeInventory(days_to_eol=-10, kernel_age_days=1500, incidents_90d=8, days_since_patch=400)


class TestNodeHealth:
    def test_healthy_node_low_index_standard_protocol(self):
        a = assess_node(HEALTHY)
        assert a.degradation_index < 30
        assert a.protocol == "standard"
        assert a.hard_block is None
        assert a.forbid_auto_restart is False

    def test_dead_node_blocked_with_hard_block(self):
        a = assess_node(DEAD)
        assert a.degradation_index >= 85
        assert a.protocol == "blocked"
        assert a.canary_pct == 0
        assert a.hard_block is not None      # NE2 sẽ buộc block này vào prose

    def test_index_is_deterministic_and_bounded(self):
        assert node_health_index(DEAD) == node_health_index(DEAD)
        assert 0 <= node_health_index(HEALTHY) <= 100
        assert 0 <= node_health_index(DEAD) <= 100

    def test_monotonic_worse_eol_never_lowers_index(self):
        # BẤT BIẾN: node quá hạn EOL không thể "khỏe hơn" node còn hạn (cùng phần còn lại)
        near = NodeInventory(days_to_eol=10, kernel_age_days=30, incidents_90d=0, days_since_patch=5)
        far = NodeInventory(days_to_eol=900, kernel_age_days=30, incidents_90d=0, days_since_patch=5)
        assert node_health_index(near) >= node_health_index(far)

    def test_protocol_thresholds_boundary(self):
        # ngay tại ngưỡng 60 phải là restricted + cấm auto-restart
        cautious = NodeInventory(days_to_eol=100, kernel_age_days=400, incidents_90d=2, days_since_patch=90)
        a = assess_node(cautious)
        assert a.protocol in {"cautious", "restricted"}
        if a.degradation_index >= 60:
            assert a.forbid_auto_restart is True


# --- Schema invariant S1: rollback_plan bắt buộc ----------------------------

class TestBlueprintSchema:
    def test_blueprint_requires_rollback_plan(self):
        la = LayerAResult(query_id="q1")
        with pytest.raises(ValidationError):
            ComplianceBlueprint(query_id="q1", narrative="...", layer_a=la)  # thiếu rollback_plan

    def test_blueprint_rejects_empty_rollback_plan(self):
        la = LayerAResult(query_id="q1")
        with pytest.raises(ValidationError):
            ComplianceBlueprint(query_id="q1", narrative="...", rollback_plan="", layer_a=la)

    def test_valid_blueprint_constructs(self):
        la = LayerAResult(query_id="q1")
        bp = ComplianceBlueprint(
            query_id="q1", narrative="Deploy ...", rollback_plan="revert to snapshot X", layer_a=la
        )
        assert bp.rollback_plan == "revert to snapshot X"
        assert bp.plan_b is False

"""D32.4 — Harness 5 scenario mô phỏng (spec §3), end-to-end và offline 100%.

Mỗi scenario chạy CHUỖI THẬT: KB ingest (SQLite tmp) → search → Layer A (pure functions)
→ prose (chuỗi cố định đóng vai đầu ra LLM — Agent-E runtime chưa nối LLM ở phase này)
→ Agent-R reconcile → verdict kỳ vọng. Không mock module nội bộ nào: harness chứng minh
các mảnh D32.1/2/3 khớp nhau qua API công khai.

NỢ GHI NHẬN (D32.5): S5 mới phủ nhánh mâu thuẫn phát hiện được tất định (L2 đè L1-security
thiếu flag → NE3) + Plan B artifact; detector "2 chỉ thị L1 active loại trừ nhau cùng scope"
cần mini-spec riêng, chưa có trong D32.3.
"""

import pytest
from pydantic import ValidationError

from tools.compliance.kb import ingest_markdown_table, search
from tools.compliance.layer_a import (
    IncompatRule,
    NodeInventory,
    assess_node,
    quorum_size,
    size_replicas,
    solve_version_constraints,
)
from tools.compliance.reconcile import reconcile, run_reconcile_loop
from tools.compliance.schemas import (
    ComplianceBlueprint,
    ComputedMetric,
    LayerAResult,
)


@pytest.fixture(autouse=True)
def _fts5_only(monkeypatch):
    """Harness chạy tất định thuần FTS5 — vô hiệu embedding (và dọn env leak nếu có)."""
    monkeypatch.setenv("SR_EMBED_MODEL", "")


@pytest.fixture
def kb_db(tmp_path):
    return str(tmp_path / "scenario_kb.db")


def _ingest(tmp_path, kb_db, name: str, md: str, meta: dict):
    f = tmp_path / f"{name}.md"
    f.write_text(md, encoding="utf-8")
    return ingest_markdown_table(str(f), meta, db_path=kb_db)


INCOMPAT_MD = """
| Package A | Operator A | Version A | Package B | Operator B | Version B | Condition | Action |
|---|---|---|---|---|---|---|---|
| libssl | == | 1.0 | webapp | >= | 3.0 | default | rollback |
"""

META_PKG = {
    "doc_id": "matrix_s1", "version": "2026-07", "domain": "packaging",
    "authority_tier": "T1", "layer": "L1_canonical", "namespace": "prod",
}


# ============================================================================
# S1 — Emergency legacy migration: solver + rollback bắt buộc + NE2/NE5
# ============================================================================

class TestS1EmergencyMigration:
    def test_unresolvable_conflict_never_auto_continues(self, tmp_path, kb_db):
        nodes = _ingest(tmp_path, kb_db, "s1", INCOMPAT_MD, META_PKG)
        rule = IncompatRule(
            block_id="B1", pkg_a="libssl", spec_a="==1.0", pkg_b="webapp", spec_b=">=3.0",
            reason="ABI break", source_node=nodes[0].node_id,
        )
        sol = solve_version_constraints({"libssl": "1.0", "webapp": "3.5"}, [rule])
        assert sol.status == "UNRESOLVABLE"
        assert sol.resolution is None                      # bất biến S1
        assert sol.hard_blocks[0].source_node == nodes[0].node_id

    def test_emergency_does_not_relax_rollback_requirement(self):
        la = LayerAResult(query_id="s1", rollback_required=True)
        with pytest.raises(ValidationError):               # thiếu rollback_plan = invalid
            ComplianceBlueprint(query_id="s1", narrative="deploy now!", layer_a=la)

    def test_prose_omitting_hard_block_is_rejected(self, tmp_path, kb_db):
        nodes = _ingest(tmp_path, kb_db, "s1b", INCOMPAT_MD, META_PKG)
        nid = nodes[0].node_id
        rule = IncompatRule(
            block_id="B1", pkg_a="libssl", spec_a="==1.0", pkg_b="webapp", spec_b=">=3.0",
            reason="ABI break", source_node=nid,
        )
        sol = solve_version_constraints({"libssl": "1.0", "webapp": "3.5"}, [rule])
        la = LayerAResult(query_id="s1", hard_blocks=sol.hard_blocks, rollback_required=True)
        retrieved = search("libssl", namespace="prod", db_path=kb_db)
        smooth = f"Mọi thứ sẵn sàng, tiến hành nâng cấp webapp ngay [{nid}]."
        verdict = reconcile(smooth, la, retrieved, {n.node_id for n in nodes}, set())
        assert verdict.final_state == "CO_REJECTED"
        assert "NE2" in verdict.never_events_triggered      # block bị giấu → lộ ngay

    def test_full_chain_verified_when_block_and_rollback_present(self, tmp_path, kb_db):
        nodes = _ingest(tmp_path, kb_db, "s1c", INCOMPAT_MD, META_PKG)
        nid = nodes[0].node_id
        rule = IncompatRule(
            block_id="B1", pkg_a="libssl", spec_a="==1.0", pkg_b="webapp", spec_b=">=3.0",
            reason="ABI break", source_node=nid,
        )
        sol = solve_version_constraints({"libssl": "1.0", "webapp": "3.5"}, [rule])
        la = LayerAResult(query_id="s1", hard_blocks=sol.hard_blocks, rollback_required=True)
        retrieved = search("libssl", namespace="prod", db_path=kb_db)
        prose = (
            f"CHẶN: libssl==1.0 x webapp>=3.0 [{nid}]. "
            f"Rollback về snapshot gần nhất trước khi thử lại [{nid}]."
        )
        verdict = reconcile(prose, la, retrieved, {n.node_id for n in nodes}, set())
        assert verdict.passed is True
        assert verdict.final_state == "CO_VERIFIED"
        bp = ComplianceBlueprint(
            query_id="s1", narrative=prose,
            rollback_plan="revert snapshot + repin libssl", layer_a=la,
        )
        assert bp.rollback_plan


# ============================================================================
# S2 — Multi-cluster scale-up: số nào cũng phải truy về formula/node (NE1)
# ============================================================================

def _layer_a_s2() -> LayerAResult:
    return LayerAResult(
        query_id="s2",
        computed=[
            size_replicas(900, 250),                        # ceil(3.6)=4 → "4"
            quorum_size(5),                                 # "3"
            ComputedMetric(name="ram_per_replica", value="8", unit="GB", formula_id="ram.v1"),
        ],
        rollback_required=False,
    )


class TestS2ScaleUp:
    def test_prose_with_layer_a_numbers_verifies(self):
        la = _layer_a_s2()
        prose = "Mỗi replica cấp 8 GB [layer_a:ram.v1], quorum giữ mức đa số [layer_a:quorum.v1]."
        verdict = reconcile(prose, la, [], set(), {"replicas.v1", "quorum.v1", "ram.v1"})
        assert verdict.final_state == "CO_VERIFIED"

    def test_invented_number_rejected_then_fixed_via_rewrite_loop(self):
        la = _layer_a_s2()
        drafts = iter([
            "Mỗi replica cấp 16 GB [layer_a:ram.v1].",      # LLM bịa 16 GB
            "Mỗi replica cấp 8 GB [layer_a:ram.v1].",       # viết lại đúng
        ])
        verdict, prose = run_reconcile_loop(
            lambda v: next(drafts), la, [], set(), {"ram.v1"},
        )
        assert verdict.final_state == "CO_VERIFIED"
        assert verdict.rewrite_count == 1
        assert "8 GB" in prose


# ============================================================================
# S3 — Residency clampdown: L2 đè L1 phải có conflict_flag (NE3)
# ============================================================================

RESIDENCY_L1_MD = """
| Component | Metric | Threshold | Unit | Action |
|---|---|---|---|---|
| object-store | replication_regions | 3 | regions | expand |
"""

RESIDENCY_L2_MD = """
| Component | Metric | Threshold | Unit | Action |
|---|---|---|---|---|
| object-store | replication_regions | 1 | regions | clamp |
"""

META_L1_SEC = {
    "doc_id": "global_sec", "version": "1", "domain": "security",
    "authority_tier": "T1", "layer": "L1_canonical", "namespace": "prod",
}
META_L2_SEC = {
    "doc_id": "local_runbook", "version": "1", "domain": "security",
    "authority_tier": "T3", "layer": "L2_local_runbook", "namespace": "prod",
}


class TestS3ResidencyClampdown:
    def test_unflagged_l2_override_escalates_before_llm(self, tmp_path, kb_db):
        _ingest(tmp_path, kb_db, "l1", RESIDENCY_L1_MD, META_L1_SEC)
        _ingest(tmp_path, kb_db, "l2", RESIDENCY_L2_MD, META_L2_SEC)   # KHÔNG flag
        retrieved = search("object-store", namespace="prod", db_path=kb_db)
        assert len(retrieved) == 2                          # thấy cả hai layer
        la = LayerAResult(query_id="s3")
        verdict = reconcile("bất kỳ prose nào.", la, retrieved, set(), set())
        assert verdict.final_state == "CO_ESCALATED"        # lỗi dữ liệu — không rewrite
        assert "NE3" in verdict.never_events_triggered
        assert verdict.rewrite_count == 0

    def test_declared_conflict_flag_clears_ne3(self, tmp_path, kb_db):
        _ingest(tmp_path, kb_db, "l1", RESIDENCY_L1_MD, META_L1_SEC)
        meta_flagged = {**META_L2_SEC, "conflict_flag": "overrides global_sec#000 per waiver W-7 (data-residency)"}
        _ingest(tmp_path, kb_db, "l2f", RESIDENCY_L2_MD, meta_flagged)
        retrieved = search("object-store", namespace="prod", db_path=kb_db)
        la = LayerAResult(query_id="s3")
        verdict = reconcile("Ghi chú vận hành thường.", la, retrieved, set(), set())
        assert "NE3" not in verdict.never_events_triggered
        assert verdict.final_state == "CO_VERIFIED"


# ============================================================================
# S4 — Degraded deploy: tham số rollout từ bảng ngưỡng, node đỏ = hard block
# ============================================================================

class TestS4DegradedDeploy:
    def test_red_node_hard_block_must_surface_in_prose(self):
        dead = NodeInventory(days_to_eol=-30, kernel_age_days=1500,
                             incidents_90d=9, days_since_patch=400)
        assessment = assess_node(dead)
        assert assessment.protocol == "blocked" and assessment.hard_block is not None
        la = LayerAResult(query_id="s4", hard_blocks=[assessment.hard_block],
                          rollback_required=True)
        hidden = "Hạ tầng hơi cũ nhưng vẫn triển khai được [layer_a:node_health.v1]."
        verdict = reconcile(hidden, la, [], set(), {"node_health.v1"})
        assert "NE2" in verdict.never_events_triggered      # giấu node đỏ → lộ

        honest = (
            f"CHẶN: {assessment.hard_block.subject} [layer_a:node_health.v1]. "
            "Thay node trước, rollback plan giữ nguyên [layer_a:node_health.v1]."
        )
        verdict2 = reconcile(honest, la, [], set(), {"node_health.v1"})
        assert verdict2.final_state == "CO_VERIFIED"

    def test_rollout_params_come_from_threshold_table_not_prose(self):
        healthy = NodeInventory(days_to_eol=900, kernel_age_days=30,
                                incidents_90d=0, days_since_patch=10)
        a = assess_node(healthy)
        assert (a.protocol, a.canary_pct) == ("standard", 25)
        degraded = NodeInventory(days_to_eol=45, kernel_age_days=700,
                                 incidents_90d=4, days_since_patch=170)
        d = assess_node(degraded)
        assert d.canary_pct in {0, 5, 10}                   # chỉ giá trị trong bảng ngưỡng
        assert d.degradation_index > a.degradation_index


# ============================================================================
# S5 — Black-swan: cấm tổng hợp thỏa hiệp; Plan B là artifact riêng sạch nguồn
# ============================================================================

class TestS5BlackSwan:
    def test_smooth_compromise_prose_cannot_pass_over_conflict(self, tmp_path, kb_db):
        # Mâu thuẫn phát hiện được tất định: L2-security đè L1 KHÔNG flag.
        _ingest(tmp_path, kb_db, "l1", RESIDENCY_L1_MD, META_L1_SEC)
        _ingest(tmp_path, kb_db, "l2", RESIDENCY_L2_MD, META_L2_SEC)
        retrieved = search("object-store", namespace="prod", db_path=kb_db)
        la = LayerAResult(query_id="s5")
        smooth = "Dung hòa hai chuẩn bằng cấu hình trung gian, mọi bên đều ổn."
        verdict = reconcile(smooth, la, retrieved, set(), set())
        assert verdict.passed is False
        assert verdict.final_state == "CO_ESCALATED"        # người quyết, hệ không tự chọn

    def test_plan_b_artifact_built_only_from_clean_nodes_verifies(self, tmp_path, kb_db):
        nodes = _ingest(tmp_path, kb_db, "clean", INCOMPAT_MD, META_PKG)  # packaging, sạch
        nid = nodes[0].node_id
        retrieved = search("libssl", namespace="prod", db_path=kb_db)
        la = LayerAResult(query_id="s5b", rollback_required=True)
        prose = f"Plan B: giữ libssl==1.0, cô lập webapp phiên bản cũ [{nid}]."
        verdict = reconcile(prose, la, retrieved, {n.node_id for n in nodes}, set())
        assert verdict.final_state == "CO_VERIFIED"
        bp = ComplianceBlueprint(
            query_id="s5b", narrative=prose, plan_b=True,
            rollback_plan="tắt Plan B, quay lại cấu hình hiện hành", layer_a=la,
        )
        assert bp.plan_b is True                            # artifact riêng, người chọn

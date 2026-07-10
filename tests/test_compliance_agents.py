"""Tests cho Agent-V (assertions) + Agent-R (reconcile) của COMPLIANCE-OS (D32.3).

Offline 100%, không mock HTTP — cả hai module là code tất định thuần. Mỗi NE checker
có đủ: case pass + case vi phạm + case biên. Vòng rewrite được test bằng generate_fn
giả tiêm vào (LLM thật chỉ xuất hiện ở runtime D32.4).
"""

import pytest

from tools.compliance.assertions import (
    extract_assertions,
    extract_citations,
    split_sentences,
)
from tools.compliance.reconcile import (
    MAX_REWRITES,
    check_ne1_numeric,
    check_ne2_completeness,
    check_ne3_conflict_flags,
    check_ne4_citations,
    check_ne5_resolve,
    layer_a_source_text,
    reconcile,
    run_reconcile_loop,
)
from tools.compliance.schemas import ComputedMetric, HardBlock, LayerAResult

# --- Fixtures chung ----------------------------------------------------------

LA = LayerAResult(
    query_id="q1",
    computed=[ComputedMetric(name="latency_target", value="12", unit="ms", formula_id="lat.v1")],
    hard_blocks=[HardBlock(
        block_id="B1", subject="libssl==1.0 x webapp>=3.0",
        reason="webapp>=3.0 drops libssl 1.0 ABI", source_node="rfc-x#01",
    )],
    rollback_required=True,
)

NODE_OK = {
    "node_id": "rfc-x#01", "layer": "L1_canonical", "domain": "packaging",
    "conflict_flag": None,
    "content": "libssl==1.0 XUNG KHẮC webapp>=3.0 — hành động: rollback",
}
KB_IDS = {"rfc-x#01", "rfc-y#02"}
FORMULAS = {"lat.v1"}

PROSE_OK = (
    "Hệ đạt latency_target 12 ms [layer_a:lat.v1]. "
    "Cấm kết hợp libssl==1.0 x webapp>=3.0 [rfc-x#01]. "
    "Rollback bằng snapshot trước đó [rfc-x#01]."
)


# --- Agent-V: extract_assertions ----------------------------------------------

class TestAgentV:
    def test_package_spec_with_citation_source(self):
        tuples = extract_assertions("Pin webapp==3.1 để tương thích [rfc-x#01].")
        pkg = [t for t in tuples if t.attribute == "version_spec"]
        assert len(pkg) == 1
        assert pkg[0].entity == "webapp"
        assert pkg[0].value == "==3.1"
        assert pkg[0].constraint_source == "rfc-x#01"

    def test_numeric_anchor_reuses_firewall_extractor(self):
        tuples = extract_assertions("Độ trễ đo được 12 ms [layer_a:lat.v1].")
        nums = [t for t in tuples if t.attribute == "numeric"]
        assert any(t.value == "12 ms" and t.entity == "unit" for t in nums)
        assert all(t.constraint_source == "layer_a:lat.v1" for t in nums)

    def test_key_value_config_extracted(self):
        tuples = extract_assertions("Đặt max_connections=200 cho cụm chính [rfc-y#02].")
        kv = [t for t in tuples if t.attribute == "config"]
        assert len(kv) == 1
        assert (kv[0].entity, kv[0].value) == ("max_connections", "200")

    def test_key_value_does_not_swallow_package_spec(self):
        # 'webapp==3.1' phải ra version_spec, KHÔNG ra config 'webapp=...'
        tuples = extract_assertions("Nâng webapp==3.1 [rfc-x#01].")
        assert all(t.attribute != "config" for t in tuples)

    def test_uncited_sentence_yields_empty_source(self):
        tuples = extract_assertions("Cụm cần 3 replicas với độ trễ 12 ms.")
        assert tuples and all(t.constraint_source == "" for t in tuples)

    def test_citation_tokens_not_extracted_as_values(self):
        # Nội dung trong [..] là metadata — không được bóc thành assertion
        tuples = extract_assertions("Xem nguồn [rfc9110#042-3fa9c1d2].")
        assert tuples == []

    def test_extract_citations_both_forms(self):
        text = "a [rfc-x#01] b [layer_a:quorum.v1] c"
        assert extract_citations(text) == ["rfc-x#01", "layer_a:quorum.v1"]

    def test_sentence_split_does_not_break_versions(self):
        sents = split_sentences("Dùng bản 2.4.1 nhé. Câu hai.")
        assert len(sents) == 2
        assert "2.4.1" in sents[0]


# --- NE1: số không khớp Layer A ------------------------------------------------

class TestNE1:
    def test_matching_numbers_pass(self):
        assert check_ne1_numeric(PROSE_OK, LA, [NODE_OK["content"]]) == []

    def test_mutated_number_fails(self):
        v = check_ne1_numeric("Hệ đạt 13 ms [layer_a:lat.v1].", LA, [])
        assert len(v) == 1
        assert v[0].never_event == "NE1"
        assert "13 ms" in v[0].subject

    def test_layer_a_source_text_contains_all_values(self):
        text = layer_a_source_text(LA)
        assert "12 ms" in text and "libssl==1.0 x webapp>=3.0" in text


# --- NE2: sót hard block (completeness chiều ngược) ----------------------------

class TestNE2:
    def test_block_present_passes(self):
        assert check_ne2_completeness(PROSE_OK, LA) == []

    def test_missing_block_fails_with_block_id(self):
        v = check_ne2_completeness("Mọi thứ ổn, cứ triển khai.", LA)
        assert len(v) == 1
        assert v[0].never_event == "NE2"
        assert "B1" in v[0].detail

    def test_whitespace_difference_still_matches(self):
        prose = "Cấm  libssl==1.0   x   webapp>=3.0  nhé."
        assert check_ne2_completeness(prose, LA) == []


# --- NE3: L2 đè L1-security thiếu conflict_flag --------------------------------

L1_SEC = {"node_id": "iso#01", "layer": "L1_canonical", "domain": "security",
          "conflict_flag": None, "content": "TLS 1.2 minimum"}
L2_SEC_NOFLAG = {"node_id": "local#01", "layer": "L2_local_runbook", "domain": "security",
                 "conflict_flag": None, "content": "site allows TLS 1.0 on legacy"}
L2_SEC_FLAGGED = {**L2_SEC_NOFLAG, "conflict_flag": "overrides iso#01 per waiver W-7"}


class TestNE3:
    def test_l2_security_without_flag_violates(self):
        v = check_ne3_conflict_flags([L1_SEC, L2_SEC_NOFLAG])
        assert len(v) == 1
        assert v[0].never_event == "NE3"
        assert v[0].subject == "local#01"

    def test_l2_with_conflict_flag_passes(self):
        assert check_ne3_conflict_flags([L1_SEC, L2_SEC_FLAGGED]) == []

    def test_l2_nonsecurity_domain_not_flagged_is_fine(self):
        pkg_l2 = {"node_id": "local#02", "layer": "L2_local_runbook",
                  "domain": "packaging", "conflict_flag": None, "content": "x"}
        assert check_ne3_conflict_flags([L1_SEC, pkg_l2]) == []

    def test_no_l1_security_in_set_means_no_override(self):
        assert check_ne3_conflict_flags([L2_SEC_NOFLAG]) == []


# --- NE4: chỉ thị actionable thiếu citation ------------------------------------

class TestNE4:
    def test_directive_with_citation_passes(self):
        assert check_ne4_citations("Deploy bản build mới [rfc-x#01].") == []

    def test_directive_without_citation_violates(self):
        v = check_ne4_citations("Deploy bản build mới ngay hôm nay.")
        assert len(v) == 1 and v[0].never_event == "NE4"

    def test_vietnamese_directive_detected(self):
        v = check_ne4_citations("Tiến hành nâng cấp cụm chính trong đêm.")
        assert len(v) == 1

    def test_non_directive_prose_needs_no_citation(self):
        assert check_ne4_citations("Kiến trúc hiện tại gồm ba cụm chính.") == []

    def test_strict_mode_action_section_requires_citation_every_sentence(self):
        prose = "## Action\nCân nhắc phương án chuyển đổi dần.\n## Notes\nTự do."
        assert check_ne4_citations(prose, strict=False) == []      # không động từ chỉ thị
        v = check_ne4_citations(prose, strict=True)                 # strict: vẫn phải cite
        assert len(v) == 1 and "Cân nhắc" in v[0].subject


# --- NE5: citation mồ côi / ngoài retrieval set ---------------------------------

class TestNE5:
    def test_valid_citations_resolve(self):
        assert check_ne5_resolve(PROSE_OK, KB_IDS, {"rfc-x#01"}, FORMULAS) == []

    def test_nonexistent_node_is_fabricated_citation(self):
        v = check_ne5_resolve("Xem [ghost#99].", KB_IDS, {"rfc-x#01"}, FORMULAS)
        assert len(v) == 1 and v[0].never_event == "NE5"
        assert "bịa" in v[0].detail

    def test_real_node_outside_retrieval_set_violates(self):
        v = check_ne5_resolve("Xem [rfc-y#02].", KB_IDS, {"rfc-x#01"}, FORMULAS)
        assert len(v) == 1
        assert "retrieval set" in v[0].detail

    def test_unknown_formula_id_violates(self):
        v = check_ne5_resolve("Số [layer_a:ghost.v9].", KB_IDS, {"rfc-x#01"}, FORMULAS)
        assert len(v) == 1 and v[0].subject == "layer_a:ghost.v9"


# --- Agent-R: reconcile + vòng rewrite có trần ----------------------------------

class TestReconcile:
    def test_clean_prose_verified(self):
        verdict = reconcile(PROSE_OK, LA, [NODE_OK], KB_IDS, FORMULAS)
        assert verdict.passed is True
        assert verdict.final_state == "CO_VERIFIED"
        assert verdict.never_events_triggered == []

    def test_ne3_escalates_immediately_no_rewrite(self):
        verdict = reconcile(PROSE_OK, LA, [NODE_OK, L1_SEC, L2_SEC_NOFLAG], KB_IDS, FORMULAS)
        assert verdict.final_state == "CO_ESCALATED"
        assert "NE3" in verdict.never_events_triggered
        assert verdict.rewrite_count == 0

    def test_ne1_first_failure_is_rejected_for_rewrite(self):
        bad = PROSE_OK.replace("12 ms", "13 ms")
        verdict = reconcile(bad, LA, [NODE_OK], KB_IDS, FORMULAS)
        assert verdict.final_state == "CO_REJECTED"
        assert "NE1" in verdict.never_events_triggered

    def test_ne2_persisting_after_one_reminder_escalates(self):
        no_block = "Hệ đạt latency_target 12 ms [layer_a:lat.v1]."
        verdict = reconcile(no_block, LA, [NODE_OK], KB_IDS, FORMULAS, rewrite_count=1)
        assert verdict.final_state == "CO_ESCALATED"
        assert "NE2" in verdict.never_events_triggered

    def test_loop_fix_on_second_attempt_verifies(self):
        drafts = iter([PROSE_OK.replace("12 ms", "13 ms"), PROSE_OK])

        def gen(violations):
            return next(drafts)

        verdict, prose = run_reconcile_loop(gen, LA, [NODE_OK], KB_IDS, FORMULAS)
        assert verdict.final_state == "CO_VERIFIED"
        assert verdict.rewrite_count == 1
        assert prose == PROSE_OK

    def test_loop_never_fixing_hits_cap_and_escalates(self):
        calls = []

        def gen(violations):
            calls.append(list(violations))
            return PROSE_OK.replace("12 ms", "13 ms")

        verdict, _ = run_reconcile_loop(gen, LA, [NODE_OK], KB_IDS, FORMULAS)
        assert verdict.final_state == "CO_ESCALATED"
        assert verdict.rewrite_count == MAX_REWRITES
        assert len(calls) == MAX_REWRITES + 1          # 1 bản đầu + 2 lần viết lại, không hơn
        assert calls[1] and calls[1][0].never_event == "NE1"  # lần sau nhận violation lần trước

    def test_layer_a_immutable_through_loop(self):
        before = LA.model_dump()

        def gen(violations):
            return PROSE_OK

        run_reconcile_loop(gen, LA, [NODE_OK], KB_IDS, FORMULAS)
        assert LA.model_dump() == before

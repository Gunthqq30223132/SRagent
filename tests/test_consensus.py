"""BS4 §9 — test offline bắt buộc cho Consensus Generator. LLM mock toàn bộ."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from tools import consensus_run
from tools.consensus_ledger import (
    UNMAPPED,
    Claim,
    assign_direction,
    band_rob_overall,
    build_anchor_set,
    build_ledger,
    check_narrative,
    detect_conflicts,
    render_excluded,
    render_table,
    rob_weight,
)
from tools.protocol_build import OutcomeSpec, PicoConcept, ReviewProtocol

RUN = "sr-20260728-t01"
UID_1 = "arxiv:2401.0001"
UID_2 = "arxiv:2401.0002"


@pytest.fixture
def store(tmp_path):
    with StagingStore(tmp_path / "t.db") as s:
        yield s


def _protocol(**kw) -> ReviewProtocol:
    base = dict(
        topic_vi="test",
        population=PicoConcept(concept="A"),
        intervention=PicoConcept(concept="B"),
        exclusion_criteria=[],
        outcomes=[
            OutcomeSpec(
                id="recovery",
                label_en="Recovery time",
                match_fields=["recovery_time"],
                direction_terms={
                    "decrease": ["reduc", "shorten"],
                    "increase": ["prolong"],
                    "no_difference": ["no significant difference"],
                },
            )
        ],
        unit_lexicon=["mg", "min"],
    )
    base.update(kw)
    return ReviewProtocol(**base)


def _ext(uid, field, value, quote, verified=1):
    return {"uid": uid, "field": field, "value": value, "quote": quote, "verified": verified}


# --- (a) đầu vào ledger ---------------------------------------------------------------


def test_ledger_admits_only_verified_one():
    rows = [
        _ext(UID_1, "recovery_time", "10 min", "reduced by 10 min", verified=1),
        _ext(UID_1, "recovery_time", "99 min", "unverifiable", verified=2),
        _ext(UID_1, "recovery_time", "88 min", "killed", verified=0),
    ]
    claims = build_ledger(rows, {UID_1: "Low"}, _protocol(), RUN)
    assert [c.value for c in claims] == ["10 min"]


def test_human_overall_beats_machine(store):
    doc = Document(uid=UID_1, source="arxiv", source_id=UID_1, authority_tier=1, title="t")
    doc.status = DocStatus.QUEUED
    store.upsert(doc)
    store.add_rob_assessment(UID_1, "rob_a", "m", "RCT", "__overall__", "High")
    store.add_rob_assessment(UID_1, "human", "human", "RCT", "__overall__", "Low")

    assert consensus_run.collect_rob_map(store, [UID_1]) == {UID_1: "Low"}


# --- (b) VOID / không quy đổi được ⇒ weight 0 nhưng KHÔNG biến mất --------------------


def test_void_stays_in_ledger_with_zero_weight():
    rows = [_ext(UID_1, "recovery_time", "10 min", "reduced by 10 min")]
    claims = build_ledger(rows, {UID_1: "VOID"}, _protocol(), RUN)
    assert len(claims) == 1
    assert claims[0].weight == 0.0
    assert UID_1 in render_excluded(claims)


def test_minors_score_without_bands_is_unbanded_not_guessed():
    """Đối kháng PM: điểm MINORS ("18") KHÔNG được tự quy đổi thành Low/High.

    Quy đổi điểm sang nhãn là phán định lâm sàng (luật PM-Owned). Không khai
    `minors_bands` ⇒ weight 0 + hiện trong Excluded, chứ không im lặng cho 1.0.
    """
    claims = build_ledger(
        [_ext(UID_1, "recovery_time", "10 min", "reduced by 10 min")],
        {UID_1: "18"},
        _protocol(),
        RUN,
    )
    assert claims[0].weight == 0.0
    assert "chưa quy đổi được" in render_excluded(claims)


def test_minors_bands_when_declared_are_honoured():
    proto = _protocol()
    object.__setattr__(proto, "minors_bands", {"Low": 17, "Some concerns": 13})
    assert band_rob_overall("18", {"Low": 17, "Some concerns": 13}) == "Low"
    assert band_rob_overall("14", {"Low": 17, "Some concerns": 13}) == "Some concerns"
    assert band_rob_overall("5", {"Low": 17, "Some concerns": 13}) == "High"


def test_rob_weight_is_fail_closed():
    assert rob_weight("Low") == 1.0
    assert rob_weight("Some concerns") == 0.5
    assert rob_weight("High") == 0.25
    assert rob_weight("VOID") == 0.0
    with pytest.raises(ValueError, match="không nhận diện được"):
        rob_weight("probably fine")


# --- (c) direction tất định ----------------------------------------------------------


class TestDirection:
    TERMS = {"decrease": ["reduc"], "increase": ["prolong"]}

    def test_single_group_match_assigns(self):
        assert assign_direction("significantly reduced pain", self.TERMS) == "decrease"

    def test_two_group_match_returns_none(self):
        assert assign_direction("reduced X but prolonged Y", self.TERMS) is None

    def test_no_terms_returns_none(self):
        assert assign_direction("reduced pain", None) is None
        assert assign_direction("reduced pain", {}) is None

    def test_no_match_returns_none(self):
        assert assign_direction("unrelated sentence", self.TERMS) is None


def test_unmapped_field_never_gets_direction():
    claims = build_ledger(
        [_ext(UID_1, "some_other_field", "10 min", "reduced by 10 min")],
        {UID_1: "Low"},
        _protocol(),
        RUN,
    )
    assert claims[0].outcome_id == UNMAPPED
    assert claims[0].direction is None


# --- (d) phát hiện xung đột ----------------------------------------------------------


def _claims_pair(dir_a, dir_b, weight=1.0):
    return [
        Claim(claim_id=f"clm-{RUN}-001", run_id=RUN, outcome_id="recovery", uid=UID_1,
              field="recovery_time", value="10 min", quote="q", rob_overall="Low",
              weight=weight, direction=dir_a),
        Claim(claim_id=f"clm-{RUN}-002", run_id=RUN, outcome_id="recovery", uid=UID_2,
              field="recovery_time", value="20 min", quote="q", rob_overall="Low",
              weight=weight, direction=dir_b),
    ]


def test_opposing_directions_form_conflict_group():
    claims = detect_conflicts(_claims_pair("increase", "decrease"))
    assert all(c.conflict_group == "cfl-recovery" for c in claims)


def test_no_difference_conflicts_with_a_direction():
    claims = detect_conflicts(_claims_pair("no_difference", "decrease"))
    assert all(c.conflict_group == "cfl-recovery" for c in claims)


def test_same_direction_is_not_marked_consistent():
    claims = detect_conflicts(_claims_pair("decrease", "decrease"))
    assert all(c.conflict_group is None for c in claims)


def test_null_direction_never_creates_conflict():
    claims = detect_conflicts(_claims_pair(None, "decrease"))
    assert all(c.conflict_group is None for c in claims)


def test_zero_weight_claims_excluded_from_conflict_detection():
    claims = detect_conflicts(_claims_pair("increase", "decrease", weight=0.0))
    assert all(c.conflict_group is None for c in claims)


def test_conflict_block_is_rendered_separately():
    table = render_table(detect_conflicts(_claims_pair("increase", "decrease")))
    assert "CONFLICTING — not pooled" in table


# --- (e)(f)(g)(h) tường lửa narrative -------------------------------------------------


@pytest.fixture
def one_claim():
    return [
        Claim(claim_id=f"clm-{RUN}-001", run_id=RUN, outcome_id="recovery", uid=UID_1,
              field="recovery_time", value="10 min", quote="q", rob_overall="Low",
              weight=1.0, direction="decrease")
    ]


def test_ne1_rejects_number_absent_from_ledger(one_claim):
    anchors = build_anchor_set(one_claim, ["min"])
    problems = check_narrative(
        f"Recovery fell by 47 min [clm-{RUN}-001].", one_claim, anchors
    )
    assert any(p.startswith("NE1") for p in problems)


def test_ne1_accepts_number_present_in_ledger(one_claim):
    anchors = build_anchor_set(one_claim, ["min"])
    assert check_narrative(
        f"Recovery fell by 10 min [clm-{RUN}-001].", one_claim, anchors
    ) == []


def test_claim_id_digits_are_not_treated_as_data(one_claim):
    """Đối kháng PM: chữ số bên trong [clm-...] KHÔNG được tính là số liệu.

    Nếu quên bóc token trích dẫn trước NE1 thì mọi narrative đúng đều bị reject
    và hệ rơi fallback vĩnh viễn — hỏng âm thầm, test thường không bắt được.
    """
    anchors = build_anchor_set(one_claim, ["min"])
    assert check_narrative(f"No numbers here [clm-{RUN}-001].", one_claim, anchors) == []


def test_medical_dose_fabrication_is_caught(one_claim):
    """Đối kháng PM: NE1 phải bắt được số Y KHOA bịa, không chỉ số miền CS.

    `extract_anchors` của tools/guard chỉ nhận diện mỏ neo CS (IP/version/%/GB/ms).
    Với "500 mg" nó trả RỖNG — nếu NE1 chỉ dựa vào nó thì liều thuốc bịa đi thẳng
    vào báo cáo. Đây là failure mode chết người của SR gây mê, khóa lại bằng test.
    """
    from tools.guard.firewall import extract_anchors

    assert extract_anchors("500 mg") == []  # tiền đề: firewall dùng chung mù ca này

    claim = one_claim[0].model_copy(update={"value": "50 mg"})
    anchors = build_anchor_set([claim], ["mg"])
    problems = check_narrative(
        f"The dose was 500 mg [clm-{RUN}-001].", [claim], anchors
    )
    assert any(p.startswith("NE1") for p in problems)
    assert check_narrative(f"The dose was 50 mg [clm-{RUN}-001].", [claim], anchors) == []


def test_substring_number_does_not_slip_through(one_claim):
    """Ledger có '100' mà LLM viết '10' ⇒ phải reject (membership, không substring)."""
    claim = one_claim[0].model_copy(update={"value": "100 min"})
    anchors = build_anchor_set([claim], ["min"])
    problems = check_narrative(f"Fell by 10 min [clm-{RUN}-001].", [claim], anchors)
    assert any(p.startswith("NE1") for p in problems)


def test_approximation_word_next_to_number_is_rejected(one_claim):
    anchors = build_anchor_set(one_claim, ["min"])
    problems = check_narrative(
        f"Recovery fell by approximately 10 min [clm-{RUN}-001].", one_claim, anchors
    )
    assert any(p.startswith("LINT") for p in problems)


def test_ne2_rejects_narrative_that_hides_a_conflict():
    claims = detect_conflicts(_claims_pair("increase", "decrease"))
    anchors = build_anchor_set(claims, ["min"])
    problems = check_narrative(
        f"One study reported 10 min [clm-{RUN}-001].", claims, anchors
    )
    assert any(p.startswith("NE2") for p in problems)


def test_ne2_passes_when_both_sides_share_a_sentence():
    claims = detect_conflicts(_claims_pair("increase", "decrease"))
    anchors = build_anchor_set(claims, ["min"])
    text = (
        f"Findings conflict: 10 min [clm-{RUN}-001] versus 20 min [clm-{RUN}-002]."
    )
    assert [p for p in check_narrative(text, claims, anchors) if p.startswith("NE2")] == []


def test_ne4_rejects_number_without_citation(one_claim):
    anchors = build_anchor_set(one_claim, ["min"])
    problems = check_narrative("Recovery fell by 10 min.", one_claim, anchors)
    assert any(p.startswith("NE4") for p in problems)


def test_ne5_rejects_orphan_citation(one_claim):
    anchors = build_anchor_set(one_claim, ["min"])
    problems = check_narrative(
        f"Recovery fell by 10 min [clm-{RUN}-001] [clm-{RUN}-999].", one_claim, anchors
    )
    assert any(p.startswith("NE5") for p in problems)


# --- (i)(j)(k) CLI end-to-end (LLM mock) ----------------------------------------------


def _write_protocol(tmp_path: Path) -> Path:
    p = tmp_path / "proto.json"
    p.write_text(
        json.dumps(
            {
                "topic_vi": "test",
                "population": {"concept": "A"},
                "intervention": {"concept": "B"},
                "exclusion_criteria": [],
                "outcomes": [
                    {
                        "id": "recovery",
                        "label_en": "Recovery",
                        "match_fields": ["recovery_time"],
                        "direction_terms": {"decrease": ["reduc"]},
                    }
                ],
                "unit_lexicon": ["min"],
            }
        ),
        encoding="utf-8",
    )
    return p


def _seed_run(store, proto_path: Path, state="CONSENSUS_READY", approved=True):
    sha = hashlib.sha256(proto_path.read_bytes()).hexdigest()
    store.conn.execute(
        """INSERT INTO sr_runs (run_id, query, protocol_path, protocol_sha256,
                                state, created_at)
           VALUES (?,?,?,?,?, datetime('now'))""",
        (RUN, "q", str(proto_path), sha, state),
    )
    doc = Document(uid=UID_1, source="arxiv", source_id=UID_1, authority_tier=1, title="t")
    doc.status = DocStatus.QUEUED
    store.upsert(doc)
    store.log_event(UID_1, "ROB_COMPLETED", "", run_id=RUN)
    store.add_rob_assessment(UID_1, "rob_a", "m", "RCT", "__overall__", "Low")
    store.add_extraction(UID_1, "recovery_time", "10 min", "reduced by 10 min", "abstract", 1)
    if approved:
        store.log_event(f"consensus:{RUN}", "CONSENSUS_APPROVED", "human gate", run_id=RUN)
    store.conn.commit()


class _BadLLM:
    """Luôn trả narrative vi phạm ⇒ ép hệ đi hết 3 lượt rồi rơi fallback."""

    model = "mock"

    def generate_structured(self, system, user, schema, num_ctx=None):
        return schema(narrative="Recovery fell by 999 min with no citation.")


def test_fallback_after_two_rewrites_still_produces_report(store, tmp_path, monkeypatch):
    proto = _write_protocol(tmp_path)
    _seed_run(store, proto)
    out = tmp_path / "report.md"
    monkeypatch.setattr(consensus_run, "StagingStore", lambda *a, **k: store)
    monkeypatch.setattr(consensus_run, "OllamaClient", lambda *a, **k: _BadLLM())

    rc = consensus_run.main(
        ["--protocol", str(proto), "--run", RUN, "--out", str(out)]
    )
    assert rc == 0
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "mode" in text and "fallback" in text

    events = [
        r["event_type"]
        for r in store.conn.execute(
            "SELECT event_type FROM events WHERE run_id = ?", (RUN,)
        ).fetchall()
    ]
    assert "CONSENSUS_NARRATIVE_FALLBACK" in events
    assert "CONSENSUS_COMPLETED" in events
    assert store.conn.execute(
        "SELECT state FROM sr_runs WHERE run_id = ?", (RUN,)
    ).fetchone()["state"] == "CLOSED"
    # Ledger được ghi TRƯỚC narrative — sự thật tồn tại độc lập với văn bản.
    assert store.conn.execute(
        "SELECT COUNT(*) n FROM consensus_claim WHERE run_id = ?", (RUN,)
    ).fetchone()["n"] == 1


def test_gate_blocks_without_consensus_approved(store, tmp_path, monkeypatch, capsys):
    proto = _write_protocol(tmp_path)
    _seed_run(store, proto, approved=False)
    monkeypatch.setattr(consensus_run, "StagingStore", lambda *a, **k: store)

    rc = consensus_run.main(["--protocol", str(proto), "--run", RUN, "--no-llm"])
    assert rc == 2
    assert "CONSENSUS_APPROVED" in capsys.readouterr().err
    # Không ghi gì khi bị từ chối.
    assert store.conn.execute(
        "SELECT COUNT(*) n FROM consensus_claim"
    ).fetchone()["n"] == 0


def test_gate_blocks_on_wrong_state(store, tmp_path, monkeypatch, capsys):
    proto = _write_protocol(tmp_path)
    _seed_run(store, proto, state="OPEN")
    monkeypatch.setattr(consensus_run, "StagingStore", lambda *a, **k: store)

    rc = consensus_run.main(["--protocol", str(proto), "--run", RUN, "--no-llm"])
    assert rc == 2
    assert "CONSENSUS_READY" in capsys.readouterr().err


def test_gate_blocks_on_protocol_sha_drift(store, tmp_path, monkeypatch, capsys):
    proto = _write_protocol(tmp_path)
    _seed_run(store, proto)
    # Protocol đổi SAU khi người chốt ⇒ phê duyệt mất hiệu lực.
    proto.write_text(proto.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    monkeypatch.setattr(consensus_run, "StagingStore", lambda *a, **k: store)

    rc = consensus_run.main(["--protocol", str(proto), "--run", RUN, "--no-llm"])
    assert rc == 2
    assert "protocol_sha256" in capsys.readouterr().err


def test_closed_run_cannot_be_rerun(store, tmp_path, monkeypatch, capsys):
    proto = _write_protocol(tmp_path)
    _seed_run(store, proto, state="CLOSED")
    monkeypatch.setattr(consensus_run, "StagingStore", lambda *a, **k: store)

    rc = consensus_run.main(["--protocol", str(proto), "--run", RUN, "--no-llm"])
    assert rc == 2
    assert "CLOSED" in capsys.readouterr().err


def test_no_llm_path_produces_deterministic_report(store, tmp_path, monkeypatch):
    """Đường thoát không-LLM luôn ra báo cáo — không có chế độ 'chờ LLM'."""
    proto = _write_protocol(tmp_path)
    _seed_run(store, proto)
    out = tmp_path / "r.md"
    monkeypatch.setattr(consensus_run, "StagingStore", lambda *a, **k: store)

    rc = consensus_run.main(
        ["--protocol", str(proto), "--run", RUN, "--out", str(out), "--no-llm"]
    )
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "10 min" in text
    assert f"clm-{RUN}-001" in text


# --- Mối nối phase graph (bug tích hợp, unit test từng stage không bắt được) ----------


class TestPhaseWiring:
    """Đối kháng PM: hai stage cuối phải được gọi ĐÚNG THAM SỐ từ orchestrator.

    Cả hai lỗi dưới đây đều 'xanh' ở mọi test cấp stage vì stage tự nó không sai —
    chỗ sai là dòng lệnh mà sr_run dựng cho nó.
    """

    def _phase(self, name):
        from tools.sr_run import build_phases

        return next(p for p in build_phases() if p.name == name)

    def test_extract_receives_protocol(self, tmp_path):
        """Thiếu --protocol ⇒ evidence_extract rơi về taxonomy CS trên corpus y khoa."""
        import argparse

        args = argparse.Namespace(protocol=tmp_path / "p.json", limit=10)
        argv = self._phase("extract").build_args(args)
        assert "--protocol" in argv

    def test_consensus_receives_run_id_from_env(self, tmp_path, monkeypatch):
        """--run là bắt buộc của consensus_run; run mới chỉ có run_id trong env."""
        import argparse

        monkeypatch.setenv("SR_RUN_ID", RUN)
        args = argparse.Namespace(protocol=tmp_path / "p.json", limit=10, run=None)
        argv = self._phase("consensus").build_args(args)
        assert argv[argv.index("--run") + 1] == RUN


# --- Protocol validation --------------------------------------------------------------


def test_field_claimed_by_two_outcomes_is_rejected_at_load():
    with pytest.raises(ValueError, match="hai outcome cùng nhận"):
        _protocol(
            outcomes=[
                OutcomeSpec(id="o1", label_en="A", match_fields=["shared"]),
                OutcomeSpec(id="o2", label_en="B", match_fields=["shared"]),
            ]
        )

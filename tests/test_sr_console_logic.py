"""D37 §3 — test offline cho logic SR Console (không cần Streamlit runtime)."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from tools.rob_run import quote_lacks_pertinence
from ui import console_logic as logic

RUN_A = "sr-20260728-aaa"
RUN_B = "sr-20260728-bbb"


@pytest.fixture
def store(tmp_path):
    with StagingStore(tmp_path / "t.db") as s:
        yield s


def _mk_run(store, run_id, state=logic.STATE_OPEN, sha="deadbeef"):
    store.conn.execute(
        """INSERT INTO sr_runs (run_id, query, protocol_path, protocol_sha256,
                                state, created_at)
           VALUES (?,?,?,?,?, datetime('now'))""",
        (run_id, f"query {run_id}", "p.json", sha, state),
    )
    store.conn.commit()


def _mk_doc(store, uid, score=50.0):
    doc = Document(
        uid=uid, source="arxiv", source_id=uid, authority_tier=1,
        title=f"title {uid}", abstract="abstract",
    )
    doc.status = DocStatus.QUEUED
    store.upsert(doc)
    # rubric_score là cột dẫn xuất trong bảng documents — set thẳng để cố định thứ tự.
    store.conn.execute(
        "UPDATE documents SET rubric_score = ? WHERE uid = ?", (score, uid)
    )
    store.conn.commit()


# --- (a) danh sách escalation: đúng run + đúng thứ tự ---------------------------------


def test_escalation_list_is_run_scoped_and_ordered(store):
    _mk_run(store, RUN_A)
    _mk_run(store, RUN_B)
    for uid, score in [("arxiv:2401.0001", 10.0), ("arxiv:2401.0002", 90.0), ("arxiv:2401.0003", 20.0)]:
        _mk_doc(store, uid, score)
        store.log_event(uid, "ROB_ESCALATED", "mismatch", run_id=RUN_A)
    store.log_event("arxiv:2401.0003", "ROB_PERTINENCE_FLAG", "rob_a:d1", run_id=RUN_A)

    # Doc của run khác tuyệt đối không lọt vào hàng đợi của RUN_A.
    _mk_doc(store, "arxiv:2401.0004", 99.0)
    store.log_event("arxiv:2401.0004", "ROB_ESCALATED", "mismatch", run_id=RUN_B)

    items = logic.list_rob_escalations(store, RUN_A)
    assert [i["uid"] for i in items] == ["arxiv:2401.0003", "arxiv:2401.0002", "arxiv:2401.0001"]
    assert "arxiv:2401.0004" not in [i["uid"] for i in items]


def test_adjudicated_doc_leaves_the_queue(store):
    _mk_run(store, RUN_A)
    _mk_doc(store, "arxiv:2401.1001")
    store.log_event("arxiv:2401.1001", "ROB_ESCALATED", "mismatch", run_id=RUN_A)
    assert len(logic.list_rob_escalations(store, RUN_A)) == 1

    time.sleep(0.01)  # đảm bảo created_at của completion > của escalation
    store.log_event("arxiv:2401.1001", "ROB_COMPLETED", "human adjudication", run_id=RUN_A)
    assert logic.list_rob_escalations(store, RUN_A) == []


def test_completion_in_another_run_does_not_clear_debt(store):
    """Đối kháng: phán định ở run khác KHÔNG được rửa nợ escalation của run này."""
    _mk_run(store, RUN_A)
    _mk_run(store, RUN_B)
    _mk_doc(store, "arxiv:2401.1001")
    store.log_event("arxiv:2401.1001", "ROB_ESCALATED", "mismatch", run_id=RUN_A)
    time.sleep(0.01)
    store.log_event("arxiv:2401.1001", "ROB_COMPLETED", "human adjudication", run_id=RUN_B)

    assert [i["uid"] for i in logic.list_rob_escalations(store, RUN_A)] == ["arxiv:2401.1001"]


# --- (b)(f) lưu phán định: đủ rows + overall tất định ---------------------------------


def test_save_adjudication_writes_rows_and_machine_overall(store):
    _mk_run(store, RUN_A)
    _mk_doc(store, "arxiv:2401.1001")
    verdicts = {
        "d1_randomization": "Low",
        "d2_deviations": "Low",
        "d3_missing_outcome": "Some concerns",
        "d4_measurement": "Low",
        "d5_selection": "Low",
    }
    overall = logic.save_human_adjudication(store, "arxiv:2401.1001", "RCT", verdicts, RUN_A)

    assert overall == "Some concerns"  # máy tính, không phải người gõ
    rows = [r for r in store.get_rob_assessments("arxiv:2401.1001") if r["agent"] == "human"]
    assert len(rows) == 6  # 5 domain + __overall__
    stored_overall = [r for r in rows if r["domain"] == "__overall__"][0]
    assert stored_overall["verdict"] == "Some concerns"

    evs = store.conn.execute(
        "SELECT event_type, run_id FROM events WHERE uid = 'arxiv:2401.1001'"
    ).fetchall()
    assert ("ROB_COMPLETED", RUN_A) in [(e["event_type"], e["run_id"]) for e in evs]


def test_human_void_stays_void(store):
    """VOID người chọn KHÔNG được 'rửa' thành Low — doc phải rơi khỏi phần số BS4."""
    _mk_run(store, RUN_A)
    _mk_doc(store, "arxiv:2401.1001")
    verdicts = {
        "d1_randomization": "VOID",
        "d2_deviations": "Low",
        "d3_missing_outcome": "Low",
        "d4_measurement": "Low",
        "d5_selection": "Low",
    }
    assert logic.save_human_adjudication(store, "arxiv:2401.1001", "RCT", verdicts, RUN_A) == "VOID"


def test_missing_domain_refuses_to_compute_overall(store):
    _mk_run(store, RUN_A)
    _mk_doc(store, "arxiv:2401.1001")
    with pytest.raises(ValueError, match="Thiếu phán định"):
        logic.save_human_adjudication(
            store, "arxiv:2401.1001", "RCT", {"d1_randomization": "Low"}, RUN_A
        )


# --- (c)(d) cổng consensus ------------------------------------------------------------


def test_gate_blocked_while_escalation_pending(store):
    _mk_run(store, RUN_A)
    _mk_doc(store, "arxiv:2401.1001")
    store.log_event("arxiv:2401.1001", "ROB_ESCALATED", "mismatch", run_id=RUN_A)

    status = logic.consensus_gate_status(store, RUN_A)
    assert status["can_approve"] is False
    assert status["pending_escalations"] == 1
    assert any("chưa phân xử" in r for r in status["reasons"])

    with pytest.raises(ValueError, match="Không đủ điều kiện"):
        logic.approve_consensus(store, RUN_A)
    # Fail-closed: không được ghi gì khi bị từ chối.
    assert store.conn.execute(
        "SELECT COUNT(*) n FROM events WHERE event_type = 'CONSENSUS_APPROVED'"
    ).fetchone()["n"] == 0


def test_approve_writes_event_and_state(store):
    _mk_run(store, RUN_A)
    status = logic.consensus_gate_status(store, RUN_A)
    assert status["can_approve"] is True

    logic.approve_consensus(store, RUN_A)

    ev = store.conn.execute(
        "SELECT run_id FROM events WHERE event_type = 'CONSENSUS_APPROVED'"
    ).fetchone()
    assert ev["run_id"] == RUN_A
    state = store.conn.execute(
        "SELECT state FROM sr_runs WHERE run_id = ?", (RUN_A,)
    ).fetchone()["state"]
    assert state == logic.STATE_CONSENSUS_READY


def test_cannot_approve_twice(store):
    """Đối kháng PM: bấm chốt lần hai phải bị chặn — state đã rời OPEN."""
    _mk_run(store, RUN_A)
    logic.approve_consensus(store, RUN_A)
    with pytest.raises(ValueError, match="Không đủ điều kiện"):
        logic.approve_consensus(store, RUN_A)
    assert store.conn.execute(
        "SELECT COUNT(*) n FROM events WHERE event_type = 'CONSENSUS_APPROVED'"
    ).fetchone()["n"] == 1


def test_unverified_quotes_are_informational_not_blocking(store):
    _mk_run(store, RUN_A)
    _mk_doc(store, "arxiv:2401.1001")
    store.log_event("arxiv:2401.1001", "EXTRACT_COMPLETED", "", run_id=RUN_A)
    store.add_extraction("arxiv:2401.1001", "f", "v", "q", "abstract", 2)

    status = logic.consensus_gate_status(store, RUN_A)
    assert status["unverified_quotes"] == 1
    assert status["can_approve"] is True  # thông tin, KHÔNG chặn (D37 §1 Tab 3)


# --- (e) hủy run ----------------------------------------------------------------------


def test_abandon_requires_reason_and_sets_state(store):
    _mk_run(store, RUN_A)
    with pytest.raises(ValueError, match="lý do"):
        logic.abandon_run(store, RUN_A, "   ")

    logic.abandon_run(store, RUN_A, "sai protocol")
    assert store.conn.execute(
        "SELECT state FROM sr_runs WHERE run_id = ?", (RUN_A,)
    ).fetchone()["state"] == logic.STATE_ABANDONED


# --- writer lock ----------------------------------------------------------------------


def test_writes_blocked_while_orchestrator_holds_lock(store, tmp_path, monkeypatch):
    """Bất biến D37 §2.4: lockfile tồn tại ⇒ console read-only."""
    from unittest.mock import patch

    from sr_agent.store import writer_lock

    _mk_run(store, RUN_A)
    lock_file = tmp_path / ".sr_writer.lock"
    # PID 1 luôn sống trong container và khác PID test ⇒ lock hợp lệ của "tiến trình
    # khác". Dùng PID chết sẽ bị holder() dọn orphan và test thành rỗng.
    started = datetime.now(timezone.utc).isoformat()
    with patch.object(writer_lock, "DEFAULT_LOCK_PATH", lock_file):
        lock_file.write_text(
            f'{{"role": "orchestrator", "pid": 1, "started_at": "{started}"}}',
            encoding="utf-8",
        )
        with pytest.raises(logic.WriteLocked):
            logic.approve_consensus(store, RUN_A)


# --- D37 §4 pertinence lint -----------------------------------------------------------


class TestPertinenceLint:
    def test_quote_without_any_stem_is_flagged(self):
        assert quote_lacks_pertinence(
            "We used chain-of-thought prompting.", ["random", "allocat", "sequence"]
        ) is True

    def test_quote_with_one_stem_is_not_flagged(self):
        assert quote_lacks_pertinence(
            "Patients were randomly allocated to two arms.", ["random", "allocat"]
        ) is False

    def test_no_hints_disables_the_feature(self):
        assert quote_lacks_pertinence("anything at all", []) is False

    def test_matching_is_case_insensitive_substring_not_fuzzy(self):
        # 'Randomisation' chứa stem 'random' (substring) ⇒ không flag.
        assert quote_lacks_pertinence("Randomisation was concealed.", ["random"]) is False
        # 'randmo' KHÔNG phải substring ⇒ vẫn flag (không có fuzzy — bất biến #2).
        assert quote_lacks_pertinence("Randomisation was concealed.", ["randmo"]) is True

"""Test BS2 orchestrator (`tools/sr_run.py`) — offline, không Ollama/mạng.

Trọng tâm: **bất biến cổng người** (CLAUDE.md #6) — orchestrator không bao giờ
tự tạo trạng thái APPROVED; nó chỉ DỪNG và đọc quyết định của người.
"""
import argparse

import pytest

from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from tools import sr_run
from tools.sr_run import AUTO, HUMAN_GATE, Phase, build_phases, run_pipeline


def _doc(uid_num: str, status: DocStatus) -> Document:
    return Document(
        uid=f"arxiv:{uid_num}",
        source="arxiv",
        source_id=f"arxiv:{uid_num}",
        authority_tier=2,
        title="t",
        status=status,
    )


def _approved_doc(uid_num: str = "2401.12345") -> Document:
    return _doc(uid_num, DocStatus.APPROVED)


def _queued_doc(uid_num: str = "2402.54321") -> Document:
    return _doc(uid_num, DocStatus.QUEUED)


def _args(**kw) -> argparse.Namespace:
    base = dict(query="q", max_results=5, protocol="p.json", limit=3, start_from=None, db=None)
    base.update(kw)
    return argparse.Namespace(**base)


# --- đồ thị ------------------------------------------------------------------

def test_phase_graph_shape_and_gates():
    phases = build_phases()
    names = [p.name for p in phases]
    assert names == [
        "ingest", "review", "screen", "eligibility",
        "extract", "rob", "consensus_review", "consensus",
    ]
    gates = [p.name for p in phases if p.kind == HUMAN_GATE]
    assert gates == ["review", "consensus_review"]
    # ingest phải đứng TRƯỚC cổng review (không sàng lọc trước khi người duyệt).
    assert names.index("ingest") < names.index("review") < names.index("screen")


# --- bất biến cổng người -----------------------------------------------------

def test_ingest_then_halts_at_review_gate_never_approves(tmp_path):
    """Chạy từ đầu: ingest (giả) tạo doc QUEUED → DỪNG ở cổng review, và
    KHÔNG có doc nào thành APPROVED (orchestrator không tự duyệt)."""
    calls: list[str] = []

    def fake_ingest(argv):
        calls.append("ingest")
        with StagingStore(tmp_path / "t.db") as s:
            s.upsert(_queued_doc())
        return 0

    def fake_screen(argv):
        calls.append("screen")
        return 0

    phases = [
        Phase("ingest", AUTO, "ingest", build_args=lambda a: []),
        Phase("review", HUMAN_GATE, "duyệt", satisfied=sr_run._has_approved, resume_hint="screen"),
        Phase("screen", AUTO, "screen", build_args=lambda a: []),
    ]
    # tiêm runner giả (không đụng mạng)
    phases[0].resolve_runner = lambda: fake_ingest  # type: ignore[attr-defined]
    phases[2].resolve_runner = lambda: fake_screen  # type: ignore[attr-defined]

    with StagingStore(tmp_path / "t.db") as store:
        rc = run_pipeline(store, phases, _args(), start_from=None)
        assert rc == 0
        # ingest chạy, screen KHÔNG (bị chặn bởi cổng)
        assert calls == ["ingest"]
        # bất biến: không doc nào APPROVED, cổng chưa qua
        assert not sr_run._has_approved(store)
        counts = sr_run._status_counts(store)
        assert counts.get(DocStatus.APPROVED.value, 0) == 0
        assert counts.get(DocStatus.QUEUED.value) == 1


def test_gate_passes_only_when_human_state_present(tmp_path):
    """Cổng review chỉ 'đã qua' khi ĐỌC thấy doc APPROVED do người tạo."""
    calls: list[str] = []
    phases = [
        Phase("review", HUMAN_GATE, "duyệt", satisfied=sr_run._has_approved, resume_hint="screen"),
        Phase("screen", AUTO, "screen", build_args=lambda a: []),
    ]
    phases[1].resolve_runner = lambda: (lambda argv: calls.append("screen") or 0)  # type: ignore

    with StagingStore(tmp_path / "t.db") as store:
        store.upsert(_approved_doc())  # NGƯỜI đã duyệt (trạng thái có thật)
        rc = run_pipeline(store, phases, _args(), start_from="review")
        assert rc == 0
        assert calls == ["screen"]  # cổng thỏa → chạy tiếp


def test_cannot_skip_unsatisfied_gate_via_from(tmp_path):
    """--from screen KHÔNG cho lách cổng review chưa thỏa: phải từ chối (rc=2)."""
    calls: list[str] = []
    phases = [
        Phase("review", HUMAN_GATE, "duyệt", satisfied=sr_run._has_approved, resume_hint="screen"),
        Phase("screen", AUTO, "screen", build_args=lambda a: []),
    ]
    phases[1].resolve_runner = lambda: (lambda argv: calls.append("screen") or 0)  # type: ignore

    with StagingStore(tmp_path / "t.db") as store:
        # chỉ có QUEUED, chưa ai duyệt
        store.upsert(_queued_doc())
        rc = run_pipeline(store, phases, _args(), start_from="screen")
        assert rc == 2
        assert calls == []  # không được chạy screen khi cổng chưa thỏa


# --- lan truyền lỗi & ranh giới ---------------------------------------------

def test_auto_phase_failure_stops_pipeline(tmp_path):
    calls: list[str] = []
    phases = [
        Phase("a", AUTO, "a", build_args=lambda x: []),
        Phase("b", AUTO, "b", build_args=lambda x: []),
    ]
    phases[0].resolve_runner = lambda: (lambda argv: 3)  # type: ignore  # fail rc=3
    phases[1].resolve_runner = lambda: (lambda argv: calls.append("b") or 0)  # type: ignore

    with StagingStore(tmp_path / "t.db") as store:
        rc = run_pipeline(store, phases, _args(), start_from="a")
        assert rc == 3
        assert calls == []  # b không chạy sau khi a fail


def test_unimplemented_future_phase_halts_cleanly(tmp_path):
    """Phase tương lai (module chưa có) dừng sạch rc=0, không crash."""
    phases = [Phase("consensus", AUTO, "future",
                    runner_ref=("tools.__nonexistent_module__", "main"),
                    build_args=lambda a: [])]
    assert phases[0].is_available() is False
    with StagingStore(tmp_path / "t.db") as store:
        rc = run_pipeline(store, phases, _args(), start_from="consensus")
        assert rc == 0


def test_unknown_start_from_rejected(tmp_path):
    with StagingStore(tmp_path / "t.db") as store:
        rc = run_pipeline(store, build_phases(), _args(), start_from="nope")
        assert rc == 2


# --- smoke CLI ---------------------------------------------------------------

def test_plan_smoke(capsys):
    assert sr_run.main(["plan"]) == 0
    out = capsys.readouterr().out
    assert "CỔNG NGƯỜI" in out and "ingest" in out


def test_status_smoke(tmp_path, capsys):
    db = tmp_path / "t.db"
    with StagingStore(db) as store:
        store.upsert(_queued_doc())
    assert sr_run.main(["status", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "queued" in out and "chưa" in out


def test_run_from_scratch_requires_query():
    assert sr_run.main(["run"]) == 2  # thiếu --query và không --from

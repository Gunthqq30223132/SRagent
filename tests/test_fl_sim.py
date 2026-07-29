"""FL-SIM — harness E2E offline: chạy TRỌN tuyến SR với LLM mock ở tầng HTTP.

Vì sao tồn tại: 523 test kia đều ở cấp stage — mỗi stage đúng khi chạy riêng.
Nhưng cả họ bug FL-1 (F1–F3) và bốn bug tích hợp tìm được ngày 2026-07-29 đều
KHÔNG nằm trong stage nào cả; chúng nằm ở **mối nối** giữa các stage: dòng lệnh
orchestrator dựng, biến môi trường truyền qua, trạng thái run mà bước sau đọc.
Loại bug đó chỉ lộ ra khi cho cả chuỗi chạy liền một mạch.

Nguyên tắc thiết kế:
1. **Runner THẬT.** Không tiêm `resolve_runner` giả như `test_sr_run.py` — mục
   đích chính là chạy code thật của từng stage và mối nối giữa chúng.
2. **Mock ở tầng HTTP**, không mock `generate_structured`. Nhờ vậy prompt-building,
   num_ctx guard, structured-output parsing và xử lý lỗi đều là code thật chạy.
3. **Dispatch theo JSON schema** trong request (`format.title`) chứ không theo từ
   khóa prompt — prompt đổi chữ thì mock vẫn đúng.

Ghi chú bất biến #6: test này gọi `console_logic.approve_consensus` để mô phỏng cú
bấm của người. Đó là hợp lệ TRONG TEST — chính hàm cổng người đang được kiểm thử.
Nó nằm trong `tests/`, dùng DB tạm, không có CLI và không export helper nào để ai
đó lỡ import vào đường chạy thật.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store import writer_lock
from sr_agent.store.staging import StagingStore
from tools import sr_run
from ui import console_logic

OLLAMA = "http://localhost:11434"
ARXIV_API = "https://export.arxiv.org/api/query"
EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
IEEE_API = "https://ieeexploreapi.ieee.org/api/v1/search/articles"


def _mock_sources() -> None:
    """Nguồn trả RỖNG có chủ đích.

    Ingest vẫn chạy code thật (router → fetcher → dedup → rubric) và phải trả rc=0
    để chuỗi đi tiếp — đó là mối nối cần kiểm. Còn corpus thì gieo sẵn ở fixture:
    độ trung thực của parse Atom/JSON đã được `test_ingest.py`/`test_europepmc.py`
    phủ rồi, dựng lại ở đây chỉ thêm bề mặt vỡ mà không thêm độ phủ.
    """
    respx.get(ARXIV_API).mock(
        return_value=httpx.Response(
            200,
            text='<?xml version="1.0" encoding="UTF-8"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom"></feed>',
        )
    )
    respx.get(EPMC_SEARCH).mock(
        return_value=httpx.Response(200, json={"resultList": {"result": []}})
    )
    respx.get(IEEE_API).mock(return_value=httpx.Response(200, json={"articles": []}))

FULL_TEXT = (
    "Introduction. Postoperative recovery time matters after cardiac surgery. "
    "Methods. Patients were randomly assigned to sevoflurane or propofol. "
    "Allocation sequence was computer generated and concealed. "
    "Outcome assessors were blinded to allocation. "
    "No participants were lost to follow-up and all data were reported. "
    "Results. Recovery time was reduced by 10 min in the sevoflurane arm. "
    "Discussion. The reduction appears consistent across subgroups."
)

PROTOCOL = {
    "topic_vi": "gây mê hít và thời gian hồi tỉnh",
    "population": {"concept": "cardiac surgery"},
    "intervention": {"concept": "sevoflurane"},
    "comparison": {"concept": "propofol"},
    "outcome": {"concept": "recovery time"},
    "exclusion_criteria": ["ET1", "ET3"],
    "extraction_fields": [
        {"id": "recovery_time", "description_en": "Recovery time reported", "value_hint": "min"}
    ],
    "outcomes": [
        {
            "id": "recovery",
            "label_en": "Recovery time",
            "match_fields": ["recovery_time"],
            "direction_terms": {"decrease": ["reduc"], "increase": ["prolong"]},
        }
    ],
    "unit_lexicon": ["min", "mg"],
}


# --- Mock Ollama: dispatch theo schema, không theo từ khóa prompt ---------------------


def _response_for(schema_title: str, props: dict) -> dict:
    """Trả về payload hợp lệ cho từng schema mà các stage yêu cầu."""
    if schema_title == "ScreenVerdict":
        return {
            "verdict": "include",
            "criterion_id": None,
            "evidence_quote": None,
            # PHẢI là trích nguyên văn: screening chạy trên title+abstract, còn
            # eligibility chạy trên full_text — câu này có mặt trong CẢ HAI, nên
            # verify_quote pass ở cả hai chặng.
            "relevance_quote": "Recovery time was reduced by 10 min in the sevoflurane arm.",
            "confidence": "high",
        }
    if schema_title == "StudyTypeClassification":
        return {
            "study_type": "RCT",
            "evidence_quote": "Patients were randomly assigned to sevoflurane or propofol.",
        }
    if schema_title == "RoB2LLMResponse":
        quotes = {
            "d1_randomization": "Allocation sequence was computer generated and concealed.",
            "d2_deviations": "Patients were randomly assigned to sevoflurane or propofol.",
            "d3_missing_outcome": "No participants were lost to follow-up and all data were reported.",
            "d4_measurement": "Outcome assessors were blinded to allocation.",
            "d5_selection": "Recovery time was reduced by 10 min in the sevoflurane arm.",
        }
        out: dict = {"study_type": "RCT"}
        for domain, quote in quotes.items():
            out[domain] = {"verdict": "Low", "evidence_quote": quote}
        return out
    # EvidencedExtraction dựng động từ protocol (D40) — đọc chính properties gửi lên.
    return {
        field: {
            "value": "10 min",
            "quote": "Recovery time was reduced by 10 min in the sevoflurane arm.",
            "section": "full_text",
        }
        for field in props
    }


def _ollama_router(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    schema = body.get("format") or {}
    payload = _response_for(schema.get("title", ""), schema.get("properties", {}))
    return httpx.Response(
        200, json={"message": {"role": "assistant", "content": json.dumps(payload)}}
    )


def _mock_ollama() -> None:
    """Hai screener PHẢI khác model (CLAUDE.md) — /api/tags phải liệt kê đủ, nếu
    không screen_run rơi về single_model_mode và tuyến sau nhận 0 doc."""
    respx.get(f"{OLLAMA}/api/tags").mock(
        return_value=httpx.Response(
            200,
            json={
                "models": [
                    {"name": "llama3.1:8b", "digest": "sha256:a"},
                    {"name": "gemma4:e4b", "digest": "sha256:b"},
                    {"name": "qwen2.5:7b-instruct", "digest": "sha256:c"},
                ]
            },
        )
    )
    respx.post(f"{OLLAMA}/api/chat").mock(side_effect=_ollama_router)


@pytest.fixture
def sim(tmp_path, monkeypatch):
    """Cô lập tuyệt đối: DB tạm, lockfile tạm, thư mục làm việc tạm."""
    db = tmp_path / "sim.db"
    monkeypatch.setenv("SR_AGENT_DB", str(db))
    monkeypatch.setattr(writer_lock, "DEFAULT_LOCK_PATH", tmp_path / ".sr_writer.lock")
    # `sr_run` SET os.environ["SR_RUN_ID"] và không bao giờ dọn (tiến trình CLI thì
    # vô hại, nhưng trong pytest nó rò sang test sau và làm log_event gắn nhầm run).
    # Phải setenv chứ không delenv: delenv trên biến chưa tồn tại KHÔNG ghi nhận gì
    # để monkeypatch hoàn tác. Chuỗi rỗng an toàn — mọi chỗ đọc đều `... or None`.
    monkeypatch.setenv("SR_RUN_ID", "")

    proto = tmp_path / "proto.json"
    proto.write_text(json.dumps(PROTOCOL), encoding="utf-8")

    with StagingStore(db) as store:
        for i in range(3):
            doc = Document(
                uid=f"arxiv:2401.0000{i}",
                source="arxiv",
                source_id=f"arxiv:2401.0000{i}",
                authority_tier=1,
                title=f"Sevoflurane versus propofol trial {i}",
                abstract="Recovery time was reduced by 10 min in the sevoflurane arm.",
                full_text=FULL_TEXT,
            )
            doc.status = DocStatus.QUEUED
            store.upsert(doc)
    yield {"db": db, "proto": proto, "tmp": tmp_path}


def _run(argv: list[str]) -> int:
    return sr_run.main(argv)


# --- Kịch bản chính -------------------------------------------------------------------


@respx.mock
def test_full_chain_halts_at_human_gate_then_completes_after_approval(sim, monkeypatch):
    """Chạy screen→extract, DỪNG ở cổng người, người chốt, chạy tiếp ra báo cáo.

    Đây là kịch bản vận hành thật của FL-4 rút gọn. Nó khoá cùng lúc bốn mối nối
    từng hỏng: --db lan xuống stage, --protocol tới extract, --run tới consensus,
    và trạng thái CONSENSUS_READY được phép resume.
    """
    _mock_ollama()
    _mock_sources()

    db, proto, tmp = sim["db"], sim["proto"], sim["tmp"]

    rc = _run([
        "run", "--query", "sevoflurane recovery", "--protocol", str(proto),
        "--limit", "5", "--max-results", "1", "--db", str(db),
    ])
    assert rc == 0, "tuyến phải dừng SẠCH ở cổng người, không phải lỗi"

    with StagingStore(db) as store:
        run_row = store.conn.execute(
            "SELECT * FROM sr_runs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        assert run_row is not None, "phải tạo được sr_runs cho run mới"
        run_id = run_row["run_id"]
        assert run_row["state"] == "OPEN"

        events = _event_types(store, run_id)
        # Mỗi stage phải để lại dấu vết RUN-SCOPED — nếu --db không lan xuống stage
        # thì các event này nằm ở DB khác và assert dưới đây sẽ trống.
        assert "SCREENED" in events, events
        assert "ELIG_INCLUDED" in events, events
        assert "ROB_COMPLETED" in events, events
        assert "EXTRACT_COMPLETED" in events, events

        # Bất biến #6: orchestrator KHÔNG tự vượt cổng.
        assert "CONSENSUS_APPROVED" not in events
        assert "CONSENSUS_COMPLETED" not in events

        # D40: extract phải dùng field của PROTOCOL, không phải taxonomy CS mặc định.
        fields = {
            r["field"]
            for r in store.conn.execute("SELECT DISTINCT field FROM extraction").fetchall()
        }
        assert fields == {"recovery_time"}, f"field động D40 không tới được stage: {fields}"

        # Người bấm chốt (D37) — cổng người, không phải orchestrator.
        console_logic.approve_consensus(store, run_id)

    out = tmp / "report.md"
    rc = _run([
        "run", "--run", run_id, "--protocol", str(proto),
        "--limit", "5", "--db", str(db), "--from", "consensus",
    ])
    assert rc == 0, "sau khi người chốt, tuyến phải chạy tiếp được"

    with StagingStore(db) as store:
        events = _event_types(store, run_id)
        assert "CONSENSUS_APPROVED" in events
        assert "CONSENSUS_COMPLETED" in events
        assert store.conn.execute(
            "SELECT state FROM sr_runs WHERE run_id = ?", (run_id,)
        ).fetchone()["state"] == "CLOSED"

        claims = store.conn.execute(
            "SELECT * FROM consensus_claim WHERE run_id = ?", (run_id,)
        ).fetchall()
        assert claims, "ledger rỗng — chuỗi chạy hết nhưng không sinh claim nào"
        for c in claims:
            assert c["value"] == "10 min"
            assert c["outcome_id"] == "recovery"
            assert c["direction"] == "decrease"   # 'reduc' khớp đúng một nhóm
            assert c["weight"] == 1.0             # RoB Low

    report = _latest_report(run_id)
    assert report is not None, "không sinh được file báo cáo"
    text = report.read_text(encoding="utf-8")
    assert "10 min" in text
    assert run_id in text
    report.unlink()


def _event_types(store: StagingStore, run_id: str) -> set[str]:
    return {
        r["event_type"]
        for r in store.conn.execute(
            "SELECT DISTINCT event_type FROM events WHERE run_id = ?", (run_id,)
        ).fetchall()
    }


def _latest_report(run_id: str) -> Path | None:
    return next(iter(sorted(Path("docs/runs").glob(f"*-consensus-{run_id}.md"))), None)


# --- Mối nối riêng lẻ (test hồi quy cho từng bug đã tìm ra) ---------------------------


@respx.mock
def test_db_override_reaches_every_stage(sim):
    """`--db` phải chi phối cả tuyến. Trước khi vá, orchestrator ghi DB override
    còn từng stage tự mở StagingStore() trỏ staging thật — im lặng, không lỗi,
    và mọi số đếm đều sai."""
    _mock_ollama()
    _mock_sources()

    db, proto = sim["db"], sim["proto"]
    _run([
        "run", "--query", "q", "--protocol", str(proto),
        "--limit", "5", "--max-results", "1", "--db", str(db),
    ])

    with StagingStore(db) as store:
        n = store.conn.execute("SELECT COUNT(*) n FROM screening").fetchone()["n"]
    assert n > 0, "stage screen ghi vào DB khác — --db không lan xuống phase con"


def test_resumable_states_include_the_state_humans_create():
    """CONSENSUS_READY là trạng thái do người tạo ở D37; thiếu nó trong tập
    resumable thì đúng luồng D37→BS4 bị chặn ngay sau khi người bấm chốt."""
    assert "CONSENSUS_READY" in sr_run.RESUMABLE_STATES
    assert "OPEN" in sr_run.RESUMABLE_STATES
    # Bất biến sau chốt: đã đóng thì không mở lại.
    assert "CLOSED" not in sr_run.RESUMABLE_STATES
    assert "ABANDONED" not in sr_run.RESUMABLE_STATES


def test_staging_store_default_path_is_late_bound(tmp_path, monkeypatch):
    """Đổi SR_AGENT_DB SAU khi import phải có tác dụng — nếu không, mọi tiến trình
    con đều bám vào DB bind lúc import (cùng họ sẹo writer_lock/OPS-1)."""
    target = tmp_path / "late.db"
    monkeypatch.setenv("SR_AGENT_DB", str(target))
    with StagingStore() as store:
        assert store.db_path == target

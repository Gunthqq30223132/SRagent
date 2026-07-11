"""Tests for tools/screen_run.py (PRISMA Screening)."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from sr_agent.config import OLLAMA_MODEL
from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from tests.test_pipeline import FakeFetcher, make_doc
from tools.protocol_build import PicoConcept, ReviewProtocol
from tools.screen_run import ScreenVerdict, normalize_text, run_screening_a, verify_quote
from sr_agent.monitor.health import compute_cohen_kappa

OLLAMA = "http://localhost:11434"


@pytest.fixture
def store(tmp_path):
    with StagingStore(tmp_path / "t.db") as s:
        yield s


@pytest.fixture
def protocol():
    return ReviewProtocol(
        topic_vi="chủ đề",
        population=PicoConcept(concept="LLM"),
        intervention=PicoConcept(concept="RAG"),
        exclusion_criteria=["ET1", "ET2", "ET3"]
    )


@pytest.fixture
def criteria():
    return {
        "ET1": {"label_vi": "Sai Population", "description_en": "Wrong population"},
        "ET2": {"label_vi": "Không có Intervention", "description_en": "No intervention"},
        "ET3": {"label_vi": "Loại xuất bản ngoài phạm vi", "description_en": "Wrong study type"}
    }


class TestVerifier:
    def test_normalize_text_smart_quotes(self):
        text = "This is a ‘test’ with “smart” quotes."
        assert normalize_text(text) == "this is a 'test' with \"smart\" quotes."

    def test_normalize_text_whitespace(self):
        text = "Multiple   spaces  and\nnewlines."
        assert normalize_text(text) == "multiple spaces and newlines."

    def test_normalize_text_dashes(self):
        text = "Dash – and em—dash."
        assert normalize_text(text) == "dash - and em-dash."

    def test_verify_quote_exact_match(self):
        source = "We use Retrieval-Augmented Generation (RAG) to improve QA."
        quote = "Retrieval-Augmented Generation"
        assert verify_quote(source, quote) is True

    def test_verify_quote_with_quotes_and_spacing_diff(self):
        source = "We use “Retrieval-Augmented Generation”  to improve QA."
        quote = " “Retrieval-Augmented Generation” "
        assert verify_quote(source, quote) is True

    def test_verify_quote_not_matching(self):
        source = "We use Retrieval-Augmented Generation (RAG) to improve QA."
        quote = "Fine-Tuning"
        assert verify_quote(source, quote) is False


class TestScreeningA:
    @respx.mock
    def test_screening_a_include_verdict(self, store, protocol, criteria):
        # Insert a queued document
        doc = make_doc("ieee", "38111222", "Title RAG LLM", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "This is an abstract about RAG and LLM."
        store.upsert(doc)
        
        # Mock Ollama outputting include — M7.2: include cũng phải kèm relevance_quote verbatim
        dummy_verdict = {
            "verdict": "include",
            "relevance_quote": "about RAG and LLM",
            "confidence": "high"
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_verdict)}
        }))

        count = run_screening_a(store, protocol, criteria, limit=1)
        assert count == 1

        # Verify db verdict
        verdicts = store.screen_verdicts("ieee:38111222")
        assert len(verdicts) == 1
        assert verdicts[0]["verdict"] == "include"
        assert verdicts[0]["agent"] == "screener_a"
        assert verdicts[0]["confidence"] == "high"
        # relevance_quote được lưu vào cột evidence_quote (không đổi schema DB)
        assert verdicts[0]["evidence_quote"] == "about RAG and LLM"

    @respx.mock
    def test_screening_a_exclude_valid_verdict(self, store, protocol, criteria):
        doc = make_doc("ieee", "38111222", "Title Wrong Population", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "This study is about healthcare patients, not LLM systems."
        store.upsert(doc)
        
        dummy_verdict = {
            "verdict": "exclude",
            "criterion_id": "ET1",
            "evidence_quote": "healthcare patients, not LLM systems",
            "confidence": "high"
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_verdict)}
        }))
        
        count = run_screening_a(store, protocol, criteria, limit=1)
        assert count == 1
        
        verdicts = store.screen_verdicts("ieee:38111222")
        assert len(verdicts) == 1
        assert verdicts[0]["verdict"] == "exclude"
        assert verdicts[0]["criterion_id"] == "ET1"
        assert verdicts[0]["evidence_quote"] == "healthcare patients, not LLM systems"

    @respx.mock
    def test_screening_a_exclude_invalid_missing_quote(self, store, protocol, criteria):
        doc = make_doc("ieee", "38111222", "Title Wrong Population", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "This study is about healthcare patients."
        store.upsert(doc)
        
        # Missing quote
        dummy_verdict = {
            "verdict": "exclude",
            "criterion_id": "ET1",
            "confidence": "high"
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_verdict)}
        }))
        
        count = run_screening_a(store, protocol, criteria, limit=1)
        assert count == 1
        
        verdicts = store.screen_verdicts("ieee:38111222")
        assert len(verdicts) == 1
        assert verdicts[0]["verdict"] == "invalid"  # should be marked invalid due to missing quote

    @respx.mock
    def test_screening_a_exclude_invalid_hallucinated_quote(self, store, protocol, criteria):
        doc = make_doc("ieee", "38111222", "Title Wrong Population", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "This study is about healthcare patients."
        store.upsert(doc)
        
        # Hallucinated quote
        dummy_verdict = {
            "verdict": "exclude",
            "criterion_id": "ET1",
            "evidence_quote": "hallucinated not in text quote",
            "confidence": "high"
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_verdict)}
        }))
        
        count = run_screening_a(store, protocol, criteria, limit=1)
        assert count == 1
        
        verdicts = store.screen_verdicts("ieee:38111222")
        assert len(verdicts) == 1
        assert verdicts[0]["verdict"] == "invalid"  # should be marked invalid because quote doesn't match


class TestConsensusAndTiebreaker:
    @respx.mock
    def test_consensus_agree_exclude(self, store, protocol, criteria):
        doc = make_doc("ieee", "38111222", "Title 2", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "Wrong population details."
        store.upsert(doc)

        dummy_verdict = {
            "verdict": "exclude",
            "criterion_id": "ET1",
            "evidence_quote": "Wrong population details",
            "confidence": "high"
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_verdict)}
        }))

        from tools.screen_run import run_screening_batch
        res = run_screening_batch(store, protocol, criteria, limit=1)
        assert res["processed"] == 1

        # Check status updated to REJECTED
        updated = store.get("ieee:38111222")
        assert updated.status is DocStatus.REJECTED

    @respx.mock
    def test_consensus_agree_include(self, store, protocol, criteria):
        doc = make_doc("ieee", "38111222", "Title 2", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "RAG and LLM systems are here."
        store.upsert(doc)

        dummy_verdict = {
            "verdict": "include",
            "relevance_quote": "RAG and LLM systems",
            "confidence": "high"
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_verdict)}
        }))

        from tools.screen_run import run_screening_batch
        res = run_screening_batch(store, protocol, criteria, limit=1)
        assert res["processed"] == 1

        # Check status kept as QUEUED
        updated = store.get("ieee:38111222")
        assert updated.status is DocStatus.QUEUED

    @respx.mock
    def test_disagreement_resolved_by_tiebreaker(self, store, protocol, criteria):
        doc = make_doc("ieee", "38111222", "Title 2", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "Wrong population details."
        store.upsert(doc)

        # Mock: screener_a says exclude, screener_b says include, tiebreaker says exclude
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(side_effect=[
            # Screener A
            httpx.Response(200, json={
                "message": {"role": "assistant", "content": json.dumps({
                    "verdict": "exclude", "criterion_id": "ET1",
                    "evidence_quote": "Wrong population details", "confidence": "high"
                })}
            }),
            # Screener B — include hợp lệ (M7.2: phải kèm relevance_quote verbatim)
            httpx.Response(200, json={
                "message": {"role": "assistant", "content": json.dumps({
                    "verdict": "include", "relevance_quote": "Wrong population details",
                    "confidence": "high"
                })}
            }),
            # Tiebreaker
            httpx.Response(200, json={
                "message": {"role": "assistant", "content": json.dumps({
                    "verdict": "exclude", "criterion_id": "ET1",
                    "evidence_quote": "Wrong population details", "confidence": "high"
                })}
            })
        ])

        from tools.screen_run import run_screening_batch
        res = run_screening_batch(store, protocol, criteria, limit=1)
        assert res["processed"] == 1

        # Check resolved to REJECTED by tiebreaker
        updated = store.get("ieee:38111222")
        assert updated.status is DocStatus.REJECTED

    @respx.mock
    def test_disagreement_escalated_due_to_low_confidence(self, store, protocol, criteria):
        doc = make_doc("ieee", "38111222", "Title 2", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "Wrong population details."
        store.upsert(doc)

        # Mock: screener_a says exclude, screener_b says include, tiebreaker says low confidence
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(side_effect=[
            # Screener A
            httpx.Response(200, json={
                "message": {"role": "assistant", "content": json.dumps({
                    "verdict": "exclude", "criterion_id": "ET1",
                    "evidence_quote": "Wrong population details", "confidence": "high"
                })}
            }),
            # Screener B — include hợp lệ
            httpx.Response(200, json={
                "message": {"role": "assistant", "content": json.dumps({
                    "verdict": "include", "relevance_quote": "Wrong population details",
                    "confidence": "high"
                })}
            }),
            # Tiebreaker (low confidence, quote hợp lệ — escalate vì confidence chứ không vì invalid)
            httpx.Response(200, json={
                "message": {"role": "assistant", "content": json.dumps({
                    "verdict": "include", "relevance_quote": "Wrong population details",
                    "confidence": "low"
                })}
            })
        ])

        from tools.screen_run import run_screening_batch
        res = run_screening_batch(store, protocol, criteria, limit=1)
        assert res["processed"] == 1

        # Check status remains QUEUED (escalated)
        updated = store.get("ieee:38111222")
        assert updated.status is DocStatus.QUEUED
        
        # Check escalated event was logged
        events = [r["event_type"] for r in store.conn.execute("SELECT event_type FROM events WHERE uid = 'ieee:38111222'").fetchall()]
        assert "SCREEN_ESCALATED" in events


class TestKappaMath:
    def test_kappa_perfect_agreement(self):
        verdicts = [("include", "include"), ("include", "include"), ("exclude", "exclude")]
        assert compute_cohen_kappa(verdicts) == 1.0

    def test_kappa_perfect_disagreement(self):
        verdicts = [("include", "exclude"), ("exclude", "include")]
        # expected p_o = 0.0, expected p_e = 0.5
        # kappa = (0.0 - 0.5) / (1 - 0.5) = -1.0
        assert compute_cohen_kappa(verdicts) == -1.0

    def test_kappa_not_enough_data(self):
        assert compute_cohen_kappa([("include", "include")]) is None
        assert compute_cohen_kappa([]) is None


class TestScreenerBIndependence:
    @respx.mock
    def test_screener_b_does_not_see_screener_a_output(self, store, protocol, criteria):
        doc = make_doc("ieee", "38111222", "Title 2", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "Some content."
        store.upsert(doc)

        # Mock tags to contain gemma4:e4b so dual-screening runs normally
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={
            "models": [{"name": "gemma4:e4b"}]
        }))
        
        a_verdict_dict = {
            "verdict": "exclude", "criterion_id": "ET1",
            "evidence_quote": "ZZZ_UNIQUE_A_QUOTE", "confidence": "high"
        }
        respx.post(f"{OLLAMA}/api/chat").mock(side_effect=[
            # Screener A
            httpx.Response(200, json={
                "message": {"role": "assistant", "content": json.dumps(a_verdict_dict)}
            }),
            # Screener B
            httpx.Response(200, json={
                "message": {"role": "assistant", "content": json.dumps({
                    "verdict": "exclude", "criterion_id": "ET1",
                    "evidence_quote": "Some content", "confidence": "high"
                })}
            })
        ])

        from tools.screen_run import run_screening_batch
        # Set env so we check tags correctly
        import os
        os.environ["SR_SCREEN_MODEL_B"] = "gemma4:e4b"
        run_screening_batch(store, protocol, criteria, limit=1)

        # Inspect the requests captured by respx
        screener_b_request = None
        for call in respx.calls:
            req = call.request
            if req.method == "POST" and "/api/chat" in str(req.url):
                body = json.loads(req.content)
                for msg in body.get("messages", []):
                    if "screener_b" in msg.get("content", ""):
                        screener_b_request = req
                        break
        
        assert screener_b_request is not None
        req_body = json.loads(screener_b_request.content)
        messages_text = str(req_body["messages"])
        
        # Rigorous check: B's request body must NOT contain A's unique quote, 'screener_a', or A's verdict JSON
        assert "ZZZ_UNIQUE_A_QUOTE" not in messages_text
        assert "screener_a" not in messages_text
        assert json.dumps(a_verdict_dict) not in messages_text
        assert '"verdict": "exclude"' not in messages_text  # B does not see A's output verdict


class TestModelAConfig:
    """M7.2 Phase 2R: SR_SCREEN_MODEL_A tách screener A khỏi OLLAMA_MODEL toàn cục."""

    def _seed_doc(self, store):
        doc = make_doc("ieee", "38111222", "Title 2", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "RAG and LLM systems are here."
        store.upsert(doc)

    def _include_response(self):
        return httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps({
                "verdict": "include", "relevance_quote": "RAG and LLM systems",
                "confidence": "high"
            })}
        })

    @respx.mock
    def test_env_model_a_is_used_and_recorded(self, store, protocol, criteria, monkeypatch):
        monkeypatch.setenv("SR_SCREEN_MODEL_A", "custom-a:1b")
        monkeypatch.setenv("SR_SCREEN_MODEL_B", "gemma4:e4b")
        self._seed_doc(store)
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={
            "models": [{"name": "custom-a:1b"}, {"name": "gemma4:e4b"}]
        }))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=self._include_response())

        from tools.screen_run import run_screening_batch
        run_screening_batch(store, protocol, criteria, limit=1)

        models = {r["agent"]: r["model"] for r in store.screen_verdicts("ieee:38111222")}
        assert models["screener_a"] == "custom-a:1b"     # ghi đúng model từng row
        assert models["screener_b"] == "gemma4:e4b"

    @respx.mock
    def test_missing_model_a_falls_back_loudly(self, store, protocol, criteria, monkeypatch):
        monkeypatch.setenv("SR_SCREEN_MODEL_A", "khong-ton-tai:9b")
        monkeypatch.setenv("SR_SCREEN_MODEL_B", "gemma4:e4b")
        self._seed_doc(store)
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={
            "models": [{"name": "gemma4:e4b"}]             # thiếu model A tùy biến
        }))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=self._include_response())

        from tools.screen_run import run_screening_batch
        run_screening_batch(store, protocol, criteria, limit=1)

        models = {r["agent"]: r["model"] for r in store.screen_verdicts("ieee:38111222")}
        assert models["screener_a"] == OLLAMA_MODEL        # quay về mặc định, không chết lặng
        events = [r["event_type"] for r in store.conn.execute(
            "SELECT event_type FROM events WHERE uid = 'screening:batch'"
        ).fetchall()]
        assert "SCREEN_MODEL_A_FALLBACK" in events         # và phải ỒN ÀO


class TestQuoteCopyDiscipline:
    """M7.2 Phase 1b: luật chép quote cơ học phải có mặt trong CẢ BA prompt.

    Phase 2 đo được screener A invalid 50.6% do chèn '...' và sửa ký tự LaTeX —
    lỗi kỷ luật chép, chữa ở prompt; verifier giữ nguyên (nới verifier = nới firewall)."""

    def test_all_three_prompts_carry_quote_copy_rules(self, protocol, criteria):
        from tools.screen_run import (
            QUOTE_COPY_RULES,
            build_screener_a_prompts,
            build_screener_b_prompts,
            build_tiebreaker_prompts,
        )

        sys_a, _ = build_screener_a_prompts("T", "A", protocol, criteria)
        sys_b, _ = build_screener_b_prompts("T", "A", protocol, criteria)
        sys_tb, _ = build_tiebreaker_prompts("T", "A", protocol, criteria, "v1", "v2")

        for sys_prompt in (sys_a, sys_b, sys_tb):
            assert QUOTE_COPY_RULES in sys_prompt
            assert "character-for-character" in sys_prompt
            assert "NEVER shorten with '...'" in sys_prompt

    def test_exclude_prompts_pin_criterion_id_to_listed_codes(self, protocol, criteria):
        from tools.screen_run import build_screener_a_prompts, build_screener_b_prompts

        sys_a, _ = build_screener_a_prompts("T", "A", protocol, criteria)
        sys_b, _ = build_screener_b_prompts("T", "A", protocol, criteria)
        for sys_prompt in (sys_a, sys_b):
            assert "EXACTLY one of the codes listed" in sys_prompt


class TestSymmetricEvidenceTax:
    """M7.2 §2.1: include cũng phải trả phí kiểm chứng — không còn verdict miễn phí.

    Trước hiệu chuẩn, include không cần gì trong khi exclude phải qua verify_quote ⇒
    model nhỏ thoái hóa 100% include (κ = 0, First Light 2026-07-11)."""

    @respx.mock
    def test_include_without_relevance_quote_is_invalid(self, store, protocol, criteria):
        doc = make_doc("ieee", "38111222", "Title RAG LLM", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "This is an abstract about RAG and LLM."
        store.upsert(doc)

        dummy_verdict = {"verdict": "include", "confidence": "high"}   # thiếu relevance_quote
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_verdict)}
        }))

        count = run_screening_a(store, protocol, criteria, limit=1)
        assert count == 1
        verdicts = store.screen_verdicts("ieee:38111222")
        assert verdicts[0]["verdict"] == "invalid"   # include miễn phí không còn tồn tại

    @respx.mock
    def test_include_with_hallucinated_relevance_quote_is_invalid(self, store, protocol, criteria):
        doc = make_doc("ieee", "38111222", "Title RAG LLM", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "This is an abstract about RAG and LLM."
        store.upsert(doc)

        dummy_verdict = {
            "verdict": "include",
            "relevance_quote": "totally fabricated sentence not in the text",
            "confidence": "high"
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_verdict)}
        }))

        count = run_screening_a(store, protocol, criteria, limit=1)
        assert count == 1
        verdicts = store.screen_verdicts("ieee:38111222")
        assert verdicts[0]["verdict"] == "invalid"   # quote bịa = void, không phải "sửa lại cho khớp"


class TestDegenerateGuard:
    """M7.2 §3 Phase 1.3: screener vote một chiều 100% trên batch đủ lớn ⇒ SCREEN_DEGENERATE."""

    def _seed_docs(self, store, n):
        for i in range(n):
            doc = make_doc("ieee", f"381113{i:02d}", f"Title {i}", 1)
            doc.status = DocStatus.QUEUED
            doc.abstract = "RAG and LLM systems are here."
            store.upsert(doc)

    def _mock_all_include(self):
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={
            "models": [{"name": "gemma4:e4b"}]
        }))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps({
                "verdict": "include", "relevance_quote": "RAG and LLM systems",
                "confidence": "high"
            })}
        }))

    @respx.mock
    def test_all_include_batch_fires_degenerate_for_both_screeners(self, store, protocol, criteria, monkeypatch):
        monkeypatch.setenv("SR_SCREEN_MODEL_B", "gemma4:e4b")
        self._seed_docs(store, 10)
        self._mock_all_include()

        from tools.screen_run import run_screening_batch
        res = run_screening_batch(store, protocol, criteria, limit=10)

        assert res["processed"] == 10
        assert res["include_rate_a"] == 1.0 and res["include_rate_b"] == 1.0
        assert res["invalid_rate_a"] == 0.0 and res["invalid_rate_b"] == 0.0
        assert res["kappa"] == 1.0            # đồng thuận tuyệt đối include: p_o = p_e = 1

        events = [r["event_type"] for r in store.conn.execute(
            "SELECT event_type FROM events WHERE uid = 'screening:batch'"
        ).fetchall()]
        assert events.count("SCREEN_DEGENERATE") == 2   # cả A lẫn B đều một chiều

    @respx.mock
    def test_small_batch_does_not_fire_degenerate(self, store, protocol, criteria, monkeypatch):
        monkeypatch.setenv("SR_SCREEN_MODEL_B", "gemma4:e4b")
        self._seed_docs(store, 2)             # dưới ngưỡng DEGENERATE_MIN_VALID
        self._mock_all_include()

        from tools.screen_run import run_screening_batch
        res = run_screening_batch(store, protocol, criteria, limit=2)

        assert res["processed"] == 2
        events = [r["event_type"] for r in store.conn.execute(
            "SELECT event_type FROM events WHERE uid = 'screening:batch'"
        ).fetchall()]
        assert "SCREEN_DEGENERATE" not in events   # mẫu quá nhỏ, κ/rate chưa có nghĩa


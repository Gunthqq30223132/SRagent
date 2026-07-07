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
from tools.screen_run import ScreenVerdict, compute_cohen_kappa, normalize_text, run_screening_a, verify_quote

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
        
        # Mock Ollama outputting include
        dummy_verdict = {
            "verdict": "include",
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
            # Screener B
            httpx.Response(200, json={
                "message": {"role": "assistant", "content": json.dumps({
                    "verdict": "include", "confidence": "high"
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
            # Screener B
            httpx.Response(200, json={
                "message": {"role": "assistant", "content": json.dumps({
                    "verdict": "include", "confidence": "high"
                })}
            }),
            # Tiebreaker (low confidence)
            httpx.Response(200, json={
                "message": {"role": "assistant", "content": json.dumps({
                    "verdict": "include", "confidence": "low"
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

        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(side_effect=[
            # Screener A
            httpx.Response(200, json={
                "message": {"role": "assistant", "content": json.dumps({
                    "verdict": "exclude", "criterion_id": "ET1",
                    "evidence_quote": "Some content", "confidence": "high"
                })}
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
        # Check that there is no reference to screener_a or its outputs in the messages
        messages_text = str(req_body["messages"])
        assert "screener_a" not in messages_text
        assert "exclude" not in messages_text or "verdict" not in messages_text  # should only have exclusion criteria definitions, not screener_a's choice


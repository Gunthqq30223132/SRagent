"""Tests for Sprint M6-HOTFIX business invariants (G4)."""

import json
import os
import pytest
import respx
import httpx

from sr_agent.config import OLLAMA_MODEL
from sr_agent.models.schemas import DocStatus
from sr_agent.store.staging import StagingStore
from sr_agent.monitor.health import snapshot
from tests.test_pipeline import make_doc
from tools.protocol_build import ReviewProtocol, PicoConcept
from tools.screen_run import run_screening_batch
from tools.evidence_extract import run_extraction_batch

OLLAMA = "http://localhost:11434"


@pytest.fixture
def store(tmp_path):
    with StagingStore(tmp_path / "t.db") as s:
        yield s


@pytest.fixture
def protocol():
    return ReviewProtocol(
        topic_vi="chủ đề",
        population=PicoConcept(concept="LLM", synonyms=[], required=True),
        intervention=PicoConcept(concept="RAG", synonyms=[], required=True),
        languages=["en"],
        study_types_excluded=["editorial"],
        exclusion_criteria=["ET1", "ET2"]
    )


@pytest.fixture
def criteria():
    return {
        "ET1": {"label_vi": "Sai Population", "description_en": "Wrong population"},
        "ET2": {"label_vi": "Không có Intervention", "description_en": "No intervention"}
    }


class TestM6HotfixInvariants:
    @respx.mock
    def test_single_model_mode_fallback(self, store, protocol, criteria):
        # 1 queued document
        doc = make_doc("ieee", "11111111", "Title 1", 1)
        doc.status = DocStatus.QUEUED
        store.upsert(doc)

        # Mock tags: gemma4:e4b is NOT present
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={
            "models": [{"name": OLLAMA_MODEL}]
        }))

        # Both screener A and screener B chat mock returns (using client_a model)
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps({
                "verdict": "include", "confidence": "high"
            })}
        }))

        os.environ["SR_SCREEN_MODEL_B"] = "gemma4:e4b"
        res = run_screening_batch(store, protocol, criteria, limit=1)

        # Verify output summary
        assert res["single_model_mode"] is True
        assert res["kappa"] is None

        # Verify event logged
        events = store.conn.execute("SELECT * FROM events WHERE uid = 'screening:batch'").fetchall()
        assert len(events) == 1
        assert events[0]["event_type"] == "SCREEN_SINGLE_MODEL"

        # Verify health snapshot single_model_mode_recent is True
        snap = snapshot(store)
        assert snap.single_model_mode_recent is True

    @respx.mock
    def test_extraction_all_negative_none_score(self, store):
        # 1 queued document
        doc = make_doc("ieee", "11111111", "Title 1", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "We evaluate our methods."
        store.upsert(doc)

        # Mock structured extraction outputting negative answers without quotes
        dummy_extraction = {
            "has_code_repo": {"value": "false", "quote": "", "section": ""},
            "dataset_spec": {"value": "null", "quote": "", "section": ""},
            "baselines": {"value": "none", "quote": "", "section": ""},
            "metrics": {"value": "[]", "quote": "", "section": ""}
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_extraction)}
        }))

        count = run_extraction_batch(store, limit=1)
        assert count == 1

        # Check all 4 rows verified=2
        exts = store.extractions("ieee:11111111", verified_only=False)
        assert len(exts) == 4
        for e in exts:
            assert e["verified"] == 2

        # verified_only=True returns empty
        assert len(store.extractions("ieee:11111111", verified_only=True)) == 0

        # Health snapshot grounding score is None
        snap = snapshot(store)
        assert snap.grounding_avg_24h is None

    @respx.mock
    def test_screening_network_transient_error_break(self, store, protocol, criteria):
        # 3 queued documents
        doc1 = make_doc("ieee", "11111111", "Title 1", 1)
        doc2 = make_doc("ieee", "22222222", "Title 2", 1)
        doc3 = make_doc("ieee", "33333333", "Title 3", 1)
        for d in (doc1, doc2, doc3):
            d.status = DocStatus.QUEUED
            store.upsert(d)

        # Mock tags
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={
            "models": [{"name": "gemma4:e4b"}]
        }))

        # Mock chat: doc1 succeeds, doc2 raises ConnectError
        call_count = 0
        def chat_callback(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps({"verdict": "include", "relevance_quote": "We evaluate on benchmarks", "confidence": "high"})}})
            elif call_count == 2:
                return httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps({"verdict": "include", "relevance_quote": "We evaluate on benchmarks", "confidence": "high"})}})
            else:
                raise httpx.ConnectError("Connection refused")

        respx.post(f"{OLLAMA}/api/chat").mock(side_effect=chat_callback)

        res = run_screening_batch(store, protocol, criteria, limit=3)
        assert res["processed"] == 1  # Only doc1 processed successfully

        # Verify doc1 has consensus and screen verdicts
        assert len(store.screen_verdicts("ieee:11111111")) == 2

        # Verify doc2 and doc3 have no verdicts and no SCREEN_ESCALATED events
        assert len(store.screen_verdicts("ieee:22222222")) == 0
        assert len(store.screen_verdicts("ieee:33333333")) == 0
        
        events = store.conn.execute("SELECT * FROM events WHERE uid IN ('ieee:22222222', 'ieee:33333333')").fetchall()
        assert len(events) == 0

    @respx.mock
    def test_two_batches_have_separate_kappa(self, store, protocol, criteria):
        # 4 queued documents
        doc1 = make_doc("ieee", "11111111", "Title 1", 1)
        doc2 = make_doc("ieee", "22222222", "Title 2", 1)
        doc3 = make_doc("ieee", "33333333", "Title 3", 1)
        doc4 = make_doc("ieee", "44444444", "Title 4", 1)
        for d in (doc1, doc2, doc3, doc4):
            d.status = DocStatus.QUEUED
            store.upsert(d)

        # Mock tags
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={
            "models": [{"name": "gemma4:e4b"}]
        }))

        # Mock chat responses:
        # Batch 1 (doc1 and doc2): Screener A and B agree (include, include) -> kappa = 1.0
        # Batch 2 (doc3 and doc4): Screener A and B disagree (include, exclude / exclude, include) -> kappa = -1.0
        respx.post(f"{OLLAMA}/api/chat").mock(side_effect=[
            # Doc 1
            httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps({"verdict": "include", "relevance_quote": "We evaluate on benchmarks", "confidence": "high"})}}),
            httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps({"verdict": "include", "relevance_quote": "We evaluate on benchmarks", "confidence": "high"})}}),
            # Doc 2
            httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps({"verdict": "include", "relevance_quote": "We evaluate on benchmarks", "confidence": "high"})}}),
            httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps({"verdict": "include", "relevance_quote": "We evaluate on benchmarks", "confidence": "high"})}}),
            # Doc 3 (screener_a = include, screener_b = exclude) -> tiebreaker (exclude)
            httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps({"verdict": "include", "relevance_quote": "We evaluate on benchmarks", "confidence": "high"})}}),
            httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps({"verdict": "exclude", "criterion_id": "ET1", "evidence_quote": "Title 3", "confidence": "high"})}}),
            httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps({"verdict": "exclude", "criterion_id": "ET1", "evidence_quote": "Title 3", "confidence": "high"})}}),
            # Doc 4 (screener_a = exclude, screener_b = include) -> tiebreaker (exclude)
            httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps({"verdict": "exclude", "criterion_id": "ET1", "evidence_quote": "Title 4", "confidence": "high"})}}),
            httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps({"verdict": "include", "relevance_quote": "We evaluate on benchmarks", "confidence": "high"})}}),
            httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps({"verdict": "exclude", "criterion_id": "ET1", "evidence_quote": "Title 4", "confidence": "high"})}}),
        ])

        # Run Batch 1
        res1 = run_screening_batch(store, protocol, criteria, limit=2)
        assert res1["processed"] == 2
        assert res1["kappa"] == 1.0

        # Run Batch 2
        res2 = run_screening_batch(store, protocol, criteria, limit=2)
        assert res2["processed"] == 2
        assert res2["kappa"] == -1.0

        # Verify runs table contains 2 separate records with different kappa
        runs = store.conn.execute("SELECT * FROM runs ORDER BY id").fetchall()
        assert len(runs) == 2
        
        run1_report = json.loads(runs[0]["report_json"])
        run2_report = json.loads(runs[1]["report_json"])

        assert run1_report["kappa"] == 1.0
        assert run2_report["kappa"] == -1.0

"""Tests for tools/eligibility_run.py (PRISMA Full-Text Eligibility)."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from sr_agent.config import OLLAMA_MODEL
from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from sr_agent.errors import TransientError
from tests.test_pipeline import make_doc
from tools.protocol_build import PicoConcept, ReviewProtocol
from tools.eligibility_run import run_eligibility_batch, has_full_text
from tools.prisma_report import generate_prisma_report

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
        exclusion_criteria=["EF1", "EF2", "EF4"]
    )


@pytest.fixture
def criteria():
    return {
        "EF1": {"label_vi": "Không có đánh giá thực nghiệm", "description_en": "no empirical evaluation while protocol requires measurable outcome"},
        "EF2": {"label_vi": "Outcome không được báo cáo", "description_en": "experiments exist but the protocol outcome is not measured/reported"},
        "EF4": {"label_vi": "Trùng dữ liệu (salami slicing)", "description_en": "same authors + same experiments already in the included set"}
    }


class TestEligibilityRunner:
    @respx.mock
    def test_doc_without_full_text(self, store, protocol, criteria):
        # 1. Setup doc with title and abstract but NO full text
        doc = make_doc("ieee", "11111111", "Title 1", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "An abstract about RAG."
        doc.full_text = None
        doc.sections = None
        store.upsert(doc)
        
        # Screen included event
        store.log_event("ieee:11111111", "SCREEN_INCLUDED", "Consensus include")
        
        # We mock Ollama tags just in case, but it shouldn't even make any HTTP call to chat
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        route_chat = respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={}))

        count = run_eligibility_batch(store, protocol, criteria, limit=1)
        assert count == 1
        
        # Check event logged
        events = store.conn.execute("SELECT event_type FROM events WHERE uid = 'ieee:11111111'").fetchall()
        event_types = [e["event_type"] for e in events]
        assert "ELIG_ABSTRACT_ONLY" in event_types
        assert "ELIG_INCLUDED" not in event_types
        assert "ELIG_EXCLUDED" not in event_types
        
        # Check status unchanged
        fetched_doc = store.get("ieee:11111111")
        assert fetched_doc.status == DocStatus.QUEUED
        
        # Verifying zero HTTP calls to Ollama chat
        assert not route_chat.called

    @respx.mock
    def test_exclude_ef1_valid_quote(self, store, protocol, criteria):
        # Setup doc with full text
        doc = make_doc("ieee", "22222222", "Title 2", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "Abstract"
        doc.full_text = "This paper has no empirical evaluation metric at all."
        store.upsert(doc)
        
        store.log_event("ieee:22222222", "SCREEN_INCLUDED", "Consensus include")
        
        dummy_verdict = {
            "verdict": "exclude",
            "criterion_id": "EF1",
            "evidence_quote": "no empirical evaluation metric",
            "confidence": "high"
        }
        
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={
            "models": [{"name": OLLAMA_MODEL}]
        }))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_verdict)}
        }))
        
        count = run_eligibility_batch(store, protocol, criteria, limit=1)
        assert count == 1
        
        # Check event
        events = store.conn.execute("SELECT event_type, detail FROM events WHERE uid = 'ieee:22222222'").fetchall()
        elig_ex_event = [e for e in events if e["event_type"] == "ELIG_EXCLUDED"]
        assert len(elig_ex_event) == 1
        assert elig_ex_event[0]["detail"] == "EF1"
        
        # Check status
        fetched_doc = store.get("ieee:22222222")
        assert fetched_doc.status == DocStatus.REJECTED
        
        # Check screening verdict
        verdicts = store.screen_verdicts("ieee:22222222")
        assert len(verdicts) == 1
        assert verdicts[0]["agent"] == "eligibility"
        assert verdicts[0]["verdict"] == "exclude"
        assert verdicts[0]["criterion_id"] == "EF1"

    @respx.mock
    def test_invalid_verdict_quote_hallucinated(self, store, protocol, criteria):
        doc = make_doc("ieee", "33333333", "Title 3", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "Abstract"
        doc.full_text = "Standard full text content."
        store.upsert(doc)
        
        store.log_event("ieee:33333333", "SCREEN_INCLUDED", "Consensus include")
        
        dummy_verdict = {
            "verdict": "exclude",
            "criterion_id": "EF1",
            "evidence_quote": "hallucinated quote",
            "confidence": "high"
        }
        
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_verdict)}
        }))
        
        count = run_eligibility_batch(store, protocol, criteria, limit=1)
        assert count == 1
        
        events = store.conn.execute("SELECT event_type FROM events WHERE uid = 'ieee:33333333'").fetchall()
        event_types = [e["event_type"] for e in events]
        assert "ELIG_ESCALATED" in event_types
        assert "ELIG_EXCLUDED" not in event_types
        
        # Status remains queued
        fetched_doc = store.get("ieee:33333333")
        assert fetched_doc.status == DocStatus.QUEUED

    @respx.mock
    def test_doc_not_screen_included_skipped(self, store, protocol, criteria):
        # Doc in status queued but NO event SCREEN_INCLUDED
        doc = make_doc("ieee", "44444444", "Title 4", 1)
        doc.status = DocStatus.QUEUED
        doc.full_text = "Some text."
        store.upsert(doc)
        
        count = run_eligibility_batch(store, protocol, criteria, limit=1)
        assert count == 0
        
        events = store.conn.execute("SELECT event_type FROM events WHERE uid = 'ieee:44444444'").fetchall()
        assert len(events) == 0

    @respx.mock
    def test_transient_error_handling(self, store, protocol, criteria):
        doc1 = make_doc("ieee", "55555555", "Title 5", 1)
        doc1.status = DocStatus.QUEUED
        doc1.full_text = "Text 5"
        store.upsert(doc1)
        store.log_event("ieee:55555555", "SCREEN_INCLUDED")
        
        doc2 = make_doc("ieee", "66666666", "Title 6", 1)
        doc2.status = DocStatus.QUEUED
        doc2.full_text = "Text 6"
        store.upsert(doc2)
        store.log_event("ieee:66666666", "SCREEN_INCLUDED")
        
        # Mock tags
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        
        # Let's mock a HTTP status error for Ollama chat
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(503, text="Service Unavailable"))
        
        count = run_eligibility_batch(store, protocol, criteria, limit=2)
        assert count == 0
        
        # Make sure no ELIG_* events or screening verdicts are written for doc1 or doc2
        events = store.conn.execute("SELECT event_type FROM events WHERE event_type LIKE 'ELIG_%'").fetchall()
        assert len(events) == 0
        
        verdicts = store.conn.execute("SELECT * FROM screening").fetchall()
        assert len(verdicts) == 0

    def test_prisma_report_eligibility(self, store):
        # Mock various events
        # Identification & screening Setup
        report1 = {"fetched": 10, "duplicates": 2, "rejected_by_rubric": 3, "queued": 5}
        store.record_run("q", "2026-07-08T00:00:00Z", json.dumps(report1))
        
        # Documents: 2 approved
        for i in range(2):
            doc = make_doc("ieee", f"9999000{i}", f"T {i}", 1)
            doc.status = DocStatus.APPROVED
            store.upsert(doc)
            
        # Log eligibility events
        # 2 included
        store.log_event("ieee:100", "ELIG_INCLUDED", "LLM include")
        store.log_event("ieee:101", "ELIG_INCLUDED", "LLM include")
        
        # 3 excluded (2 EF1, 1 EF4)
        store.log_event("ieee:200", "ELIG_EXCLUDED", "EF1")
        store.log_event("ieee:201", "ELIG_EXCLUDED", "EF1")
        store.log_event("ieee:202", "ELIG_EXCLUDED", "EF4")
        
        # 2 abstract-only
        store.log_event("ieee:300", "ELIG_ABSTRACT_ONLY", "No full text")
        store.log_event("ieee:301", "ELIG_ABSTRACT_ONLY", "No full text")
        
        report = generate_prisma_report(store)
        
        # Check assessed (ELIG_INCLUDED + ELIG_EXCLUDED) = 5
        assert "- **Full-text articles assessed for eligibility**: 5" in report
        
        # Check excluded = 3
        assert "- **Full-text articles excluded with reasons**: 3" in report
        
        # Check reasons grouped by criterion (detail column)
        assert "- **EF1**: 2 records" in report
        assert "- **EF4**: 1 records" in report
        
        # Check abstract-only = 2
        assert "- **Abstract-only (no full-text retrieved)**: 2" in report

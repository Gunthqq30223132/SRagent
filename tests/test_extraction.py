"""Tests for tools/evidence_extract.py (Evidence Extraction)."""

# LaTeX math block: $E = mc^2$

import json
from pathlib import Path

import httpx
import pytest
import respx

from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from tests.test_pipeline import make_doc
from tools.evidence_extract import run_extraction_batch, get_section_text

OLLAMA = "http://localhost:11434"


@pytest.fixture
def store(tmp_path):
    with StagingStore(tmp_path / "t.db") as s:
        yield s


class TestExtraction:
    @respx.mock
    def test_extraction_verified_success(self, store):
        # Insert a queued document
        doc = make_doc("ieee", "38111222", "Title RAG", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "We use the ImageNet-1k dataset for benchmarks."
        store.upsert(doc)
        store.log_event(doc.uid, "ELIG_INCLUDED", "")  # tiền điều kiện extract (FL-1)
        
        dummy_extraction = {
            "has_code_repo": {"value": "false", "quote": "", "section": "abstract"},
            "dataset_spec": {"value": "ImageNet-1k", "quote": "ImageNet-1k dataset", "section": "abstract"},
            "baselines": {"value": "none", "quote": "", "section": "abstract"},
            "metrics": {"value": "none", "quote": "", "section": "abstract"}
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_extraction)}
        }))
        
        count = run_extraction_batch(store, limit=1)
        assert count == 1
        
        # Verify db extractions (verified_only=False)
        exts = store.extractions("ieee:38111222", verified_only=False)
        assert len(exts) == 4
        
        # Check dataset_spec is verified=1
        dataset_spec = [e for e in exts if e["field"] == "dataset_spec"][0]
        assert dataset_spec["verified"] == 1
        
        # verified_only=True should return only 1 because dataset_spec is the only verified=1
        exts_verified = store.extractions("ieee:38111222", verified_only=True)
        assert len(exts_verified) == 1
        assert exts_verified[0]["field"] == "dataset_spec"

    @respx.mock
    def test_extraction_unverified_due_to_hallucinated_quote(self, store):
        doc = make_doc("ieee", "38111222", "Title RAG", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "We use the ImageNet-1k dataset for benchmarks."
        store.upsert(doc)
        store.log_event(doc.uid, "ELIG_INCLUDED", "")  # tiền điều kiện extract (FL-1)
        
        # Quote not in abstract
        dummy_extraction = {
            "has_code_repo": {"value": "false", "quote": "", "section": "abstract"},
            "dataset_spec": {"value": "ImageNet-1k", "quote": "non existent quote text", "section": "abstract"},
            "baselines": {"value": "none", "quote": "", "section": "abstract"},
            "metrics": {"value": "none", "quote": "", "section": "abstract"}
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_extraction)}
        }))
        
        count = run_extraction_batch(store, limit=1)
        assert count == 1
        
        exts_all = store.extractions("ieee:38111222", verified_only=False)
        dataset_spec = [e for e in exts_all if e["field"] == "dataset_spec"][0]
        assert dataset_spec["verified"] == 0  # should be unverified due to hallucinated quote
        
        # Verified only should return empty because dataset_spec is verified=0 and others are verified=2
        exts_verified = store.extractions("ieee:38111222", verified_only=True)
        assert len(exts_verified) == 0
        
        # Event should be logged
        events = [r["event_type"] for r in store.conn.execute("SELECT event_type FROM events WHERE uid = 'ieee:38111222'").fetchall()]
        assert "EXTRACT_UNVERIFIED" in events

    @respx.mock
    def test_extraction_unverified_due_to_wrong_section(self, store):
        doc = make_doc("ieee", "38111222", "Title RAG", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "We use the ImageNet-1k dataset for benchmarks."
        store.upsert(doc)
        store.log_event(doc.uid, "ELIG_INCLUDED", "")  # tiền điều kiện extract (FL-1)
        
        # Quote is in abstract, but section is context (where it is empty)
        dummy_extraction = {
            "has_code_repo": {"value": "false", "quote": "", "section": "abstract"},
            "dataset_spec": {"value": "ImageNet-1k", "quote": "ImageNet-1k dataset", "section": "context"},
            "baselines": {"value": "none", "quote": "", "section": "abstract"},
            "metrics": {"value": "accuracy", "quote": "", "section": "abstract"}
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_extraction)}
        }))
        
        count = run_extraction_batch(store, limit=1)
        assert count == 1
        
        exts_all = store.extractions("ieee:38111222", verified_only=False)
        dataset_spec = [e for e in exts_all if e["field"] == "dataset_spec"][0]
        assert dataset_spec["verified"] == 0  # should be unverified due to wrong section


class TestExtractionPrecondition:
    """FL-1 2026-07-19: extract phải đòi ELIG_INCLUDED — filter 'queued' trần
    từng gặm 10 doc tồn chưa qua sàng từ các run cũ trên DB không sạch."""

    def test_pending_uids_requires_elig_included(self, store):
        from tools.evidence_extract import pending_extraction_uids

        ok = make_doc("ieee", "38111222", "Passed eligibility", 1)
        ok.status = DocStatus.QUEUED
        store.upsert(ok)
        store.log_event(ok.uid, "ELIG_INCLUDED", "")

        stale = make_doc("ieee", "38111333", "Stale from old run", 1)
        stale.status = DocStatus.QUEUED
        store.upsert(stale)  # queued nhưng KHÔNG có ELIG_INCLUDED

        abstract_only = make_doc("ieee", "38111444", "No full text", 1)
        abstract_only.status = DocStatus.QUEUED
        store.upsert(abstract_only)
        store.log_event(abstract_only.uid, "ELIG_ABSTRACT_ONLY", "")

        assert pending_extraction_uids(store) == ["ieee:38111222"]

    def test_pending_uids_skips_already_extracted(self, store):
        from tools.evidence_extract import pending_extraction_uids

        doc = make_doc("ieee", "38111222", "Done already", 1)
        doc.status = DocStatus.QUEUED
        store.log_event(doc.uid, "ELIG_INCLUDED", "")
        store.add_extraction(doc.uid, "population", "adults", "adults", "methods", 1)

        assert pending_extraction_uids(store) == []


class TestExtractionMedReady:
    @respx.mock
    def test_context_overflow_guard_raises(self):
        from sr_agent.parser.ollama_client import OllamaClient
        from sr_agent.errors import ContextOverflowError
        client = OllamaClient()
        
        # Large prompt to exceed small num_ctx
        with pytest.raises(ContextOverflowError) as exc_info:
            client.generate_structured(
                system_prompt="This is a system prompt",
                user_prompt="This is a user prompt",
                schema_model=Document,
                num_ctx=5
            )
        assert exc_info.value.token_estimate == (len("This is a system prompt") + len("This is a user prompt")) // 3
        assert exc_info.value.token_estimate > 5

    @respx.mock
    def test_extraction_batch_handles_overflow(self, store, monkeypatch):
        monkeypatch.setenv("SR_NUM_CTX", "5")
        
        doc = make_doc("ieee", "38111222", "Title RAG", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "We use the ImageNet-1k dataset for benchmarks."
        store.upsert(doc)
        store.log_event(doc.uid, "ELIG_INCLUDED", "")
        
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        
        count = run_extraction_batch(store, limit=1)
        assert count == 1
        
        # Verify event logged
        events = store.conn.execute("SELECT event_type, detail FROM events WHERE uid = 'ieee:38111222'").fetchall()
        event_types = [e["event_type"] for e in events]
        assert "LLM_CONTEXT_OVERFLOW" in event_types
        
        overflow_event = [e for e in events if e["event_type"] == "LLM_CONTEXT_OVERFLOW"][0]
        assert "stage=extract" in overflow_event["detail"]
        assert "token_estimate=" in overflow_event["detail"]

    @respx.mock
    def test_extraction_full_text_only(self, store):
        doc = make_doc("ieee", "38111555", "Title Full Text Only", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = ""
        doc.sections = None
        doc.full_text = "The experimental results show that the ImageNet-1k dataset works fine."
        store.upsert(doc)
        store.log_event(doc.uid, "ELIG_INCLUDED", "")
        
        dummy_extraction = {
            "has_code_repo": {"value": "false", "quote": "", "section": "full_text"},
            "dataset_spec": {"value": "ImageNet-1k", "quote": "ImageNet-1k dataset", "section": "full_text"},
            "baselines": {"value": "none", "quote": "", "section": "full_text"},
            "metrics": {"value": "none", "quote": "", "section": "full_text"}
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_extraction)}
        }))
        
        count = run_extraction_batch(store, limit=1)
        assert count == 1
        
        exts = store.extractions("ieee:38111555", verified_only=True)
        assert len(exts) == 1
        assert exts[0]["field"] == "dataset_spec"
        assert exts[0]["verified"] == 1
        assert exts[0]["section"] == "full_text"

    @respx.mock
    def test_extraction_value_anchor_consistency(self, store):
        doc = make_doc("ieee", "38111666", "Value Anchor Test", 1)
        doc.status = DocStatus.QUEUED
        doc.abstract = "We tested with a dose of 50 mg. Preprocessing is randomized."
        store.upsert(doc)
        store.log_event(doc.uid, "ELIG_INCLUDED", "")
        
        dummy_extraction = {
            "has_code_repo": {"value": "500 mg", "quote": "50 mg", "section": "abstract"},
            "dataset_spec": {"value": "50", "quote": "50 mg", "section": "abstract"},
            "baselines": {"value": "randomized double-blind", "quote": "randomized", "section": "abstract"},
            "metrics": {"value": "none", "quote": "", "section": "abstract"}
        }
        respx.get(f"{OLLAMA}/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(dummy_extraction)}
        }))
        
        count = run_extraction_batch(store, limit=1)
        assert count == 1
        
        exts = store.extractions("ieee:38111666", verified_only=False)
        has_code_repo = [e for e in exts if e["field"] == "has_code_repo"][0]
        dataset_spec = [e for e in exts if e["field"] == "dataset_spec"][0]
        baselines = [e for e in exts if e["field"] == "baselines"][0]
        
        assert has_code_repo["verified"] == 0
        assert dataset_spec["verified"] == 1
        assert baselines["verified"] == 1
        
        events = store.conn.execute(
            "SELECT event_type, detail FROM events WHERE uid = 'ieee:38111666' AND event_type = 'EXTRACT_VALUE_MISMATCH'"
        ).fetchall()
        assert len(events) == 1
        assert events[0]["detail"] == "has_code_repo"
        assert "500 mg" not in events[0]["detail"]
        assert "50 mg" not in events[0]["detail"]

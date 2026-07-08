"""Tests for tools/evidence_extract.py (Evidence Extraction)."""

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

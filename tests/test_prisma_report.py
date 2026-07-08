"""Tests for tools/prisma_report.py."""

import json
from datetime import datetime, timezone
import pytest

from sr_agent.models.schemas import DocStatus
from sr_agent.store.staging import StagingStore
from tests.test_pipeline import make_doc
from tools.prisma_report import generate_prisma_report


@pytest.fixture
def store(tmp_path):
    with StagingStore(tmp_path / "t.db") as s:
        yield s


def test_prisma_report_counts(store):
    # 1. Setup mock runs
    report1 = {"fetched": 5, "duplicates": 1, "rejected_by_rubric": 2, "queued": 2}
    store.record_run("query1", datetime.now(timezone.utc).isoformat(), json.dumps(report1))
    
    # 2. Setup mock screening
    # Document 1: include
    doc1 = make_doc("ieee", "11111111", "Title 1", 1)
    doc1.status = DocStatus.QUEUED
    store.upsert(doc1)
    store.add_screen_verdict("ieee:11111111", "screener_a", "m1", "include", confidence="high")
    
    # Document 2: exclude
    doc2 = make_doc("ieee", "22222222", "Title 2", 1)
    doc2.status = DocStatus.QUEUED
    store.upsert(doc2)
    store.add_screen_verdict("ieee:22222222", "screener_a", "m1", "exclude", "ET1", "quote 2", "high")
    
    # 3. Setup mock approved
    doc3 = make_doc("ieee", "33333333", "Title 3", 1)
    doc3.status = DocStatus.APPROVED
    store.upsert(doc3)
    
    report = generate_prisma_report(store)
    
    # Assert identified: 5 (from runs)
    assert "- **Records identified from databases**: 5" in report
    # Assert duplicates: 1
    assert "- **Duplicate records removed**: 1" in report
    # Assert rubric excluded: 2
    assert "- **Records excluded by quality gate (rubric < 60)**: 2" in report
    # Assert screened: 2
    assert "- **Records screened**: 2" in report
    # Assert excluded: 1
    assert "- **Records excluded**: 1" in report
    # Assert inclusion: 1
    assert "- **Studies included in systematic review**: 1" in report
    # Assert specific exclusion reasons
    assert "- **ET1**: 1 records" in report

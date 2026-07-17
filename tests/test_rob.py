import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sr_agent.models.schemas import DocStatus, Document
from sr_agent.store.staging import StagingStore
from sr_agent.errors import SchemaValidationError

from tools.rob_run import (
    compute_rob2_overall,
    compute_minors_overall,
    compute_agreement_stats,
    run_rob_batch,
    StudyTypeClassification,
    RoB2DomainAssessment,
    RoB2LLMResponse,
    MinorsItemAssessment,
    MinorsLLMResponse,
)
from tools.protocol_build import ReviewProtocol


# ----------------- Cochrane RoB2 & MINORS Pure Algorithms Tests -----------------

def test_compute_rob2_overall():
    # Low: if all are Low
    assert compute_rob2_overall("Low", "Low", "Low", "Low", "Low") == "Low"
    
    # High: if at least one is High
    assert compute_rob2_overall("Low", "High", "Low", "Low", "Low") == "High"
    assert compute_rob2_overall("High", "High", "Some concerns", "Low", "Low") == "High"
    
    # Some concerns: if no High/VOID, and at least one Some concerns
    assert compute_rob2_overall("Low", "Some concerns", "Low", "Low", "Low") == "Some concerns"
    assert compute_rob2_overall("Some concerns", "Some concerns", "Low", "Low", "Low") == "Some concerns"

    # VOID: if any domain is VOID (priority: VOID > High > Some concerns > Low)
    assert compute_rob2_overall("Low", "High", "VOID", "Low", "Low") == "VOID"
    assert compute_rob2_overall("VOID", "Low", "Low", "Low", "Low") == "VOID"


def test_compute_rob2_overall_unknown_rule_fails_closed():
    # Bảo thủ bất đối xứng: rule lạ phải raise, KHÔNG được âm thầm trả "Low"
    # bất kể mọi domain thực tế là gì (kể cả toàn High).
    with pytest.raises(ValueError):
        compute_rob2_overall("High", "High", "High", "High", "High", rule="not_a_real_rule")


def test_compute_minors_overall():
    # Test MINORS score summation
    scores_non_comparative = {f"item{i}": "2" for i in range(1, 9)}
    assert compute_minors_overall(scores_non_comparative) == "16"
    
    scores_mixed = {
        "item1": "2", "item2": "1", "item3": "0", "item4": "2",
        "item5": "1", "item6": "2", "item7": "1", "item8": "0"
    }
    assert compute_minors_overall(scores_mixed) == "9"

    scores_comparative = {f"item{i}": "2" for i in range(1, 13)}
    assert compute_minors_overall(scores_comparative) == "24"

    # VOID logic: if any item is VOID, overall is VOID
    scores_void = {f"item{i}": ("2" if i != 3 else "VOID") for i in range(1, 9)}
    assert compute_minors_overall(scores_void) == "VOID"


def test_compute_agreement_stats():
    ratings_a = ["Low", "Low", "Some concerns", "High", "Low"]
    ratings_b = ["Low", "Low", "Some concerns", "High", "Low"]
    po, kappa, mismatches = compute_agreement_stats(ratings_a, ratings_b)
    assert po == 1.0
    assert kappa == 1.0
    assert mismatches == []

    ratings_b2 = ["Low", "High", "Some concerns", "High", "Low"]
    po2, kappa2, mismatches2 = compute_agreement_stats(ratings_a, ratings_b2)
    assert po2 == 0.8
    assert mismatches2 == [1]


# ----------------- DB and Flow Tests using Mocks -----------------

@pytest.fixture
def temp_db():
    temp_fd, temp_path = tempfile.mkstemp()
    db_path = Path(temp_path)
    yield db_path
    os.close(temp_fd)
    if db_path.exists():
        db_path.unlink()


def create_dummy_protocol(overall_rule="rob2_standard", minors_threshold=16) -> ReviewProtocol:
    # Need to verify if ReviewProtocol has overall_rule and minors_threshold
    # Using model_validate allows extra fields if config permits, or we can patch/parse dynamically.
    proto_data = {
        "topic_vi": "Test Topic",
        "population": {"concept": "Adults", "synonyms": ["adult"]},
        "intervention": {"concept": "Propofol", "synonyms": ["propofol"]},
        "languages": ["English"],
        "exclusion_criteria": ["ET1"],
        "overall_rule": overall_rule,
        "minors_threshold": minors_threshold
    }
    return ReviewProtocol.model_validate(proto_data)


def create_dummy_document(uid: str, text: str) -> Document:
    source, source_id = uid.split(":", 1)
    return Document.model_validate({
        "uid": uid,
        "source": source.lower(),
        "source_id": source_id,
        "authority_tier": 1,
        "title": "A Study",
        "title_normalized": "a study",
        "abstract": text,
        "full_text": text,
        "status": "queued",
        "fetched_at": "2026-07-14T12:00:00Z"
    })


@patch("tools.rob_run.OllamaClient")
def test_rob_rct_consensus(mock_client_class, temp_db):
    """Test that model A and B agree on RCT study type and have matching verdicts."""
    mock_client_a = MagicMock()
    mock_client_b = MagicMock()
    mock_client_class.side_effect = lambda model: mock_client_a if "llama" in model else mock_client_b

    # Mock availability
    mock_client_a.is_available.return_value = True
    mock_client_b.is_available.return_value = True
    mock_client_a.model = "llama3.1:8b"
    mock_client_b.model = "gemma4:e4b"

    # Mock step 1: Classify Study Type (agree on RCT)
    mock_client_a.generate_structured.side_effect = [
        StudyTypeClassification(study_type="RCT", evidence_quote="randomized study"),
        RoB2LLMResponse(
            study_type="RCT",
            d1_randomization=RoB2DomainAssessment(verdict="Low", evidence_quote="randomized study"),
            d2_deviations=RoB2DomainAssessment(verdict="Low", evidence_quote="no deviation"),
            d3_missing_outcome=RoB2DomainAssessment(verdict="Low", evidence_quote="no missing data"),
            d4_measurement=RoB2DomainAssessment(verdict="Low", evidence_quote="blinded assessors"),
            d5_selection=RoB2DomainAssessment(verdict="Low", evidence_quote="registered protocol")
        )
    ]
    mock_client_b.generate_structured.side_effect = [
        StudyTypeClassification(study_type="RCT", evidence_quote="randomized study"),
        RoB2LLMResponse(
            study_type="RCT",
            d1_randomization=RoB2DomainAssessment(verdict="Low", evidence_quote="randomized study"),
            d2_deviations=RoB2DomainAssessment(verdict="Low", evidence_quote="no deviation"),
            d3_missing_outcome=RoB2DomainAssessment(verdict="Low", evidence_quote="no missing data"),
            d4_measurement=RoB2DomainAssessment(verdict="Low", evidence_quote="blinded assessors"),
            d5_selection=RoB2DomainAssessment(verdict="Low", evidence_quote="registered protocol")
        )
    ]

    with StagingStore(temp_db) as store:
        uid = "ieee:10000001"
        doc = create_dummy_document(uid, "This is a randomized study with no deviation and no missing data. Blinded assessors reviewed the registered protocol.")
        store.upsert(doc)
        store.log_event(uid, "ELIG_INCLUDED", "passed eligibility")

        protocol = create_dummy_protocol()
        count = run_rob_batch(store, protocol, limit=1)
        assert count == 1

        # Check DB state
        events = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (uid,)).fetchall()]
        assert "ROB_COMPLETED" in events
        assert "ROB_ESCALATED" not in events

        # Check assessments stored: 5 domains + 1 overall row per agent = 6 * 2 = 12 rows
        assessments = store.get_rob_assessments(uid)
        assert len(assessments) == 12
        for r in assessments:
            assert r["study_type"] == "RCT"
            if r["domain"] == "__overall__":
                assert r["verdict"] == "Low"


@patch("tools.rob_run.OllamaClient")
def test_rob_classification_quote_fail_escalates(mock_client_class, temp_db):
    """Test that a classification quote validation failure sets type to VOID and triggers ROB_ESCALATED."""
    mock_client_a = MagicMock()
    mock_client_b = MagicMock()
    mock_client_class.side_effect = lambda model: mock_client_a if "llama" in model else mock_client_b

    mock_client_a.is_available.return_value = True
    mock_client_b.is_available.return_value = True
    mock_client_a.model = "llama3.1:8b"
    mock_client_b.model = "gemma4:e4b"

    # Model A returns a quote that is missing from text, so classification quote validation will fail.
    mock_client_a.generate_structured.side_effect = [
        StudyTypeClassification(study_type="RCT", evidence_quote="fabricated quote")
    ]
    mock_client_b.generate_structured.side_effect = [
        StudyTypeClassification(study_type="RCT", evidence_quote="randomized study")
    ]

    with StagingStore(temp_db) as store:
        uid = "ieee:10000002"
        doc = create_dummy_document(uid, "This is a randomized study.")
        store.upsert(doc)
        store.log_event(uid, "ELIG_INCLUDED", "passed eligibility")

        protocol = create_dummy_protocol()
        count = run_rob_batch(store, protocol, limit=1)
        assert count == 1

        # Mismatch (VOID vs RCT) leads to ROB_ESCALATED and halts before domains assessed
        events = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (uid,)).fetchall()]
        assert "ROB_ESCALATED" in events
        assert "ROB_COMPLETED" not in events
        
        # Check that no rob_assessments were written
        assessments = store.get_rob_assessments(uid)
        assert len(assessments) == 0


@patch("tools.rob_run.OllamaClient")
def test_rob_domain_quote_fail_void_penalty(mock_client_class, temp_db):
    """Test that a fabricated/empty domain quote triggers VOID penalty (saves VOID in DB and escalates)."""
    mock_client_a = MagicMock()
    mock_client_b = MagicMock()
    mock_client_class.side_effect = lambda model: mock_client_a if "llama" in model else mock_client_b

    mock_client_a.is_available.return_value = True
    mock_client_b.is_available.return_value = True
    mock_client_a.model = "llama3.1:8b"
    mock_client_b.model = "gemma4:e4b"

    # Model A outputs invalid quote for d1 -> verdict for d1 becomes VOID.
    mock_client_a.generate_structured.side_effect = [
        StudyTypeClassification(study_type="RCT", evidence_quote="randomized study"),
        RoB2LLMResponse(
            study_type="RCT",
            d1_randomization=RoB2DomainAssessment(verdict="Low", evidence_quote="fabricated quote"),
            d2_deviations=RoB2DomainAssessment(verdict="Low", evidence_quote="no deviation"),
            d3_missing_outcome=RoB2DomainAssessment(verdict="Low", evidence_quote="no missing data"),
            d4_measurement=RoB2DomainAssessment(verdict="Low", evidence_quote="blinded assessors"),
            d5_selection=RoB2DomainAssessment(verdict="Low", evidence_quote="registered protocol")
        )
    ]
    mock_client_b.generate_structured.side_effect = [
        StudyTypeClassification(study_type="RCT", evidence_quote="randomized study"),
        RoB2LLMResponse(
            study_type="RCT",
            d1_randomization=RoB2DomainAssessment(verdict="Low", evidence_quote="randomized study"),
            d2_deviations=RoB2DomainAssessment(verdict="Low", evidence_quote="no deviation"),
            d3_missing_outcome=RoB2DomainAssessment(verdict="Low", evidence_quote="no missing data"),
            d4_measurement=RoB2DomainAssessment(verdict="Low", evidence_quote="blinded assessors"),
            d5_selection=RoB2DomainAssessment(verdict="Low", evidence_quote="registered protocol")
        )
    ]

    with StagingStore(temp_db) as store:
        uid = "ieee:10000003"
        doc = create_dummy_document(uid, "This is a randomized study with no deviation and no missing data. Blinded assessors reviewed the registered protocol.")
        store.upsert(doc)
        store.log_event(uid, "ELIG_INCLUDED", "passed eligibility")

        protocol = create_dummy_protocol()
        count = run_rob_batch(store, protocol, limit=1)
        assert count == 1

        # Check DB state: since A has VOID in d1, its overall becomes VOID. Disagreement or VOID triggers ROB_ESCALATED.
        events = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (uid,)).fetchall()]
        assert "ROB_ESCALATED" in events
        assert "ROB_COMPLETED" not in events

        # Even though escalated, all assessments (including overall rows) must be saved.
        assessments = store.get_rob_assessments(uid)
        assert len(assessments) == 12
        
        # Verify Model A's d1 and overall are indeed VOID in the database (no washing to High/Low!)
        d1_a = [r for r in assessments if r["agent"] == "rob_a" and r["domain"] == "d1_randomization"][0]
        assert d1_a["verdict"] == "VOID"
        
        overall_a = [r for r in assessments if r["agent"] == "rob_a" and r["domain"] == "__overall__"][0]
        assert overall_a["verdict"] == "VOID"


@patch("tools.rob_run.OllamaClient")
def test_rob_overall_review_logged(mock_client_class, temp_db):
    """Test that if consensus is 'Some concerns' with >= 2 domains having Some concerns, ROB_OVERALL_REVIEW is logged."""
    mock_client_a = MagicMock()
    mock_client_b = MagicMock()
    mock_client_class.side_effect = lambda model: mock_client_a if "llama" in model else mock_client_b

    mock_client_a.is_available.return_value = True
    mock_client_b.is_available.return_value = True
    mock_client_a.model = "llama3.1:8b"
    mock_client_b.model = "gemma4:e4b"

    # Both models output 'Some concerns' for d1 and d2
    mock_client_a.generate_structured.side_effect = [
        StudyTypeClassification(study_type="RCT", evidence_quote="randomized study"),
        RoB2LLMResponse(
            study_type="RCT",
            d1_randomization=RoB2DomainAssessment(verdict="Some concerns", evidence_quote="randomized study"),
            d2_deviations=RoB2DomainAssessment(verdict="Some concerns", evidence_quote="no deviation"),
            d3_missing_outcome=RoB2DomainAssessment(verdict="Low", evidence_quote="no missing data"),
            d4_measurement=RoB2DomainAssessment(verdict="Low", evidence_quote="blinded assessors"),
            d5_selection=RoB2DomainAssessment(verdict="Low", evidence_quote="registered protocol")
        )
    ]
    mock_client_b.generate_structured.side_effect = [
        StudyTypeClassification(study_type="RCT", evidence_quote="randomized study"),
        RoB2LLMResponse(
            study_type="RCT",
            d1_randomization=RoB2DomainAssessment(verdict="Some concerns", evidence_quote="randomized study"),
            d2_deviations=RoB2DomainAssessment(verdict="Some concerns", evidence_quote="no deviation"),
            d3_missing_outcome=RoB2DomainAssessment(verdict="Low", evidence_quote="no missing data"),
            d4_measurement=RoB2DomainAssessment(verdict="Low", evidence_quote="blinded assessors"),
            d5_selection=RoB2DomainAssessment(verdict="Low", evidence_quote="registered protocol")
        )
    ]

    with StagingStore(temp_db) as store:
        uid = "ieee:10000004"
        doc = create_dummy_document(uid, "This is a randomized study with no deviation and no missing data. Blinded assessors reviewed the registered protocol.")
        store.upsert(doc)
        store.log_event(uid, "ELIG_INCLUDED", "passed eligibility")

        protocol = create_dummy_protocol()
        count = run_rob_batch(store, protocol, limit=1)
        assert count == 1

        events = [e["event_type"] for e in store.conn.execute("SELECT event_type FROM events WHERE uid = ?", (uid,)).fetchall()]
        assert "ROB_COMPLETED" in events
        assert "ROB_OVERALL_REVIEW" in events


@patch("tools.rob_run.OllamaClient")
def test_rob_idempotency(mock_client_class, temp_db):
    """Test that running the batch runner twice on the same document does not duplicate database rows."""
    mock_client_a = MagicMock()
    mock_client_b = MagicMock()
    mock_client_class.side_effect = lambda model: mock_client_a if "llama" in model else mock_client_b

    mock_client_a.is_available.return_value = True
    mock_client_b.is_available.return_value = True
    mock_client_a.model = "llama3.1:8b"
    mock_client_b.model = "gemma4:e4b"

    # First run mocks
    mock_client_a.generate_structured.side_effect = [
        StudyTypeClassification(study_type="RCT", evidence_quote="randomized study"),
        RoB2LLMResponse(
            study_type="RCT",
            d1_randomization=RoB2DomainAssessment(verdict="Low", evidence_quote="randomized study"),
            d2_deviations=RoB2DomainAssessment(verdict="Low", evidence_quote="no deviation"),
            d3_missing_outcome=RoB2DomainAssessment(verdict="Low", evidence_quote="no missing data"),
            d4_measurement=RoB2DomainAssessment(verdict="Low", evidence_quote="blinded assessors"),
            d5_selection=RoB2DomainAssessment(verdict="Low", evidence_quote="registered protocol")
        )
    ]
    mock_client_b.generate_structured.side_effect = [
        StudyTypeClassification(study_type="RCT", evidence_quote="randomized study"),
        RoB2LLMResponse(
            study_type="RCT",
            d1_randomization=RoB2DomainAssessment(verdict="Low", evidence_quote="randomized study"),
            d2_deviations=RoB2DomainAssessment(verdict="Low", evidence_quote="no deviation"),
            d3_missing_outcome=RoB2DomainAssessment(verdict="Low", evidence_quote="no missing data"),
            d4_measurement=RoB2DomainAssessment(verdict="Low", evidence_quote="blinded assessors"),
            d5_selection=RoB2DomainAssessment(verdict="Low", evidence_quote="registered protocol")
        )
    ]

    with StagingStore(temp_db) as store:
        uid = "ieee:10000005"
        doc = create_dummy_document(uid, "This is a randomized study with no deviation and no missing data. Blinded assessors reviewed the registered protocol.")
        store.upsert(doc)
        
        protocol = create_dummy_protocol()

        # Run 1
        store.log_event(uid, "ELIG_INCLUDED", "passed eligibility")
        run_rob_batch(store, protocol, limit=1)
        
        assessments_run1 = store.get_rob_assessments(uid)
        assert len(assessments_run1) == 12

        # Reset mocks for second run
        mock_client_a.generate_structured.side_effect = [
            StudyTypeClassification(study_type="RCT", evidence_quote="randomized study"),
            RoB2LLMResponse(
                study_type="RCT",
                d1_randomization=RoB2DomainAssessment(verdict="Low", evidence_quote="randomized study"),
                d2_deviations=RoB2DomainAssessment(verdict="Low", evidence_quote="no deviation"),
                d3_missing_outcome=RoB2DomainAssessment(verdict="Low", evidence_quote="no missing data"),
                d4_measurement=RoB2DomainAssessment(verdict="Low", evidence_quote="blinded assessors"),
                d5_selection=RoB2DomainAssessment(verdict="Low", evidence_quote="registered protocol")
            )
        ]
        mock_client_b.generate_structured.side_effect = [
            StudyTypeClassification(study_type="RCT", evidence_quote="randomized study"),
            RoB2LLMResponse(
                study_type="RCT",
                d1_randomization=RoB2DomainAssessment(verdict="Low", evidence_quote="randomized study"),
                d2_deviations=RoB2DomainAssessment(verdict="Low", evidence_quote="no deviation"),
                d3_missing_outcome=RoB2DomainAssessment(verdict="Low", evidence_quote="no missing data"),
                d4_measurement=RoB2DomainAssessment(verdict="Low", evidence_quote="blinded assessors"),
                d5_selection=RoB2DomainAssessment(verdict="Low", evidence_quote="registered protocol")
            )
        ]

        # Reset document status and run again (to simulate retrying the batch)
        # To run it again, we need it to not have ROB_COMPLETED in DB events
        store.conn.execute("DELETE FROM events WHERE uid = ? AND event_type LIKE 'ROB_%'", (uid,))
        store.conn.commit()
        
        # Run 2
        run_rob_batch(store, protocol, limit=1)
        
        assessments_run2 = store.get_rob_assessments(uid)
        # Should still be exactly 12, not 24! (Due to deletion of old rows before rerun)
        assert len(assessments_run2) == 12

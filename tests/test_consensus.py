"""
Tests for tools/consensus_ledger.py derived strictly from docs/specs/BS4-implementation.md §9(a-h).
# LaTeX math block: $W = \sum w_i$
"""

import pytest
from tools.consensus_ledger import (
    Claim,
    build_ledger,
    detect_conflicts,
    build_anchor_set,
    render_table,
    rob_weight,
    APPROX_LEXICON,
)


def test_spec_9a_verified_extractions_and_human_rob_priority():
    """(a) ledger chỉ nhận verified=1; human overall thắng rob_a."""
    extractions = [
        {
            "claim_id": "clm-doc1",
            "run_id": "run1",
            "uid": "doc1",
            "field": "recovery_time",
            "value": "12.5 min",
            "quote": "Recovery time was 12.5 min, significantly shorter.",
            "verified": 1,
        },
        {
            "claim_id": "clm-doc2",
            "run_id": "run1",
            "uid": "doc2",
            "field": "recovery_time",
            "value": "15 min",
            "quote": "Mean recovery time was 15 min.",
            "verified": 2,  # Should be excluded
        },
        {
            "claim_id": "clm-doc3",
            "run_id": "run1",
            "uid": "doc3",
            "field": "recovery_time",
            "value": "20 min",
            "quote": "Recovery time was 20 min.",
            "verified": 0,  # Should be excluded
        },
    ]

    # rob_map mapping uid -> rob_overall
    rob_map = {
        "doc1": "Low",
    }

    protocol = {
        "outcomes": [
            {
                "id": "primary_recovery",
                "outcome_id": "primary_recovery",
                "match_fields": ["recovery_time"],
                "direction_terms": {
                    "decrease": ["shorter", "decreas"],
                    "increase": ["prolong", "increas"],
                },
            }
        ],
        "unit_lexicon": ["min"],
    }

    claims = build_ledger(extractions, rob_map, protocol)
    assert len(claims) == 1
    assert claims[0].uid == "doc1"
    assert claims[0].rob_overall in ("Low", "low")
    assert claims[0].weight == rob_weight(claims[0].rob_overall)


def test_spec_9b_void_weight_zero_retained_in_ledger():
    """(b) VOID weight 0 vẫn nằm ledger."""
    extractions = [
        {
            "claim_id": "clm-void",
            "run_id": "run1",
            "uid": "doc_void",
            "field": "primary_outcome",
            "value": "5 mg",
            "quote": "Dose was 5 mg.",
            "verified": 1,
        }
    ]
    rob_map = {"doc_void": "VOID"}

    protocol = {
        "outcomes": [
            {"id": "dosing", "outcome_id": "dosing", "match_fields": ["primary_outcome"]}
        ],
        "unit_lexicon": ["mg"],
    }

    claims = build_ledger(extractions, rob_map, protocol)
    assert len(claims) == 1
    assert claims[0].rob_overall == "VOID"
    assert claims[0].weight == 0.0
    assert rob_weight("VOID") == 0.0


def test_spec_9c_direction_matching_invariants():
    """(c) direction: match 1 nhóm => gán, match 2 nhóm => NULL, thiếu direction_terms => NULL."""
    protocol = {
        "outcomes": [
            {
                "id": "o1",
                "outcome_id": "o1",
                "match_fields": ["f1"],
                "direction_terms": {
                    "decrease": ["reduced", "shorter"],
                    "increase": ["increased", "longer"],
                },
            },
            {
                "id": "o2",
                "outcome_id": "o2",
                "match_fields": ["f2"],
                # No direction_terms
            },
        ]
    }

    extractions = [
        {
            "claim_id": "clm-d1",
            "run_id": "run1",
            "uid": "d1",
            "field": "f1",
            "value": "10",
            "quote": "It significantly reduced recovery.",
            "verified": 1,
        },
        {
            "claim_id": "clm-d2",
            "run_id": "run1",
            "uid": "d2",
            "field": "f1",
            "value": "12",
            "quote": "It reduced pain but increased nausea.",  # Matches both decrease and increase
            "verified": 1,
        },
        {
            "claim_id": "clm-d3",
            "run_id": "run1",
            "uid": "d3",
            "field": "f2",
            "value": "5",
            "quote": "Value was 5.",
            "verified": 1,
        },
    ]

    claims = build_ledger(extractions, {}, protocol)
    claim_map = {c.uid: c for c in claims}

    assert claim_map["d1"].direction == "decrease"
    assert claim_map["d2"].direction is None
    assert claim_map["d3"].direction is None


def test_spec_9d_conflict_detection():
    """(d) conflict: đối nghịch => nhóm đúng, cùng hướng/NULL => không nhóm."""
    c1 = Claim(
        claim_id="clm-1",
        run_id="run1",
        outcome_id="o1",
        uid="doc1",
        field="f1",
        value="10",
        quote="q1",
        rob_overall="Low",
        weight=1.0,
        direction="increase",
        conflict_group=None,
        created_at="2026-07-21T00:00:00Z",
    )
    c2 = Claim(
        claim_id="clm-2",
        run_id="run1",
        outcome_id="o1",
        uid="doc2",
        field="f1",
        value="5",
        quote="q2",
        rob_overall="Low",
        weight=1.0,
        direction="decrease",
        conflict_group=None,
        created_at="2026-07-21T00:00:00Z",
    )
    c3 = Claim(
        claim_id="clm-3",
        run_id="run1",
        outcome_id="o2",
        uid="doc3",
        field="f2",
        value="8",
        quote="q3",
        rob_overall="Low",
        weight=1.0,
        direction="increase",
        conflict_group=None,
        created_at="2026-07-21T00:00:00Z",
    )
    c4 = Claim(
        claim_id="clm-4",
        run_id="run1",
        outcome_id="o2",
        uid="doc4",
        field="f2",
        value="9",
        quote="q4",
        rob_overall="Low",
        weight=1.0,
        direction="increase",  # Same direction, no conflict
        conflict_group=None,
        created_at="2026-07-21T00:00:00Z",
    )

    claims = detect_conflicts([c1, c2, c3, c4])
    claim_dict = {c.claim_id: c for c in claims}

    assert claim_dict["clm-1"].conflict_group == "cfl-o1"
    assert claim_dict["clm-2"].conflict_group == "cfl-o1"
    assert claim_dict["clm-3"].conflict_group is None
    assert claim_dict["clm-4"].conflict_group is None


def test_spec_9e_anchor_set_building():
    """(e) anchor set extracts raw value, numbers, and number-unit pairs."""
    claims = [
        Claim(
            claim_id="clm-1",
            run_id="run1",
            outcome_id="o1",
            uid="doc1",
            field="f1",
            value="12.5 mg",
            quote="q1",
            rob_overall="Low",
            weight=1.0,
            direction="increase",
            conflict_group=None,
            created_at="2026-07-21T00:00:00Z",
        ),
        Claim(
            claim_id="clm-2",
            run_id="run1",
            outcome_id="__unmapped__",
            uid="doc2",
            field="f2",
            value="99 mg",
            quote="q2",
            rob_overall="Low",
            weight=1.0,
            direction=None,
            conflict_group=None,
            created_at="2026-07-21T00:00:00Z",
        ),
        Claim(
            claim_id="clm-3",
            run_id="run1",
            outcome_id="o1",
            uid="doc3",
            field="f3",
            value="50 mg",
            quote="q3",
            rob_overall="VOID",
            weight=0.0,
            direction=None,
            conflict_group=None,
            created_at="2026-07-21T00:00:00Z",
        ),
    ]

    # Test anchor set builder
    anchors = build_anchor_set(claims)
    assert "12.5 mg" in anchors or "12.5" in anchors
    assert "99 mg" not in anchors  # unmapped excluded
    assert "50 mg" not in anchors  # weight=0 excluded


def test_spec_9f_approx_lexicon_exported():
    """(f) Hằng APPROX_LEXICON export được."""
    assert isinstance(APPROX_LEXICON, (list, tuple, set))
    for term in ["approximately", "about", "around", "roughly", "~", "khoảng", "xấp xỉ", "gần"]:
        assert term in APPROX_LEXICON


def test_spec_9g_render_table_formatting():
    """(g) render_table: markdown nhóm theo outcome, conflicting nhóm riêng."""
    c1 = Claim(
        claim_id="clm-100",
        run_id="run1",
        outcome_id="o1",
        uid="doc1",
        field="f1",
        value="10 mg",
        quote="q1",
        rob_overall="Low",
        weight=1.0,
        direction="increase",
        conflict_group="cfl-o1",
        created_at="2026-07-21T00:00:00Z",
    )
    c2 = Claim(
        claim_id="clm-101",
        run_id="run1",
        outcome_id="o1",
        uid="doc2",
        field="f1",
        value="5 mg",
        quote="q2",
        rob_overall="High",
        weight=0.25,
        direction="decrease",
        conflict_group="cfl-o1",
        created_at="2026-07-21T00:00:00Z",
    )

    table = render_table([c1, c2])
    assert "CONFLICTING — not pooled" in table
    assert "doc1" in table
    assert "clm-100" in table
    assert "doc2" in table


def test_spec_9h_rob_weight_mapping():
    """(h) rob_weight maps RoB ratings deterministically."""
    assert rob_weight("low") == 1.0 or rob_weight("Low") == 1.0 or rob_weight("high") == 1.0 or rob_weight("High") == 1.0
    assert rob_weight("VOID") == 0.0

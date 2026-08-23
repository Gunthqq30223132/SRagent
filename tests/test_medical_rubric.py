"""Test rubric y khoa — khoá lại kết quả đối chứng đã đo được.

Bối cảnh: chạy thử chủ đề chống đông chu phẫu cho thấy rubric CS mặc định LOẠI
thử nghiệm BRIDGE (RCT của NEJM, PMID 26095867) với 45.16 điểm, và xếp một bài
tổng quan tường thuật CAO HƠN một phân tích gộp. Các test dưới đây khoá lại
hành vi đã sửa để không tái phát.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sr_agent.models.schemas import DocStatus, Document
from sr_agent.quality.rubric import DEFAULT_RUBRIC, score_document

MEDICAL_RUBRIC = json.loads(
    (Path(__file__).resolve().parent.parent / "tools" / "profiles" / "medical.json")
    .read_text(encoding="utf-8")
)

NOW = datetime.now(timezone.utc)
ABSTRACT_80_WORDS = " ".join(["từ"] * 80)


def make_doc(pmid: str, *, years_old: float, evidence_level: int | None,
             abstract: str = ABSTRACT_80_WORDS) -> Document:
    return Document(
        uid="", source="pubmed", source_id=f"pubmed:{pmid}", authority_tier=1,
        title=f"Bài {pmid}", abstract=abstract, authors=["A B"],
        published_date=NOW - timedelta(days=int(years_old * 365.25)),
        evidence_level=evidence_level, status=DocStatus.FETCHED,
    )


class TestEvidenceRankRule:
    def test_meta_analysis_scores_above_narrative_review(self):
        meta = score_document(make_doc("1", years_old=1, evidence_level=1),
                              MEDICAL_RUBRIC).total
        review = score_document(make_doc("2", years_old=1, evidence_level=7),
                                MEDICAL_RUBRIC).total
        assert meta > review

    def test_unclassified_is_neutral_not_zero(self):
        """None = chưa phân loại. Cho 0 điểm sẽ âm thầm loại mọi bài arXiv/IEEE."""
        unranked = score_document(make_doc("3", years_old=1, evidence_level=None),
                                  MEDICAL_RUBRIC)
        weakest = score_document(make_doc("4", years_old=1, evidence_level=9),
                                 MEDICAL_RUBRIC)
        assert unranked.total > weakest.total

    def test_full_evidence_hierarchy_is_monotonic(self):
        scores = [
            score_document(make_doc(str(lvl), years_old=1, evidence_level=lvl),
                           MEDICAL_RUBRIC).total
            for lvl in (1, 2, 3, 4, 5, 6, 7, 9)
        ]
        assert scores == sorted(scores, reverse=True), scores


class TestLandmarkTrialNoLongerRejected:
    """Hồi quy trực tiếp cho lỗi đã đo: BRIDGE bị rubric CS loại ở 45.16 điểm."""

    @pytest.fixture
    def bridge(self):
        # RCT của NEJM 2015, 11 năm tuổi, không có repo code (như mọi bài y khoa).
        return make_doc("26095867", years_old=11.0, evidence_level=3,
                        abstract=" ".join(["từ"] * 55))

    def test_cs_rubric_rejects_it(self, bridge):
        result = score_document(bridge, DEFAULT_RUBRIC)
        assert result.total < DEFAULT_RUBRIC["pass_threshold"]

    def test_medical_rubric_accepts_it(self, bridge):
        result = score_document(bridge, MEDICAL_RUBRIC)
        assert result.total >= MEDICAL_RUBRIC["pass_threshold"], result.total

    def test_medical_rubric_has_no_code_repo_criterion(self):
        """Tiêu chí artifact_availability chiếm 25% mà bài y khoa luôn được 0."""
        keys = {c["key"] for c in MEDICAL_RUBRIC["criteria"]}
        assert "artifact_availability" not in keys

    def test_recency_window_spans_decades(self):
        recency = next(c for c in MEDICAL_RUBRIC["criteria"] if c["key"] == "recency")
        assert recency["params"]["zero_at"] >= 40

    def test_weights_sum_to_100(self):
        assert sum(c["weight"] for c in MEDICAL_RUBRIC["criteria"]) == 100


class TestCsRubricUnchanged:
    def test_cs_docs_without_evidence_level_still_score_the_same(self):
        """Trường evidence_level mới không được đổi điểm của tài liệu CS."""
        doc = Document(
            uid="", source="arxiv", source_id="arxiv:2401.12345", authority_tier=2,
            title="Bài CS", abstract=ABSTRACT_80_WORDS, authors=["A B"],
            published_date=NOW - timedelta(days=365), status=DocStatus.FETCHED,
        )
        assert doc.evidence_level is None
        assert score_document(doc, DEFAULT_RUBRIC).total > 0

    def test_default_rubric_still_has_five_criteria(self):
        assert len(DEFAULT_RUBRIC["criteria"]) == 5

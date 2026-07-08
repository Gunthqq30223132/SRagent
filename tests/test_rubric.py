from datetime import datetime, timedelta, timezone

from sr_agent.models.schemas import Document
from sr_agent.quality.rubric import DEFAULT_RUBRIC, score_document


def doc(**overrides):
    base = dict(
        uid="", source="ieee", source_id="38111222", authority_tier=1,
        title="Efficient Transformer Inference",
    )
    base.update(overrides)
    return Document(**base)


RICH_ABSTRACT = (
    "We present a systematic evaluation of quantization strategies. "
    + "Our code is available at https://github.com/example/repo and the dataset "
    + "is hosted on huggingface.co/datasets. " + "Extensive experiments show gains. " * 50
)


def test_full_marks_document():
    d = doc(
        abstract=RICH_ABSTRACT,
        authors=["A"],
        published_date=datetime.now(timezone.utc) - timedelta(days=100),
    )
    result = score_document(d)
    assert result.total == 100.0
    assert result.passed


def test_empty_preprint_fails_gate():
    d = doc(source="arxiv", source_id="arxiv:2401.00001", authority_tier=2)
    result = score_document(d)
    assert not result.passed
    assert result.total < DEFAULT_RUBRIC["pass_threshold"]


def test_breakdown_has_all_criteria_with_reasons():
    result = score_document(doc())
    keys = [c.key for c in result.breakdown]
    assert keys == [
        "source_authority", "recency", "artifact_availability",
        "abstract_completeness", "metadata_integrity",
    ]
    assert all(c.reason for c in result.breakdown)


def test_recency_linear_decay():
    mid_age = doc(published_date=datetime.now(timezone.utc) - timedelta(days=6 * 365))
    result = score_document(mid_age)
    recency = next(c for c in result.breakdown if c.key == "recency")
    assert 0 < recency.sub_score < 100  # 6 năm: giữa full(2) và zero(10)


def test_determinism():
    d = doc(abstract=RICH_ABSTRACT, published_date=datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert score_document(d) == score_document(d)

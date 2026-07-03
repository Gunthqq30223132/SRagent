import pytest
from pydantic import ValidationError

from sr_agent.models.schemas import (
    CanonicalRole,
    Document,
    IMRADSections,
    PAECSections,
    Section,
    make_uid,
    normalize_title,
)


def make_doc(**overrides):
    base = dict(
        uid="",
        source="pubmed",
        source_id="12345678",
        authority_tier=1,
        title="A Study of Things",
    )
    base.update(overrides)
    return Document(**base)


class TestIdRules:
    def test_pubmed_8_digit_ok(self):
        assert make_doc().uid == "pubmed:12345678"

    def test_pubmed_wrong_length_rejected(self):
        with pytest.raises(ValidationError):
            make_doc(source_id="1234567")

    def test_arxiv_format_ok(self):
        doc = make_doc(source="arxiv", source_id="arxiv:2401.12345", authority_tier=2)
        assert doc.uid == "arxiv:2401.12345"

    def test_arxiv_missing_prefix_rejected(self):
        with pytest.raises(ValidationError):
            make_doc(source="arxiv", source_id="2401.12345", authority_tier=2)

    def test_uid_mismatch_rejected(self):
        with pytest.raises(ValidationError):
            make_doc(uid="pubmed:99999999")

    def test_make_uid_no_double_prefix(self):
        assert make_uid("arxiv", "arxiv:2401.12345") == "arxiv:2401.12345"
        assert make_uid("pubmed", "12345678") == "pubmed:12345678"


class TestNormalizeTitle:
    def test_case_punct_whitespace(self):
        assert normalize_title("  Deep   Learning: A Survey!  ") == "deep learning a survey"

    def test_diacritics_stripped(self):
        # dấu thanh/mũ bị loại; "đ" là ký tự độc lập (không phải combining) nên giữ
        assert normalize_title("Đánh giá mô hình") == "đanh gia mo hinh"

    def test_auto_derived_on_document(self):
        assert make_doc(title="Hello, World!").title_normalized == "hello world"


class TestDiscriminatedUnion:
    def test_imrad_roundtrip(self):
        doc = make_doc(
            sections=IMRADSections(
                introduction=Section(heading_raw="Introduction", content="ctx"),
                results=Section(heading_raw="Results", content="findings"),
            )
        )
        restored = Document.model_validate_json(doc.model_dump_json())
        assert isinstance(restored.sections, IMRADSections)
        canon = restored.canonical_sections
        assert canon[CanonicalRole.CONTEXT].content == "ctx"
        assert canon[CanonicalRole.FINDINGS].content == "findings"
        assert canon[CanonicalRole.METHOD] is None

    def test_paec_roundtrip(self):
        doc = make_doc(
            source="arxiv",
            source_id="arxiv:2401.00001",
            authority_tier=2,
            sections=PAECSections(
                problem=Section(content="p"),
                conclusion=Section(content="c"),
            ),
        )
        restored = Document.model_validate_json(doc.model_dump_json())
        assert isinstance(restored.sections, PAECSections)
        canon = restored.canonical_sections
        assert canon[CanonicalRole.CONTEXT].content == "p"
        assert canon[CanonicalRole.IMPLICATIONS].content == "c"

    def test_no_sections_gives_empty_canonical(self):
        canon = make_doc().canonical_sections
        assert set(canon) == set(CanonicalRole)
        assert all(v is None for v in canon.values())

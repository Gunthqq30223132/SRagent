import pytest

from sr_agent.errors import LayoutParseError, UnsupportedFormat
from sr_agent.ingest.arxiv import ArxivFetcher, normalize_arxiv_id
from sr_agent.ingest.ieee import IEEEXploreFetcher


class TestIEEEParse:
    def test_parse_fixture(self, ieee_search_json):
        docs = IEEEXploreFetcher(api_key="x").parse_search_json(ieee_search_json)
        assert [d.uid for d in docs] == ["ieee:38111222", "ieee:37000111"]
        first = docs[0]
        assert first.authority_tier == 1
        assert first.authors == ["Alice Nguyen", "Bob Tran"]
        assert first.published_date.year == 2025
        assert "github.com" in first.abstract

    def test_missing_articles_key_is_layout_error(self):
        with pytest.raises(LayoutParseError):
            IEEEXploreFetcher(api_key="x").parse_search_json({"foo": []})

    def test_missing_title_is_layout_error(self, ieee_search_json):
        ieee_search_json["articles"][0]["title"] = ""
        with pytest.raises(LayoutParseError):
            IEEEXploreFetcher(api_key="x").parse_search_json(ieee_search_json)

    def test_non_8_digit_id_skipped(self, ieee_search_json):
        ieee_search_json["articles"][0]["article_number"] = "123"  # lệch quy tắc tĩnh
        docs = IEEEXploreFetcher(api_key="x").parse_search_json(ieee_search_json)
        assert [d.uid for d in docs] == ["ieee:37000111"]

    def test_missing_api_key_raises_clear_error(self):
        with pytest.raises(UnsupportedFormat, match="IEEE_API_KEY"):
            IEEEXploreFetcher(api_key="").search("transformer")


class TestArxivParse:
    def test_parse_fixture(self, arxiv_atom_xml):
        docs = ArxivFetcher().parse_atom(arxiv_atom_xml)
        assert [d.uid for d in docs] == ["arxiv:2401.12345", "arxiv:2503.00042"]
        first = docs[0]
        assert first.authority_tier == 2
        # title gộp whitespace/xuống dòng
        assert first.title == (
            "Efficient Transformer Inference on Edge Devices: A Systematic Evaluation"
        )
        assert first.published_date.year == 2024

    def test_garbage_atom_is_layout_error(self):
        with pytest.raises(LayoutParseError):
            ArxivFetcher().parse_atom("<<<not atom at all")


class TestNormalizeArxivId:
    @pytest.mark.parametrize("raw", [
        "http://arxiv.org/abs/2401.12345v2",
        "arxiv:2401.12345",
        "arXiv:2401.12345v3",
        "2401.12345",
    ])
    def test_variants_normalize(self, raw):
        assert normalize_arxiv_id(raw) == "arxiv:2401.12345"

    def test_invalid_returns_none(self):
        assert normalize_arxiv_id("10.1109/TSE.2024.1234") is None

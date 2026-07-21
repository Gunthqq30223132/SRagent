import pytest

from sr_agent.errors import LayoutParseError
from sr_agent.ingest.europepmc import (
    EuropePMCFetcher,
    normalize_europepmc_id,
)


class TestEuropePMCParse:
    def test_parse_fixture_uids_and_order(self, europepmc_search_json):
        docs = EuropePMCFetcher().parse_search_json(europepmc_search_json)
        # AGR record bị bỏ; giữ đúng thứ tự 3 nguồn hợp lệ.
        assert [d.uid for d in docs] == [
            "europepmc:MED:38111222",
            "europepmc:PMC:9000111",
            "europepmc:PPR:456789",
        ]

    def test_med_record_fields(self, europepmc_search_json):
        med = EuropePMCFetcher().parse_search_json(europepmc_search_json)[0]
        assert med.authority_tier == 1
        assert med.authors == ["Nguyen A", "Tran B", "Le C"]
        assert med.published_date.year == 2025 and med.published_date.month == 3
        # whitespace/newline gộp; dấu chấm cuối title bị cắt.
        assert med.title == (
            "Dexmedetomidine versus propofol for procedural sedation: "
            "a randomized trial"
        )
        assert "dexmedetomidine and propofol" in med.abstract
        assert med.url == "https://europepmc.org/article/MED/38111222"

    def test_preprint_tier_downgraded(self, europepmc_search_json):
        ppr = EuropePMCFetcher().parse_search_json(europepmc_search_json)[2]
        # PPR là preprint -> tier 2 dù mặc định nguồn là 1.
        assert ppr.authority_tier == 2

    def test_pmc_falls_back_to_pubyear_date(self, europepmc_search_json):
        pmc = EuropePMCFetcher().parse_search_json(europepmc_search_json)[1]
        assert pmc.published_date.year == 2024
        assert pmc.authors == ["Pham D", "Vo E"]

    def test_missing_resultlist_is_layout_error(self):
        with pytest.raises(LayoutParseError):
            EuropePMCFetcher().parse_search_json({"foo": []})

    def test_result_not_list_is_layout_error(self):
        with pytest.raises(LayoutParseError):
            EuropePMCFetcher().parse_search_json({"resultList": {"result": "nope"}})

    def test_missing_title_is_layout_error(self, europepmc_search_json):
        europepmc_search_json["resultList"]["result"][0]["title"] = "  "
        with pytest.raises(LayoutParseError):
            EuropePMCFetcher().parse_search_json(europepmc_search_json)

    def test_non_numeric_id_skipped(self, europepmc_search_json):
        europepmc_search_json["resultList"]["result"][0]["id"] = "MED-xx"
        docs = EuropePMCFetcher().parse_search_json(europepmc_search_json)
        assert [d.uid for d in docs] == [
            "europepmc:PMC:9000111",
            "europepmc:PPR:456789",
        ]


class TestNormalizeEuropePMCId:
    @pytest.mark.parametrize("raw,expected", [
        ("europepmc:MED:38111222", "europepmc:MED:38111222"),
        ("MED/38111222", "europepmc:MED:38111222"),
        ("med/38111222", "europepmc:MED:38111222"),
        ("PMC9000111", "europepmc:PMC:9000111"),
        ("PPR456789", "europepmc:PPR:456789"),
    ])
    def test_valid_variants(self, raw, expected):
        assert normalize_europepmc_id(raw) == expected

    @pytest.mark.parametrize("raw", [
        "38111222",       # số trần — nhập nhằng với IEEE, phải từ chối
        "arxiv:2401.12345",
        "MED/abc",
        "XYZ/123",
        "doi:10.1/x",
    ])
    def test_rejects_ambiguous_or_foreign(self, raw):
        assert normalize_europepmc_id(raw) is None

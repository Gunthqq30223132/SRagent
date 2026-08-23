"""Test nguồn PubMed — parse XML efetch, chuẩn hóa ID, bậc chứng cứ, routing.

XML fixture dựng theo ĐÚNG cấu trúc efetch thật của NCBI (PubmedArticleSet >
PubmedArticle > MedlineCitation > Article), dùng PMID có thật để nếu chạy live
trên máy có mạng thì đối chiếu được ngay.
"""

from __future__ import annotations

import httpx
import pytest

from sr_agent.errors import LayoutParseError, UnsupportedFormat
from sr_agent.models.schemas import DocStatus
from tools.sources.medical_router import MedicalSourceRouter
from tools.sources.pubmed import (
    PubMedFetcher,
    evidence_level,
    normalize_pubmed_id,
)

EFETCH_XML = """<?xml version="1.0" ?>
<PubmedArticleSet>
 <PubmedArticle>
  <MedlineCitation Status="MEDLINE">
   <PMID Version="1">42247721</PMID>
   <Article PubModel="Print-Electronic">
    <Journal>
     <JournalIssue><PubDate><Year>2026</Year><Month>Feb</Month><Day>11</Day></PubDate></JournalIssue>
     <Title>Thrombosis Research</Title>
    </Journal>
    <ArticleTitle>Comparing perioperative heparin bridging strategies in mechanical
     heart valve patients undergoing surgery: A systematic review and Bayesian
     meta-analysis.</ArticleTitle>
    <Abstract>
     <AbstractText Label="BACKGROUND">Bridging remains controversial.</AbstractText>
     <AbstractText Label="RESULTS">Four studies with 1847 patients were included.</AbstractText>
    </Abstract>
    <AuthorList>
     <Author><LastName>Nguyen</LastName><ForeName>Minh</ForeName></Author>
     <Author><CollectiveName>ISTH Working Group</CollectiveName></Author>
    </AuthorList>
    <PublicationTypeList>
     <PublicationType UI="D016428">Journal Article</PublicationType>
     <PublicationType UI="D017418">Meta-Analysis</PublicationType>
     <PublicationType UI="D000078182">Systematic Review</PublicationType>
    </PublicationTypeList>
   </Article>
  </MedlineCitation>
 </PubmedArticle>
 <PubmedArticle>
  <MedlineCitation Status="MEDLINE">
   <PMID Version="1">41073233</PMID>
   <Article PubModel="Print">
    <Journal>
     <JournalIssue><PubDate><MedlineDate>2025 Oct-Nov</MedlineDate></PubDate></JournalIssue>
     <Title>British Journal of Anaesthesia</Title>
    </Journal>
    <ArticleTitle>Direct oral anticoagulant management for neuraxial anaesthesia
     and deep peripheral nerve blocks.</ArticleTitle>
    <Abstract><AbstractText>DOACs increase bleeding risk with neuraxial blocks.</AbstractText></Abstract>
    <AuthorList><Author><LastName>Douketis</LastName><ForeName>James</ForeName></Author></AuthorList>
    <PublicationTypeList>
     <PublicationType UI="D016454">Review</PublicationType>
    </PublicationTypeList>
   </Article>
  </MedlineCitation>
 </PubmedArticle>
</PubmedArticleSet>
"""


class TestNormalizePubMedId:
    @pytest.mark.parametrize("raw,expected", [
        ("pubmed:41073233", "pubmed:41073233"),
        ("pmid:41073233", "pubmed:41073233"),
        ("PMID: 41073233", "pubmed:41073233"),
        ("https://pubmed.ncbi.nlm.nih.gov/41073233/", "pubmed:41073233"),
    ])
    def test_accepts_known_variants(self, raw, expected):
        assert normalize_pubmed_id(raw) == expected

    @pytest.mark.parametrize("raw", ["arxiv:2401.12345", "pubmed:abc", "pubmed:"])
    def test_rejects_non_pubmed(self, raw):
        assert normalize_pubmed_id(raw) is None

    def test_rejects_overlong_id_instead_of_truncating(self):
        # 9 chữ số vượt quy tắc: phải TỪ CHỐI, không được cắt bớt cho vừa.
        assert normalize_pubmed_id("pubmed:123456789") is None


class TestParseEfetchXml:
    @pytest.fixture
    def docs(self):
        return PubMedFetcher(client=httpx.Client()).parse_efetch_xml(EFETCH_XML)

    def test_parses_both_records(self, docs):
        assert len(docs) == 2
        assert [d.source_id for d in docs] == ["pubmed:42247721", "pubmed:41073233"]

    def test_uid_has_no_double_prefix(self, docs):
        assert docs[0].uid == "pubmed:42247721"

    def test_title_whitespace_collapsed_across_lines(self, docs):
        assert "systematic review and Bayesian meta-analysis" in docs[0].title
        assert "\n" not in docs[0].title

    def test_abstract_keeps_section_labels(self, docs):
        assert docs[0].abstract.startswith("BACKGROUND: Bridging remains")
        assert "RESULTS: Four studies with 1847 patients" in docs[0].abstract

    def test_collective_author_not_dropped(self, docs):
        assert docs[0].authors == ["Minh Nguyen", "ISTH Working Group"]

    def test_structured_pubdate(self, docs):
        assert (docs[0].published_date.year, docs[0].published_date.month) == (2026, 2)

    def test_medline_date_falls_back_to_year(self, docs):
        assert docs[1].published_date.year == 2025

    def test_authority_tier_is_peer_reviewed(self, docs):
        assert docs[0].authority_tier == 1

    def test_status_is_fetched(self, docs):
        assert all(d.status is DocStatus.FETCHED for d in docs)

    def test_url_points_at_real_record(self, docs):
        assert docs[1].url == "https://pubmed.ncbi.nlm.nih.gov/41073233/"

    def test_broken_xml_raises_instead_of_returning_empty(self):
        with pytest.raises(LayoutParseError):
            PubMedFetcher(client=httpx.Client()).parse_efetch_xml("<PubmedArticleSet")

    def test_missing_article_node_raises(self):
        bad = ('<PubmedArticleSet><PubmedArticle><MedlineCitation>'
               '<PMID>1</PMID></MedlineCitation></PubmedArticle></PubmedArticleSet>')
        with pytest.raises(LayoutParseError):
            PubMedFetcher(client=httpx.Client()).parse_efetch_xml(bad)


class TestEvidenceLevel:
    def test_strongest_type_wins(self):
        # Bài mang cả 3 nhãn -> phải lấy meta-analysis (mạnh nhất), không lấy
        # 'Journal Article' chỉ vì nó đứng đầu danh sách.
        assert evidence_level(
            ["Journal Article", "Meta-Analysis", "Systematic Review"]
        ) == 1

    def test_review_is_weaker_than_systematic_review(self):
        assert evidence_level(["Review"]) > evidence_level(["Systematic Review"])

    def test_unknown_type_is_none_not_worst_rank(self):
        # None = 'chưa phân loại', KHÁC với 'đã phân loại là yếu'. Trả về một
        # con số lớn ở đây sẽ khiến tầng trên tưởng đã đánh giá rồi.
        assert evidence_level(["Letter"]) is None

    def test_map_is_populated_after_parse(self):
        f = PubMedFetcher(client=httpx.Client())
        f.parse_efetch_xml(EFETCH_XML)
        assert f.evidence_levels["pubmed:42247721"] == 1
        assert f.evidence_levels["pubmed:41073233"] == 7


class TestMedicalSourceRouter:
    @pytest.fixture
    def router(self):
        return MedicalSourceRouter()

    def test_routes_pubmed(self, router):
        assert router.classify("pmid:41073233") == ("pubmed", "pubmed:41073233")

    def test_still_routes_arxiv(self, router):
        assert router.classify("arxiv:2401.12345") == ("arxiv", "arxiv:2401.12345")

    def test_still_routes_ieee(self, router):
        assert router.classify("10787654") == ("ieee", "10787654")

    def test_eight_digit_id_is_ieee_not_pmid(self, router):
        # Ranh giới quan trọng: PMID cũng có thể 8 số. Không có tiền tố thì
        # PHẢI về IEEE như cũ — nguồn mới không được cướp ID của nguồn cũ.
        assert router.classify("42247721")[0] == "ieee"

    def test_malformed_pubmed_id_raises_not_silently_falls_through(self, router):
        with pytest.raises(UnsupportedFormat):
            router.classify("pmid:khong-phai-so")

    def test_fetcher_registered(self, router):
        assert router.fetcher_for("pubmed").source == "pubmed"

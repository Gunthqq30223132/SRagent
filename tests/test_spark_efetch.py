"""Test đường 'Spark tải hộ bản gốc' — hạng uy tín thấp hơn, và đo được.

Câu hỏi thiết kế: có nên cho Spark tải bản gốc không?
Câu trả lời của bộ test này: có, NHƯNG bản ghi phải mang nguồn riêng hạng thấp,
phải khớp với chính phiếu Spark đã khai, và phải đối chiếu được với bản chính
thống khi mạng thông. Tranh cãi "có tin được không" không giải bằng lý lẽ —
giải bằng phép đo.
"""

from __future__ import annotations

import pytest

from sr_agent.errors import LayoutParseError
from sr_agent.models.schemas import Document, default_tier
from tools.sources.pubmed import PubMedFetcher
from tools.sources.spark_efetch import (
    SparkEfetchReader,
    doi_chieu_voi_phieu,
    kiem_toan_ven_xml,
    raise_neu_rong,
    so_khop_ban_chinh_thong,
)

XML = """<?xml version="1.0"?>
<PubmedArticleSet>
 <PubmedArticle><MedlineCitation>
  <PMID Version="1">26095867</PMID>
  <Article>
   <Journal><JournalIssue><PubDate><Year>2015</Year><Month>Aug</Month></PubDate></JournalIssue>
    <Title>N Engl J Med</Title></Journal>
   <ArticleTitle>Perioperative Bridging Anticoagulation in Patients with Atrial Fibrillation.</ArticleTitle>
   <Abstract><AbstractText>Forgoing bridging was noninferior.</AbstractText></Abstract>
   <AuthorList><Author><LastName>Douketis</LastName><ForeName>James</ForeName></Author></AuthorList>
   <PublicationTypeList><PublicationType>Randomized Controlled Trial</PublicationType></PublicationTypeList>
  </Article>
 </MedlineCitation></PubmedArticle>
</PubmedArticleSet>"""


def doc_xml(xml: str = XML):
    return SparkEfetchReader().parse_efetch_xml(xml)


class TestNguonRiengHangThap:
    """Không chứng minh được XML đến từ NCBI ⇒ không được hưởng uy tín ngang bản tự tải."""

    def test_nguon_khac_pubmed_truc_tiep(self):
        assert doc_xml()[0].source == "pubmed-qua-spark"

    def test_hang_uy_tin_thap_hon_ban_tu_tai(self):
        assert default_tier("pubmed-qua-spark") > default_tier("pubmed")

    def test_van_cao_hon_nguon_hoan_toan_chua_dang_ky(self):
        assert default_tier("pubmed-qua-spark") < default_tier("mot-nguon-la-hoac")

    def test_uid_noi_ro_duong_di(self):
        """Nhìn uid là biết bản ghi này đến bằng đường nào — không phải tra sổ."""
        assert doc_xml()[0].uid.startswith("pubmed-qua-spark:")


class TestDungLaiBoPhanTichCuaTa:
    """Spark chỉ vận chuyển byte. Phân tích vẫn là việc của SR-Agent."""

    def test_cung_bo_phan_tich_voi_pubmed_that(self):
        qua_spark = doc_xml()[0]
        truc_tiep = PubMedFetcher().parse_efetch_xml(XML)[0]
        assert qua_spark.title == truc_tiep.title
        assert qua_spark.abstract == truc_tiep.abstract
        assert qua_spark.evidence_level == truc_tiep.evidence_level

    def test_bac_chung_cu_van_duoc_trich(self):
        assert doc_xml()[0].evidence_level == 3  # Randomized Controlled Trial


class TestKhopVoiPhieu:
    """Spark khai một đằng ở phiếu, nộp một nẻo ở XML — không cần tin, chỉ cần so."""

    def test_khop_thi_khong_van_de(self):
        assert doi_chieu_voi_phieu(doc_xml(), ["pubmed:26095867"]) == []

    def test_khai_ma_khong_nop_ban_goc(self):
        van_de = doi_chieu_voi_phieu(doc_xml(), ["pubmed:26095867", "pubmed:99999999"])
        assert len(van_de) == 1 and "KHÔNG có trong XML" in van_de[0]

    def test_nop_ban_goc_ma_khong_khai(self):
        """Bản ghi lọt vào kho mà không qua bước sàng lọc nào."""
        van_de = doi_chieu_voi_phieu(doc_xml(), [])
        assert len(van_de) == 1 and "KHÔNG khai trong phiếu" in van_de[0]


class TestToanVenBanGhi:
    def test_ban_ghi_du_thi_sach(self):
        assert kiem_toan_ven_xml(doc_xml()) == []

    def test_thieu_tom_tat_bi_neu(self):
        d = Document(uid="", source="pubmed-qua-spark", source_id="pubmed-qua-spark:1",
                     authority_tier=3, title="Bài", authors=["A B"], abstract=None)
        assert "tóm tắt" in kiem_toan_ven_xml([d])[0]

    def test_xml_rong_la_loi_khong_phai_ket_qua_rong(self):
        with pytest.raises(LayoutParseError, match="không chứa bản ghi nào"):
            raise_neu_rong([], "spark_efetch.xml")


class TestDoiChieuVoiBanChinhThong:
    """Mục đích thật của cả thiết kế: biến câu hỏi tin-hay-không thành phép đo."""

    @pytest.fixture
    def goc(self):
        return PubMedFetcher().parse_efetch_xml(XML)

    def test_giong_het_thi_khong_lech(self, goc):
        assert so_khop_ban_chinh_thong(doc_xml(), goc) == {}

    def test_bat_tieu_de_bi_sua(self, goc):
        sua = XML.replace("Atrial Fibrillation", "Ventricular Fibrillation")
        lech = so_khop_ban_chinh_thong(doc_xml(sua), goc)
        assert "tiêu đề lệch" in lech["26095867"][0]

    def test_bat_tom_tat_bi_sua(self, goc):
        sua = XML.replace("noninferior", "superior")
        assert "tóm tắt lệch" in so_khop_ban_chinh_thong(doc_xml(sua), goc)["26095867"][0]

    def test_bat_bac_chung_cu_bi_nang_khong(self, goc):
        """Nâng nhãn thiết kế nghiên cứu là cách bóp méo nguy hiểm nhất."""
        sua = XML.replace("Randomized Controlled Trial", "Meta-Analysis")
        assert "bậc chứng cứ lệch" in so_khop_ban_chinh_thong(doc_xml(sua), goc)["26095867"][0]

    def test_bat_ma_bia_hoan_toan(self, goc):
        sua = XML.replace("26095867", "99999999")
        assert "mã bịa" in so_khop_ban_chinh_thong(doc_xml(sua), goc)["99999999"][0]

    def test_bat_ngay_bi_sua(self, goc):
        sua = XML.replace("<Year>2015</Year>", "<Year>2021</Year>")
        assert "ngày lệch" in so_khop_ban_chinh_thong(doc_xml(sua), goc)["26095867"][0]

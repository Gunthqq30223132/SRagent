"""Test bộ đọc MEDLINE — đường vòng khi eutils bị chặn.

Mỗi test ở đây gắn với một chế độ hỏng CỤ THỂ, không phải giả định:
  - Mất thụt lề  : xảy ra thật khi dán văn bản qua Google Doc (đã đo ở vòng arXiv)
  - Trả về HTML  : xảy ra khi quên đuôi '?format=pubmed'
  - Tóm tắt cụt  : hệ quả im lặng của mất thụt lề, phải kêu riêng
"""

from __future__ import annotations

import pytest

from sr_agent.errors import LayoutParseError
from sr_agent.models.schemas import default_tier
from tools.sources.medline import canh_bao_tom_tat_cut, parse_medline
from tools.sources.spark_efetch import doi_chieu_voi_phieu

# Dựng theo đúng hình dạng PubMed trả về: nhãn 4 ký tự, nối tiếp thụt 6 dấu cách.
BRIDGE = """PMID- 26095867
OWN - NLM
STAT- MEDLINE
DP  - 2015 Aug 27
TI  - Perioperative Bridging Anticoagulation in Patients with Atrial
      Fibrillation.
AB  - BACKGROUND: It is uncertain whether bridging anticoagulation is necessary
      for patients with atrial fibrillation who need an interruption in warfarin
      treatment. CONCLUSIONS: Forgoing bridging anticoagulation was noninferior
      to perioperative bridging with low-molecular-weight heparin.
FAU - Douketis, James D
AU  - Douketis JD
FAU - Spyropoulos, Alex C
AU  - Spyropoulos AC
PT  - Journal Article
PT  - Randomized Controlled Trial
TA  - N Engl J Med
"""

PERIOP2 = """PMID- 34108229
OWN - NLM
DP  - 2021 Jun 9
TI  - Postoperative low molecular weight heparin bridging treatment (PERIOP2).
AB  - OBJECTIVE: To determine the efficacy and safety of dalteparin bridging.
FAU - Kovacs, Michael J
PT  - Randomized Controlled Trial
"""


class TestDocDungBanGhiThat:
    def test_noi_dong_tiep_cua_tieu_de(self):
        """Tiêu đề trải hai dòng phải ghép lại, không đứt ở giữa."""
        d = parse_medline(BRIDGE)[0]
        assert d.title == (
            "Perioperative Bridging Anticoagulation in Patients with "
            "Atrial Fibrillation."
        )

    def test_noi_dong_tiep_cua_tom_tat(self):
        d = parse_medline(BRIDGE)[0]
        assert d.abstract.startswith("BACKGROUND: It is uncertain")
        assert d.abstract.endswith("low-molecular-weight heparin.")
        assert "noninferior" in d.abstract

    def test_uu_tien_ten_day_du(self):
        """FAU ('Douketis, James D') giàu thông tin hơn AU ('Douketis JD')."""
        assert parse_medline(BRIDGE)[0].authors == [
            "Douketis, James D", "Spyropoulos, Alex C",
        ]

    def test_trich_duoc_bac_chung_cu(self):
        assert parse_medline(BRIDGE)[0].evidence_level == 3  # RCT

    def test_doc_duoc_ngay(self):
        d = parse_medline(BRIDGE)[0]
        assert (d.published_date.year, d.published_date.month) == (2015, 8)

    def test_tach_dung_nhieu_ban_ghi(self):
        docs = parse_medline(BRIDGE + "\n" + PERIOP2)
        assert [d.source_id.rsplit(":", 1)[-1] for d in docs] == [
            "26095867", "34108229",
        ]


class TestVanLaHangUyTinThap:
    """Đổi định dạng KHÔNG đổi mức tin cậy — câu hỏi là về người chuyển thư."""

    def test_cung_nguon_voi_duong_efetch(self):
        assert parse_medline(BRIDGE)[0].source == "pubmed-qua-spark"

    def test_thap_hon_ban_tu_tai(self):
        assert default_tier("pubmed-qua-spark") > default_tier("pubmed")

    def test_doi_chieu_duoc_voi_phieu(self):
        """Bản ghi đường này phải khớp cơ chế đối chiếu sẵn có, không cần mã riêng."""
        assert doi_chieu_voi_phieu(parse_medline(BRIDGE), ["pubmed:26095867"]) == []


class TestHongThiKeuTo:
    def test_rong(self):
        with pytest.raises(LayoutParseError, match="rỗng"):
            parse_medline("   \n  ")

    def test_tra_ve_html_vi_quen_duoi_format(self):
        html = "<!DOCTYPE html><html><head><title>PubMed</title></head></html>"
        with pytest.raises(LayoutParseError, match="format=pubmed"):
            parse_medline(html)

    def test_mat_thut_le_bi_bat(self):
        """Chế độ hỏng NGUY HIỂM NHẤT: đọc vẫn ra, nhưng tóm tắt cụt mất một nửa."""
        hong = BRIDGE.replace("      Fibrillation.", "Fibrillation.")
        with pytest.raises(LayoutParseError, match="canh lề lại"):
            parse_medline(hong)

    def test_khong_co_nhan_pmid_nao(self):
        with pytest.raises(LayoutParseError, match="không phải định dạng MEDLINE"):
            parse_medline("TI  - Một bài không mã\nAB  - Nội dung\n")

    def test_mot_ban_ghi_giua_chung_mat_pmid(self):
        """Tình huống thật hơn: tệp đúng định dạng nhưng MỘT bản ghi bị cụt đầu.

        Chốt toàn tệp không bắt được ca này vì các bản ghi khác vẫn có 'PMID-'.
        Nếu chỉ có chốt toàn tệp, bản ghi vô danh sẽ lọt vào kho.
        """
        with pytest.raises(LayoutParseError, match=r"#2 không có PMID"):
            parse_medline(BRIDGE + "\nTI  - Bài mất mã\nAB  - Nội dung\n")

    def test_pmid_khong_phai_so(self):
        with pytest.raises(LayoutParseError, match="không phải số"):
            parse_medline(BRIDGE.replace("PMID- 26095867", "PMID- abc123"))


class TestCanhBaoTomTatCut:
    def test_ban_ghi_du_thi_im_lang(self):
        assert canh_bao_tom_tat_cut(parse_medline(BRIDGE)) == []

    def test_tom_tat_ngan_bi_neu(self):
        canh = canh_bao_tom_tat_cut(parse_medline(PERIOP2))
        assert len(canh) == 1 and "kiểm xem có bị cắt không" in canh[0]

    def test_khong_co_tom_tat_bi_neu(self):
        khong = "\n".join(
            d for d in PERIOP2.splitlines() if not d.startswith("AB  -")
        )
        assert "KHÔNG có tóm tắt" in canh_bao_tom_tat_cut(parse_medline(khong))[0]

    def test_canh_bao_khong_tu_y_loai_bo(self):
        """Cảnh báo là để người xem. Bài tóm tắt ngắn thật vẫn phải được giữ."""
        docs = parse_medline(PERIOP2)
        assert canh_bao_tom_tat_cut(docs) and len(docs) == 1

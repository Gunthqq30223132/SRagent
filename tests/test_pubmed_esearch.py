"""Test bước tìm kiếm PubMed — hồi quy trực tiếp cho lỗi lần chạy thật đầu tiên.

Lần chạy đầu trên MacBook (2026-08-23) báo:
    LayoutParseError: esearch trả JSON không đúng dạng:
    Expecting value: line 1 column 1 (char 0)

Nghĩa là HTTP THÀNH CÔNG nhưng thân phản hồi không phải JSON. Hai bài học đã
chuyển thành test ở đây:
  1. Dùng XML (định dạng mặc định, ổn định) thay vì retmode=json.
  2. Mọi đường lỗi PHẢI kèm nội dung thật nhận được — thông điệp giấu thân
     phản hồi làm mất trọn một vòng thử.
"""

from __future__ import annotations

import pytest

from sr_agent.errors import LayoutParseError
from tools.sources.pubmed import PubMedFetcher

ESEARCH_OK = """<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
  <Count>4211</Count><RetMax>3</RetMax><RetStart>0</RetStart>
  <IdList>
    <Id>42247721</Id><Id>41073233</Id><Id>26095867</Id>
  </IdList>
</eSearchResult>"""


class TestParseEsearchOk:
    def test_lay_dung_danh_sach_pmid(self):
        assert PubMedFetcher.parse_esearch_xml(ESEARCH_OK) == [
            "pubmed:42247721", "pubmed:41073233", "pubmed:26095867",
        ]

    def test_khong_co_ket_qua_thi_tra_rong_khong_ngoai_le(self):
        rong = "<eSearchResult><Count>0</Count><IdList/></eSearchResult>"
        assert PubMedFetcher.parse_esearch_xml(rong) == []


class TestParseEsearchLoi:
    def test_than_rong_bao_loi_khong_tra_rong(self):
        """0 byte KHÁC 'không có bài nào khớp'. Gộp hai thứ là bỏ sót thầm lặng."""
        with pytest.raises(LayoutParseError, match="THÂN RỖNG"):
            PubMedFetcher.parse_esearch_xml("   ")

    def test_trang_html_chan_bi_bat(self):
        """'<html><body>Access denied</body></html>' TÌNH CỜ là XML hợp lệ.

        Không kiểm thẻ gốc thì nó lọt qua và trả danh sách rỗng — người dùng
        đọc thành 'không có bài nào' thay vì 'bị chặn'.
        """
        with pytest.raises(LayoutParseError, match="thẻ gốc"):
            PubMedFetcher.parse_esearch_xml(
                "<html><body>Access denied by proxy</body></html>")

    def test_json_lot_vao_cung_bi_bat(self):
        with pytest.raises(LayoutParseError, match="không phải XML"):
            PubMedFetcher.parse_esearch_xml('{"esearchresult": {"idlist": []}}')

    def test_ncbi_bao_loi_truy_van_duoc_neu_ro(self):
        with pytest.raises(LayoutParseError, match="Invalid db name"):
            PubMedFetcher.parse_esearch_xml(
                "<eSearchResult><ERROR>Invalid db name</ERROR></eSearchResult>")

    @pytest.mark.parametrize("xau", [
        "<html><body>x</body></html>",
        '{"a":1}',
        "khong phai gi ca",
    ])
    def test_moi_thong_diep_loi_deu_kem_noi_dung_that(self, xau):
        """Ràng buộc quan trọng nhất: đừng bao giờ giấu thứ máy chủ trả về."""
        with pytest.raises(LayoutParseError) as e:
            PubMedFetcher.parse_esearch_xml(xau)
        assert xau[:20] in str(e.value), str(e.value)


class TestKhongDungRetmodeJson:
    def test_client_mac_dinh_co_user_agent(self):
        """NCBI có thể chặn mềm lưu lượng ẩn danh bằng HTTP 200 + trang chặn."""
        f = PubMedFetcher()
        assert "sr-agent" in f.client.headers.get("user-agent", "")

    def test_tham_so_tim_kiem_khong_yeu_cau_json(self):
        f = PubMedFetcher()
        assert "retmode" not in f._common_params()

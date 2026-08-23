"""Test nguồn Europe PMC — nguồn đầu tiên SR-Agent tự với tới được.

Bản ghi mẫu dựng theo ĐÚNG hình dạng phản hồi thật, lấy từ lần chạy kiểm chứng
trên máy Gun ngày 2026-08-23 (bài BRIDGE, PMID 26095867): các trường id/source/
pmid/pmcid/doi/title đều là giá trị thật đã nhìn thấy tận mắt, không phải bịa
cho vừa test.
"""

from __future__ import annotations

import json

import httpx
import pytest

from sr_agent.config import UNKNOWN_SOURCE_TIER
from sr_agent.errors import LayoutParseError
from tools.sources.europepmc import (
    EuropePMCFetcher,
    ban_ghi_thanh_document,
    hang_uy_tin,
)

BRIDGE = {
    "id": "26095867", "source": "MED", "pmid": "26095867",
    "pmcid": "PMC4931686", "doi": "10.1056/nejmoa1501035",
    "title": "Perioperative Bridging Anticoagulation in Patients with Atrial Fibrillation.",
    "abstractText": "BACKGROUND: It is uncertain whether bridging is necessary.",
    "authorList": {"author": [
        {"fullName": "Douketis JD"}, {"fullName": "Spyropoulos AC"},
    ]},
    "authorString": "Douketis JD, Spyropoulos AC.",
    "pubYear": "2015", "firstPublicationDate": "2015-06-22",
    "pubTypeList": {"pubType": ["Journal Article", "Randomized Controlled Trial"]},
    "isOpenAccess": "N",
}

TIEN_AN_PHAM = {
    "id": "PPR123456", "source": "PPR", "doi": "10.1101/2025.01.01.000000",
    "title": "Một nghiên cứu chưa qua bình duyệt.",
    "abstractText": "Kết quả sơ bộ.", "pubYear": "2025",
    "pubTypeList": {"pubType": ["Preprint"]},
}


def khach(trang: list[dict]) -> httpx.Client:
    """Client giả trả về từng trang một, mô phỏng phân trang bằng cursorMark."""
    con_lai = list(trang)

    def xu_ly(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=con_lai.pop(0) if con_lai else
                              {"hitCount": 0, "resultList": {"result": []}})

    return httpx.Client(transport=httpx.MockTransport(xu_ly))


def trang(recs: list[dict], tong: int, cursor_sau: str = "") -> dict:
    d = {"hitCount": tong, "resultList": {"result": recs}}
    if cursor_sau:
        d["nextCursorMark"] = cursor_sau
    return d


class TestDocBanGhiThat:
    def test_tieu_de_va_tom_tat(self):
        d = ban_ghi_thanh_document(BRIDGE)
        assert d.title.startswith("Perioperative Bridging Anticoagulation")
        assert "uncertain" in d.abstract

    def test_tac_gia_lay_tu_danh_sach_co_cau_truc(self):
        assert ban_ghi_thanh_document(BRIDGE).authors == [
            "Douketis JD", "Spyropoulos AC",
        ]

    def test_du_phong_khi_chi_co_chuoi_gop(self):
        rec = {k: v for k, v in BRIDGE.items() if k != "authorList"}
        assert ban_ghi_thanh_document(rec).authors == [
            "Douketis JD", "Spyropoulos AC",
        ]

    def test_bac_chung_cu_tu_loai_bai(self):
        assert ban_ghi_thanh_document(BRIDGE).evidence_level == 3  # RCT

    def test_ngay_uu_tien_ngay_xuat_ban_dau(self):
        d = ban_ghi_thanh_document(BRIDGE)
        assert (d.published_date.year, d.published_date.month) == (2015, 6)

    def test_chi_co_nam_van_dung_duoc(self):
        rec = {k: v for k, v in BRIDGE.items() if k != "firstPublicationDate"}
        assert ban_ghi_thanh_document(rec).published_date.year == 2015


class TestHangUyTinTheoKhoCon:
    """Bài đã bình duyệt và bản tiền ấn phẩm KHÔNG được cùng hạng."""

    def test_medline_hang_cao_nhat(self):
        assert ban_ghi_thanh_document(BRIDGE).authority_tier == 1

    def test_tien_an_pham_hang_thap_hon(self):
        assert ban_ghi_thanh_document(TIEN_AN_PHAM).authority_tier == 2

    def test_kho_la_xuong_hang_chua_tham_dinh(self):
        assert hang_uy_tin("XYZ") == UNKNOWN_SOURCE_TIER

    def test_khong_gan_phang_mot_hang_cho_ca_nguon(self):
        med = ban_ghi_thanh_document(BRIDGE).authority_tier
        ppr = ban_ghi_thanh_document(TIEN_AN_PHAM).authority_tier
        assert med < ppr


class TestGiuVetDinhDanhKhac:
    """Không giữ vết thì D34 đếm bản EuroPMC và bản PubMed thành HAI bài."""

    def test_giu_pmid_pmcid_doi(self):
        assert set(ban_ghi_thanh_document(BRIDGE).alternate_uids) == {
            "pubmed:26095867", "pmc:PMC4931686", "doi:10.1056/nejmoa1501035",
        }

    def test_thieu_dinh_danh_phu_van_doc_duoc(self):
        assert ban_ghi_thanh_document(TIEN_AN_PHAM).alternate_uids == [
            "doi:10.1101/2025.01.01.000000",
        ]


class TestQuetToanBo:
    """Đây là hàm biến 'độ phủ 0,57%' thành chuyện của đường truyền, không phải giới hạn."""

    def test_tra_ve_ca_ban_ghi_lan_tong_kho(self):
        f = EuropePMCFetcher(client=khach([trang([BRIDGE], 1)]))
        docs, tong = f.quet_toan_bo("test")
        assert len(docs) == 1 and tong == 1

    def test_di_het_nhieu_trang(self):
        f = EuropePMCFetcher(client=khach([
            trang([BRIDGE], 2, cursor_sau="AoJ2"),
            trang([TIEN_AN_PHAM], 2, cursor_sau="AoJ3"),
        ]))
        docs, tong = f.quet_toan_bo("test", page_size=1)
        assert len(docs) == 2 and tong == 2

    def test_cursor_khong_doi_thi_dung_khong_lap_vo_han(self):
        """Nếu API đổi hành vi mà không kiểm điều này, vòng lặp chạy mãi."""
        lap = trang([BRIDGE], 99, cursor_sau="*")   # cursor trỏ về chính nó
        f = EuropePMCFetcher(client=khach([lap, lap, lap]))
        docs, _ = f.quet_toan_bo("test")
        assert len(docs) == 1

    def test_ton_trong_tran_an_toan(self):
        f = EuropePMCFetcher(client=khach([
            trang([BRIDGE, TIEN_AN_PHAM], 9999, cursor_sau="AoJ2"),
            trang([BRIDGE], 9999, cursor_sau="AoJ3"),
        ]))
        docs, _ = f.quet_toan_bo("test", tran=2)
        assert len(docs) == 2

    def test_kho_rong_khong_phai_loi(self):
        f = EuropePMCFetcher(client=khach([trang([], 0)]))
        docs, tong = f.quet_toan_bo("truy vấn không ra gì")
        assert docs == [] and tong == 0


class TestHongThiKeuTo:
    def test_khong_phai_json(self):
        c = httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, text="<html>chan dang nhap</html>")))
        with pytest.raises(LayoutParseError, match="không phải JSON"):
            EuropePMCFetcher(client=c).quet_toan_bo("test")

    def test_json_thieu_result_list(self):
        c = httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"hitCount": 5})))
        with pytest.raises(LayoutParseError, match="thiếu 'resultList'"):
            EuropePMCFetcher(client=c).quet_toan_bo("test")

    def test_ban_ghi_thieu_dinh_danh(self):
        with pytest.raises(LayoutParseError, match="thiếu 'source' hoặc 'id'"):
            ban_ghi_thanh_document({"title": "Bài không mã"})


class TestFetchTheoMa:
    def test_nhan_ma_kieu_pubmed(self):
        """Phiếu Spark ghi 'pubmed:123'. Không nhận được thì phải sửa phiếu — sai chiều."""
        f = EuropePMCFetcher(client=khach([trang([BRIDGE], 1)]))
        assert len(f.fetch(["pubmed:26095867"])) == 1

    def test_danh_sach_rong_khong_goi_mang(self):
        f = EuropePMCFetcher(client=httpx.Client(transport=httpx.MockTransport(
            lambda r: pytest.fail("không được gọi mạng khi danh sách rỗng"))))
        assert f.fetch([]) == []

    def test_search_tra_ve_ma_nguon(self):
        f = EuropePMCFetcher(client=khach([trang([BRIDGE], 1)]))
        assert f.search("test", max_results=5) == ["europepmc:MED:26095867"]

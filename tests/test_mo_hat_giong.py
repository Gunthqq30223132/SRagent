"""Test bộ sinh hạt giống không tốn thời gian chuyên gia.

Ranh giới quan trọng nhất bộ test này giữ:

  ỨNG VIÊN  != HẠT GIỐNG DÙNG ĐƯỢC

Một chuỗi trích dẫn trong manifest là LỜI KHAI. Đem lời khai chưa xác minh đi đo
độ nhạy thì mọi truy vấn đều 'sót' nó — và ta sẽ đi sửa truy vấn trong khi bài đó
có thể chưa từng tồn tại. Đó là báo động giả tệ nhất có thể có ở khâu này.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from tools.mo_hat_giong import (
    BacNguon,
    HatGiong,
    bao_cao,
    mo_tu_provenance,
    tach_chu_de_con,
    tach_trich_dan,
)

MANIFEST = {
    "files": {
        "sepsis_rules.json": {
            "synthetic": True,
            "citation": "Surviving Sepsis Campaign 2026 — Critical Care Medicine "
                        "April 2026 (DOI 10.1097/CCM.0000000000007075); "
                        "ADA Standards of Care 2026; ILCOR 2020",
        },
        "sugammadex_rules_vi.json": {
            "synthetic": True,
            "citation": "NAP4 Major Complications of Airway Management "
                        "(RCoA/AAGBI 2011); DAS 2015 Guidelines",
        },
        "khong_trich_dan.json": {"synthetic": True},
        "co_pmid.json": {"citation": "Perioperative Bridging Trial PMID: 26095867"},
    }
}


@pytest.fixture
def manifest(tmp_path):
    p = tmp_path / "provenance_manifest.json"
    p.write_text(json.dumps(MANIFEST, ensure_ascii=False), encoding="utf-8")
    return p


class TestUngVienKhacHatGiongDungDuoc:
    """Ranh giới sống còn: lời khai chưa tra ngược KHÔNG được đem đi đo."""

    def test_rut_duoc_ung_vien(self, manifest):
        assert len(mo_tu_provenance(manifest).ung_vien) >= 6

    def test_khong_ung_vien_nao_tu_dong_duoc_coi_la_xac_minh(self, manifest):
        assert mo_tu_provenance(manifest).dung_duoc == []

    def test_co_DOI_van_CHUA_phai_xac_minh(self, manifest):
        """Manifest ghi synthetic:true — định danh cũng có thể là bịa."""
        co_doi = [h for h in mo_tu_provenance(manifest).ung_vien if h.doi]
        assert co_doi and not any(h.da_xac_minh for h in co_doi)

    def test_co_PMID_van_CHUA_phai_xac_minh(self, manifest):
        co_ma = [h for h in mo_tu_provenance(manifest).ung_vien if h.ma]
        assert co_ma and not any(h.dung_duoc for h in co_ma)

    def test_xac_minh_roi_moi_dung_duoc(self):
        h = HatGiong(mo_ta="Bài nền tảng nào đó", bac_nguon=BacNguon.TRICH_DAN_ANESTHOS,
                     ma="pubmed:26095867", da_xac_minh=True)
        assert h.dung_duoc

    def test_xac_minh_nhung_khong_co_ma_thi_van_khong_dung_duoc(self):
        h = HatGiong(mo_ta="Một hướng dẫn không tra ra mã",
                     bac_nguon=BacNguon.TRICH_DAN_ANESTHOS, da_xac_minh=True)
        assert not h.dung_duoc


class TestBacDocLap:
    """Phép đo độ nhạy chỉ đáng tin bằng đúng mức độc lập của hạt giống nuôi nó."""

    def test_trich_dan_anesthos_doc_lap_hon_bac_cao_trong_kho(self):
        assert BacNguon.TRICH_DAN_ANESTHOS < BacNguon.BAC_CAO_TRONG_KHO

    def test_tham_khao_tong_quan_doc_lap_nhat(self):
        assert BacNguon.THAM_KHAO_TONG_QUAN == min(BacNguon)

    def test_ung_vien_tu_manifest_mang_dung_bac_2(self, manifest):
        assert all(h.bac_nguon is BacNguon.TRICH_DAN_ANESTHOS
                   for h in mo_tu_provenance(manifest).ung_vien)

    def test_bao_cao_neu_ro_bac_thap_la_gan_tu_xac_nhan(self, manifest):
        from tools.mo_hat_giong import MO_TA_BAC
        assert "gần tự xác nhận" in MO_TA_BAC[BacNguon.BAC_CAO_TRONG_KHO]


class TestTachTrichDanGhep:
    """Chuỗi ghép nhiều nguồn không tra ngược được về bài nào cả."""

    def test_tach_theo_dau_cham_phay(self):
        assert len(tach_trich_dan("Nguồn thứ nhất; Nguồn thứ hai; Nguồn thứ ba")) == 3

    def test_bo_manh_qua_ngan(self):
        assert tach_trich_dan("Một nguồn tử tế; x; y") == ["Một nguồn tử tế"]

    def test_mot_nguon_thi_giu_nguyen(self):
        assert tach_trich_dan("ASRA 2018 4th edition") == ["ASRA 2018 4th edition"]

    def test_moi_manh_thanh_mot_ung_vien_rieng(self, manifest):
        tu_sepsis = [h for h in mo_tu_provenance(manifest).ung_vien
                     if h.tu_tep == "sepsis_rules.json"]
        assert len(tu_sepsis) == 3


class TestBaoTepThieuTrichDan:
    def test_tep_khong_trich_dan_bi_neu_ten(self, manifest):
        assert ("khong_trich_dan.json", "không khai trích dẫn nào") in \
            mo_tu_provenance(manifest).bo_qua

    def test_loc_theo_tep_duoc(self, manifest):
        kq = mo_tu_provenance(manifest, chi_tep={"sugammadex_rules_vi.json"})
        assert {h.tu_tep for h in kq.ung_vien} == {"sugammadex_rules_vi.json"}

    def test_manifest_sai_dinh_dang_bi_tu_choi(self, tmp_path):
        p = tmp_path / "x.json"
        p.write_text(json.dumps({"linh tinh": 1}), encoding="utf-8")
        with pytest.raises(ValueError, match="không phải manifest xuất xứ"):
            mo_tu_provenance(p)


class TestTachChuDeCon:
    """Một 'chức năng' thường là N bài tổng quan, không phải một."""

    def test_khoa_cua_tep_la_ban_phan_ra_san(self, tmp_path):
        p = tmp_path / "crisis.json"
        p.write_text(json.dumps({
            "_metadata": {}, "anaphylaxis": {}, "last": {}, "cardiac-arrest": {},
        }), encoding="utf-8")
        assert tach_chu_de_con(p) == ["anaphylaxis", "last", "cardiac-arrest"]

    def test_bo_khoa_metadata(self, tmp_path):
        p = tmp_path / "x.json"
        p.write_text(json.dumps({"_metadata": {}, "_ghi_chu": {}, "that": {}}),
                     encoding="utf-8")
        assert tach_chu_de_con(p) == ["that"]

    def test_danh_sach_phang_gom_theo_nhom_duoc_ly(self, tmp_path):
        """173 hoạt chất: 173 truy vấn là vô lý, 1 truy vấn thì quá rộng."""
        p = tmp_path / "meds.json"
        p.write_text(json.dumps([
            {"name": "warfarin", "class": "chống đông"},
            {"name": "apixaban", "class": "chống đông"},
            {"name": "metformin", "class": "hạ đường huyết"},
        ]), encoding="utf-8")
        assert tach_chu_de_con(p) == ["chống đông", "hạ đường huyết"]

    def test_danh_sach_khong_co_nhom_thi_tra_rong(self, tmp_path):
        p = tmp_path / "x.json"
        p.write_text(json.dumps([{"name": "a"}, {"name": "b"}]), encoding="utf-8")
        assert tach_chu_de_con(p) == []


class TestBaoCaoNoiThatVeGioiHan:
    def test_canh_bao_khi_chua_xac_minh_duoc_gi(self, manifest):
        ra = bao_cao(mo_tu_provenance(manifest))
        assert "CHƯA đo độ nhạy được" in ra and "LỜI KHAI" in ra

    def test_neu_ro_tra_nguoc_la_kiem_toan_luon_xuat_xu(self, manifest):
        assert "kiểm toán luôn lời khai xuất xứ" in bao_cao(mo_tu_provenance(manifest))

    def test_mo_ta_qua_ngan_bi_tu_choi(self):
        with pytest.raises(ValidationError, match="quá ngắn để truy ngược"):
            HatGiong(mo_ta="x", bac_nguon=BacNguon.TRICH_DAN_ANESTHOS)

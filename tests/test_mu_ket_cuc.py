"""Nguyên tắc MÙ KẾT CỤC ở tầng sàng.

Loại một nghiên cứu vì **nó nghiên cứu gì** thì được. Loại nó vì **nó báo cáo
được gì** thì không — nghiên cứu đo kết cục nhưng ra kết quả rỗng thường không
báo cáo kết cục đó, nên loại theo "không báo cáo outcome quan tâm" sẽ **loại có
hệ thống các kết quả âm tính**, đẩy tổng hợp lệch về phía dương tính.

`EF2` phải là **nhãn trạng thái**, không phải **lý do loại**.
"""
import json
from pathlib import Path

import pytest

from tools.screen_run import ViPhamMuKetCuc, nap_tieu_chi, dong_tieu_chi

BO_TIEU_CHI = Path(__file__).resolve().parents[1] / "tools" / "criteria" / "default.json"


class _Protocol:
    def __init__(self, ma: list[str]):
        self.exclusion_criteria = ma


class TestCatalogKhaiLoai:
    def test_moi_muc_phai_khai_loai(self):
        """Mục không khai `loai` là mục chưa ai quyết nó dùng để làm gì."""
        for ma, muc in json.loads(BO_TIEU_CHI.read_text(encoding="utf-8")).items():
            assert "loai" in muc, f"{ma} không khai `loai`"
            assert muc["loai"] in ("ly_do_loai", "nhan_trang_thai"), f"{ma}: loai lạ"

    def test_EF2_la_nhan_trang_thai_khong_phai_ly_do_loai(self):
        d = json.loads(BO_TIEU_CHI.read_text(encoding="utf-8"))
        assert d["EF2"]["loai"] == "nhan_trang_thai"

    def test_EF2_ghi_ro_vi_sao(self):
        """Nhãn không kèm lý do thì vòng sau sẽ có người đổi ngược lại."""
        d = json.loads(BO_TIEU_CHI.read_text(encoding="utf-8"))
        assert d["EF2"].get("vi_sao"), "EF2 phải ghi vì sao nó không phải lý do loại"

    def test_cac_ma_khac_van_la_ly_do_loai(self):
        d = json.loads(BO_TIEU_CHI.read_text(encoding="utf-8"))
        for ma in ("ET1", "ET3", "ET5", "EF3"):
            assert d[ma]["loai"] == "ly_do_loai", f"{ma} bị đổi nhầm"


class TestNapTieuChiBatLoi:
    def test_thieu_loai_thi_bao_loi_khong_doan(self):
        with pytest.raises(ValueError, match="loai"):
            nap_tieu_chi({"XX1": {"label_vi": "a", "description_en": "b"}})

    def test_loai_la_thi_bao_loi(self):
        with pytest.raises(ValueError, match="loai"):
            nap_tieu_chi({"XX1": {"label_vi": "a", "description_en": "b", "loai": "linh tinh"}})

    def test_bo_tieu_chi_that_nap_duoc(self):
        d = nap_tieu_chi(json.loads(BO_TIEU_CHI.read_text(encoding="utf-8")))
        assert "EF2" in d


class TestKhongDuocDungNhanLamLyDoLoai:
    def test_protocol_khai_EF2_lam_ly_do_loai_thi_HONG_TO(self):
        """Bỏ qua im lặng còn tệ hơn: người duyệt tưởng tiêu chí đang được áp."""
        tc = json.loads(BO_TIEU_CHI.read_text(encoding="utf-8"))
        with pytest.raises(ViPhamMuKetCuc, match="EF2"):
            dong_tieu_chi(_Protocol(["ET1", "EF2"]), tc)

    def test_protocol_chi_dung_ly_do_loai_thi_chay_binh_thuong(self):
        tc = json.loads(BO_TIEU_CHI.read_text(encoding="utf-8"))
        dong = dong_tieu_chi(_Protocol(["ET1", "ET3"]), tc)
        assert len(dong) == 2
        assert all(d.startswith("- ET") for d in dong)

    def test_ma_khong_co_trong_bo_tieu_chi_thi_bo_qua(self):
        """Giữ nguyên hành vi cũ: mã lạ không làm hỏng lượt chạy."""
        assert dong_tieu_chi(_Protocol(["KHONG_TON_TAI"]), {}) == []

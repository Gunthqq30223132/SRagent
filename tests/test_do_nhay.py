"""Test phép đo độ nhạy bằng bài mồi.

Câu hỏi bộ test này chốt: siết truy vấn cho gọn có làm mất bài nền tảng không?
Nếu có thì lần siết đó phải bị TỪ CHỐI, dù khối lượng giảm đẹp đến đâu.
"""

from __future__ import annotations

from tools.do_nhay import (
    MOI_CHONG_DONG,
    bao_cao,
    kiem_bai_moi,
    so_sanh_hai_truy_van,
)

DU_CA_BON = list(MOI_CHONG_DONG)


class TestDoDuocDoNhay:
    def test_lay_du_bai_moi_thi_dat(self):
        kq = kiem_bai_moi(DU_CA_BON)
        assert kq.dat and kq.do_nhay == 1.0

    def test_sot_mot_bai_la_truot(self):
        """Không có ngưỡng mềm: sót 1/4 vẫn là trượt."""
        kq = kiem_bai_moi(DU_CA_BON[:3])
        assert not kq.dat
        assert kq.do_nhay == 0.75
        assert kq.bo_sot == [DU_CA_BON[3]]

    def test_khong_lay_duoc_gi(self):
        assert kiem_bai_moi([]).do_nhay == 0.0

    def test_bao_sot_kem_ly_do_bai_do_quan_trong(self):
        """Chỉ báo 'sót pubmed:26095867' thì người đọc không biết mất gì."""
        kq = kiem_bai_moi([m for m in DU_CA_BON if m != "pubmed:26095867"])
        assert "BRIDGE" in bao_cao(kq)


class TestChuanHoaMaTruocKhiSo:
    """Sai lệch định dạng mã KHÔNG được biến thành báo sót giả."""

    def test_so_tran_van_khop(self):
        assert kiem_bai_moi(["26095867", "34108229", "36462533", "40448969"]).dat

    def test_dang_pmid_van_khop(self):
        kq = kiem_bai_moi(["PMID: 26095867"])
        assert "pubmed:26095867" in kq.tim_thay

    def test_url_van_khop(self):
        kq = kiem_bai_moi(["https://pubmed.ncbi.nlm.nih.gov/34108229/"])
        assert "pubmed:34108229" in kq.tim_thay

    def test_ma_rac_khong_lam_sap(self):
        kq = kiem_bai_moi(["", "không-phải-mã", "26095867"])
        assert "pubmed:26095867" in kq.tim_thay


class TestChamMotLanSietTruyVan:
    def test_giam_khoi_luong_ma_giu_du_moi_thi_nhan(self):
        bang = so_sanh_hai_truy_van(
            kiem_bai_moi(DU_CA_BON), kiem_bai_moi(DU_CA_BON), 1767, 300,
        )
        assert "✓ NHẬN" in bang and "giảm 83%" in bang

    def test_giam_khoi_luong_ma_mat_moi_thi_tu_choi(self):
        """Đây là cái bẫy chính: bảng số trông đẹp mà thực chất là thụt lùi."""
        bang = so_sanh_hai_truy_van(
            kiem_bai_moi(DU_CA_BON), kiem_bai_moi(DU_CA_BON[:3]), 1767, 120,
        )
        assert "✗ TỪ CHỐI" in bang
        assert "SÓT THÊM" in bang

    def test_neu_ro_bai_nao_vua_bi_mat(self):
        bang = so_sanh_hai_truy_van(
            kiem_bai_moi(DU_CA_BON), kiem_bai_moi(DU_CA_BON[:3]), 1767, 120,
        )
        assert DU_CA_BON[3] in bang

    def test_da_sot_san_thi_khong_tinh_la_sot_them(self):
        """Truy vấn cũ đã sót bài đó rồi thì lần siết này không phải thủ phạm."""
        thieu = DU_CA_BON[:3]
        bang = so_sanh_hai_truy_van(
            kiem_bai_moi(thieu), kiem_bai_moi(thieu), 1767, 400,
        )
        assert "SÓT THÊM" not in bang


class TestNoiRoGioiHanCuaPhepDo:
    def test_dat_van_phai_noi_day_khong_phai_bang_chung_day_du(self):
        """Không được để người đọc tưởng độ nhạy 100% là truy vấn đã đầy đủ."""
        assert "không phải ĐỦ" in bao_cao(kiem_bai_moi(DU_CA_BON))

    def test_bon_bai_moi_deu_da_xac_minh_doc_lap(self):
        assert len(MOI_CHONG_DONG) == 4
        assert all(m.startswith("pubmed:") and v for m, v in MOI_CHONG_DONG.items())

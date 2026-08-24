"""Test đường từ vấn đề thô -> điểm quyết định -> khung tuyển chọn -> truy vấn.

Ràng buộc quan trọng nhất bộ test này giữ, và lý do nó phải là ràng buộc CẤU
TRÚC chứ không phải lời dặn:

  MÙ KẾT CỤC — không loại nghiên cứu dựa trên thứ nó TÌM THẤY.

Một lời dặn trong tài liệu thì sẽ có ngày ai đó quên. Ở đây `ket_cuc` được ghi
lại nhưng hàm dựng truy vấn không bao giờ đọc tới nó, nên vi phạm trở thành thứ
KHÔNG VIẾT RA ĐƯỢC. Test dưới khoá đúng tính chất đó.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tools.dat_cau_hoi import (
    DOI_CHIEU_BAT_BUOC,
    DangCauHoi,
    DiemQuyetDinh,
    KhungTuyenChon,
    goi_y_dang,
    tu_luoc_do_dau_ra,
)


def khung(dang=DangCauHoi.DIEU_TRI, **kw):
    mac_dinh = dict(
        diem_quyet_dinh="ngung-thuoc-truoc-mo",
        dang=dang,
        pham_vi=["Anticoagulants", "Warfarin"],
        mat_khao_sat=["Preoperative Care", "perioperative"],
        doi_chieu=["continued therapy"] if DOI_CHIEU_BAT_BUOC[dang] else [],
        ket_cuc=["thromboembolism", "major bleeding"],
    )
    return KhungTuyenChon(**{**mac_dinh, **kw})


class TestMuKetCucBaoDamBangCauTruc:
    """Vi phạm O-blind phải là chuyện KHÔNG VIẾT RA ĐƯỢC, không phải chuyện phải nhớ."""

    def test_ket_cuc_khong_lot_vao_truy_van(self):
        q = khung(ket_cuc=["thromboembolism", "major bleeding", "mortality"]).thanh_truy_van()
        for tu in ("thromboembolism", "bleeding", "mortality"):
            assert tu not in q.lower()

    def test_doi_ket_cuc_khong_lam_doi_truy_van(self):
        """Bằng chứng mạnh nhất: kết cục không tham gia vào việc dựng truy vấn."""
        a = khung(ket_cuc=["mortality"]).thanh_truy_van()
        b = khung(ket_cuc=["chi phí", "chất lượng sống", "biến cố chảy máu"]).thanh_truy_van()
        assert a == b

    def test_ket_cuc_van_bat_buoc_phai_khai(self):
        """Không lọc theo kết cục KHÁC với không cần khai kết cục."""
        with pytest.raises(ValidationError, match="không dựng được bảng tổng hợp"):
            khung(ket_cuc=[])

    def test_qua_bay_ket_cuc_bi_tu_choi(self):
        with pytest.raises(ValidationError, match="tối đa 7"):
            khung(ket_cuc=[f"kết cục {i}" for i in range(8)])

    def test_thiet_ke_nghien_cuu_cung_khong_lot_vao_truy_van(self):
        """Thiết kế là tiêu chí XẾP HẠNG lúc sàng, không phải bộ lọc lúc tìm."""
        q = khung().thanh_truy_van()
        assert "PUB_TYPE" not in q and "Randomized" not in q


class TestDoiChieuTheoDangCauHoi:
    """Bắt mọi dạng phải có đối chiếu sẽ loại sạch nghiên cứu tiên lượng cần — im lặng."""

    def test_dieu_tri_thieu_doi_chieu_bi_tu_choi(self):
        with pytest.raises(ValidationError, match="cần nhóm đối chiếu"):
            khung(DangCauHoi.DIEU_TRI, doi_chieu=[])

    def test_tac_hai_can_nhom_khong_phoi_nhiem(self):
        with pytest.raises(ValidationError, match="không phơi nhiễm"):
            khung(DangCauHoi.TAC_HAI, doi_chieu=[])

    def test_tien_luong_KHONG_bat_buoc_doi_chieu(self):
        assert khung(DangCauHoi.TIEN_LUONG, doi_chieu=[]).doi_chieu == []

    def test_chan_doan_KHONG_bat_buoc_doi_chieu(self):
        assert khung(DangCauHoi.CHAN_DOAN, doi_chieu=[]).doi_chieu == []

    def test_chan_doan_phan_biet_KHONG_bat_buoc(self):
        assert khung(DangCauHoi.CHAN_DOAN_PHAN_BIET, doi_chieu=[]).doi_chieu == []

    def test_truy_van_bo_han_menh_de_doi_chieu_khi_khong_co(self):
        q = khung(DangCauHoi.TIEN_LUONG, doi_chieu=[]).thanh_truy_van()
        assert q.count(" AND ") == 1


class TestTruyVanMoDauDeGatHatGiong:
    """Khởi động lạnh: không ai đưa bài mồi, phải tự gặt từ y văn."""

    def test_nham_vao_tong_quan_va_huong_dan(self):
        q = khung().truy_van_mo_dau()
        assert "Systematic Review" in q and "Practice Guideline" in q

    def test_rong_hon_truy_van_chinh(self):
        """Hẹp bằng truy vấn chính thì hạt giống gặt được không kiểm được điểm mù."""
        k = khung()
        assert "doi_chieu" not in k.truy_van_mo_dau()
        assert len(k.truy_van_mo_dau()) > len(k.thanh_truy_van())

    def test_van_khong_lot_ket_cuc(self):
        q = khung(ket_cuc=["mortality", "major bleeding"]).truy_van_mo_dau()
        assert "mortality" not in q.lower() and "bleeding" not in q.lower()


class TestSuyDiemQuyetDinhTuLuocDoDauRa:
    """Biến 'liệt kê câu hỏi nghiên cứu' từ việc nhớ ra thành việc đọc mã."""

    def test_truong_la_thanh_diem_quyet_dinh(self):
        assert tu_luoc_do_dau_ra({"ngung_truoc_mo": {
            "co_ngung": None, "so_gio_truoc": None}}) == [
            "ngung_truoc_mo.co_ngung", "ngung_truoc_mo.so_gio_truoc"]

    def test_bo_qua_khoa_metadata(self):
        assert tu_luoc_do_dau_ra({"_metadata": {"x": 1}, "that": None}) == ["that"]

    def test_long_nhieu_tang(self):
        assert tu_luoc_do_dau_ra({"a": {"b": {"c": None}}}) == ["a.b.c"]

    def test_luoc_do_rong_tra_rong(self):
        assert tu_luoc_do_dau_ra({}) == []

    def test_dict_rong_tinh_la_la(self):
        """Trường khai rỗng vẫn là trường phải điền — không được bỏ sót."""
        assert tu_luoc_do_dau_ra({"can_dien": {}}) == ["can_dien"]


class TestGoiYDang:
    def test_nhan_ra_cau_hoi_tac_hai(self):
        assert goi_y_dang("Nguy cơ tụ máu ngoài màng cứng là bao nhiêu") \
            is DangCauHoi.TAC_HAI

    def test_nhan_ra_cau_hoi_chan_doan(self):
        assert goi_y_dang("Xét nghiệm nào cần làm trước mổ") is DangCauHoi.CHAN_DOAN

    def test_nhan_ra_cau_hoi_tien_luong(self):
        assert goi_y_dang("Tiên lượng biến cố tim mạch sau mổ") is DangCauHoi.TIEN_LUONG

    def test_mac_dinh_la_dieu_tri(self):
        assert goi_y_dang("Có nên ngưng warfarin trước mổ không") is DangCauHoi.DIEU_TRI


class TestDiemQuyetDinhPhaiCuThe:
    def test_cau_hoi_mo_ho_bi_tu_choi(self):
        with pytest.raises(ValidationError, match="quá mơ hồ"):
            DiemQuyetDinh(ma="x", cau_hoi="kháng đông",
                          dau_ra_can_co="số giờ ngưng thuốc trước mổ",
                          dang=DangCauHoi.DIEU_TRI)

    def test_dau_ra_mo_ho_bi_tu_choi(self):
        with pytest.raises(ValidationError, match="quá mơ hồ"):
            DiemQuyetDinh(ma="x", cau_hoi="Có nên ngưng warfarin trước mổ không",
                          dau_ra_can_co="tốt", dang=DangCauHoi.DIEU_TRI)

    def test_diem_cu_the_thi_nhan(self):
        d = DiemQuyetDinh(ma="ngung-truoc-mo",
                          cau_hoi="Có nên ngưng warfarin trước thủ thuật không",
                          dau_ra_can_co="có/không kèm ngưỡng nguy cơ huyết khối",
                          dang=DangCauHoi.DIEU_TRI)
        assert d.dang is DangCauHoi.DIEU_TRI

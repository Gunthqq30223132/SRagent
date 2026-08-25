"""Test chuẩn vàng từ nguồn tổng hợp ngoài (UpToDate và tương đương).

RÀNG BUỘC QUAN TRỌNG NHẤT bộ test này giữ:

  không phát hiện lỗ hổng  !=  kho đã đủ

Nguồn tam cấp chỉ trích bài biên tập viên chọn. Phép đo chứng minh được THẤT BẠI
chứ không chứng minh được THÀNH CÔNG. Bộ test khoá luôn cả tên gọi của trạng
thái tốt nhất — để không ai đổi nó thành 'ĐẠT' rồi báo một thành tích không có.
"""

from __future__ import annotations

from tools.nguon_tong_hop import (
    TOI_THIEU_DE_KET_LUAN,
    KetLuan,
    bao_cao,
    doi_chieu_voi_kho,
    ma_tran,
    tach_danh_muc,
)

# Trích dẫn dựng theo đúng dạng bản in UpToDate: đánh số, ngắt dòng giữa mục.
DANH_MUC = """
1. Douketis JD, Spyropoulos AC, Kaatz S, et al. Perioperative Bridging
   Anticoagulation in Patients with Atrial Fibrillation. N Engl J Med 2015;
   373:823. PMID: 26095867
2. Kovacs MJ, Wells PS, Anderson DR, et al. Postoperative low molecular weight
   heparin bridging treatment. BMJ 2021; 373:n1205. PMID: 34108229
3. Some Author, Another One. A paper with no identifier at all. J Fake Med 2019;
   12:345.
"""


class TestTachDanhMuc:
    def test_noi_lai_muc_bi_ngat_dong(self):
        """Bản in PDF xuống dòng theo bề rộng trang, không theo mục.

        Cắt theo dòng sẽ biến một trích dẫn thành ba mảnh không tra được mảnh nào.
        """
        muc = tach_danh_muc(DANH_MUC)
        assert len(muc) == 3
        assert "N Engl J Med 2015" in muc[0].nguyen_van

    def test_boc_duoc_pmid(self):
        muc = tach_danh_muc(DANH_MUC)
        assert muc[0].pmid == "26095867" and muc[0].ma == "pubmed:26095867"

    def test_muc_khong_co_dinh_danh_thi_khong_tra_duoc_ngay(self):
        assert not tach_danh_muc(DANH_MUC)[2].tra_duoc_ngay

    def test_lay_nam_xuat_ban_khong_lay_so_trang(self):
        """Trích dẫn có nhiều số 4 chữ số; năm là số hợp lệ CUỐI cùng."""
        muc = tach_danh_muc("1. Ai đó. Nhan đề nào đó. Tạp chí 2015; 373:8234.\n")
        assert muc[0].nam == 2015

    def test_boc_duoc_doi(self):
        muc = tach_danh_muc("1. Ai đó. Nhan đề. Tạp chí 2020. doi:10.1001/jama.2020.1234.\n")
        assert muc[0].doi == "10.1001/jama.2020.1234" and muc[0].tra_duoc_ngay

    def test_van_ban_rong_khong_no(self):
        assert tach_danh_muc("") == []


class TestMaTran:
    def test_ba_cach_danh_ma_cung_mot_bai_deu_khop(self):
        """Lỗi này đã suýt khiến tôi kết tội Spark bịa mã."""
        assert ma_tran("pubmed:26095867") == ma_tran("europepmc:MED:26095867") == "26095867"


class TestPhepDoChayMotChieu:
    """Chứng minh được thất bại, KHÔNG chứng minh được thành công."""

    @staticmethod
    def _muc(n: int):
        return tach_danh_muc("".join(f"{i}. Tác giả. Nhan đề dài đủ. T 2020. PMID: {1000 + i}\n"
                                     for i in range(1, n + 1)))

    def test_kho_chua_du_KHONG_duoc_goi_la_dat(self):
        """Ràng buộc quan trọng nhất của cả tệp này."""
        muc = self._muc(6)
        kq = doi_chieu_voi_kho(muc, [f"europepmc:MED:{1000 + i}" for i in range(1, 7)])
        assert kq.ket_luan is KetLuan.KHONG_PHAT_HIEN_LO_HONG
        assert kq.ket_luan.value != "ĐẠT" and kq.do_phu == 1.0

    def test_sot_bai_la_lo_hong_da_xac_nhan(self):
        kq = doi_chieu_voi_kho(self._muc(6), [f"europepmc:MED:{1000 + i}" for i in range(1, 4)])
        assert kq.ket_luan is KetLuan.CO_LO_HONG and len(kq.sot) == 3

    def test_bao_dich_danh_ma_bi_sot(self):
        """Sót mà không biết sót cái gì thì không sửa được truy vấn."""
        kq = doi_chieu_voi_kho(self._muc(6), [f"europepmc:MED:{1000 + i}" for i in range(1, 6)])
        assert kq.sot == ["pubmed:1006"]


class TestQuaItThiVoHieu:
    def test_duoi_nguong_thi_vo_hieu_du_kho_chua_du(self):
        """Tra được 2/150 rồi báo 'không phát hiện lỗ hổng' là báo về ĐỘ MÙ của
        phép đo, không phải về chất lượng kho."""
        muc = tach_danh_muc(
            "1. Tác giả. Nhan đề dài đủ. T 2020. PMID: 111\n"
            "2. Tác giả. Nhan đề dài đủ. T 2020. PMID: 222\n"
        )
        kq = doi_chieu_voi_kho(muc, ["pubmed:111", "pubmed:222"])
        assert kq.ket_luan is KetLuan.VO_HIEU

    def test_vo_hieu_thi_do_phu_la_None_khong_phai_0_hay_1(self):
        """Số vô nghĩa lọt vào bảng rồi được đọc như số thật — đã mất một lần."""
        kq = doi_chieu_voi_kho([], [])
        assert kq.ket_luan is KetLuan.VO_HIEU and kq.do_phu is None

    def test_dung_nguong_thi_ket_luan_duoc(self):
        ma = [str(9000 + i) for i in range(TOI_THIEU_DE_KET_LUAN)]
        muc = tach_danh_muc("".join(
            f"{i}. Tác giả. Nhan đề dài đủ. T 2020. PMID: {m}\n" for i, m in enumerate(ma, 1)))
        assert len(muc) == TOI_THIEU_DE_KET_LUAN
        kq = doi_chieu_voi_kho(muc, [f"pubmed:{m}" for m in ma])
        assert kq.ket_luan is not KetLuan.VO_HIEU

    def test_so_qua_ngan_KHONG_duoc_nhan_nham_la_pmid(self):
        """Biểu thức nhận PMID cố ý chặt (4-8 chữ số).

        Lỏng hơn thì số rác trong trích dẫn (số tập, số trang) thành 'PMID' —
        và mã bịa thì âm thầm làm lệch cả tử số lẫn mẫu số. Chặt quá thì bài
        rơi vào 'không tra được', lộ ra ở mẫu số và không đổ lỗi cho ai.
        Hỏng an toàn thắng hỏng im lặng.
        """
        assert tach_danh_muc("1. Tác giả. Nhan đề dài đủ. T 2020. PMID: 7\n")[0].pmid is None


class TestMucChuaTraDuocKhongBiTinhLaSot:
    def test_khong_do_loi_truy_van_ve_bai_chua_chac_ton_tai(self):
        muc = tach_danh_muc(DANH_MUC)
        kq = doi_chieu_voi_kho(muc, ["pubmed:26095867", "pubmed:34108229"])
        assert len(kq.khong_tra_duoc) == 1 and kq.sot == []
        assert kq.tong_muc == 3 and kq.so_tra_duoc == 2


class TestBaoCaoNoiThang:
    def test_bao_cao_khong_phat_hien_van_phai_canh_bao_khong_phai_du(self):
        muc = TestPhepDoChayMotChieu._muc(6)
        ra = bao_cao(doi_chieu_voi_kho(muc, [f"europepmc:MED:{1000 + i}" for i in range(1, 7)]))
        assert "KHÔNG phải 'kho đã đủ'" in ra

    def test_bao_cao_vo_hieu_khong_in_con_so_do_phu(self):
        ra = bao_cao(doi_chieu_voi_kho([], [], ten_chu_de="x"))
        assert "VÔ HIỆU" in ra and "%)" not in ra.split("KẾT LUẬN")[1]

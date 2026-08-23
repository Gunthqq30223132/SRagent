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


class TestMotChoDungCauDuyNhat:
    """Chốt bài học đã trả giá: HAI chỗ dựng truy vấn = hai phép đo bất đồng.

    Lần chạy thật cho ra 0/4 ở bước đo độ nhạy và 4/4 ở lưới soi, CÙNG LÚC, cùng
    truy vấn. Nguyên nhân không phải chỗ nào dựng sai — mà là có hai chỗ dựng.
    Khi hai phép đo cùng một thứ bất đồng thì không có căn cứ nào phân xử.
    """

    def test_dang_cau_giu_nong_va_it_ngoac(self):
        from tools.do_nhay import cau_truy_van_moi
        q = cau_truy_van_moi("A OR B", "pubmed:26095867")
        assert q == "EXT_ID:26095867 AND (A OR B)"
        assert q.count("(") == 1        # dạng lồng 4 tầng đã làm Europe PMC trả rỗng
        assert q.startswith("EXT_ID:")  # mã đứng TRƯỚC, như dạng đã chạy đúng 12/12

    def test_nhan_moi_dang_ma(self):
        from tools.do_nhay import cau_truy_van_moi
        for dang in ("26095867", "pubmed:26095867", "europepmc:MED:26095867"):
            assert cau_truy_van_moi("X", dang).startswith("EXT_ID:26095867 AND")

    def test_hai_duong_ma_dung_CHUNG_bo_dung_cau(self):
        """Ràng buộc thật sự quan trọng: đo độ nhạy và lưới soi phải dựng y hệt."""
        from tools.do_nhay import cau_truy_van_moi, kiem_bai_moi_qua_mang
        from tools.soi_truy_van import soi_nhom

        da_hoi: list[str] = []

        class G:
            def quet_toan_bo(self, q, tran=1, page_size=1):
                da_hoi.append(q)
                return [], 1

        kiem_bai_moi_qua_mang(G(), "NHOM", {"pubmed:1": "mồi"})
        soi_nhom(G(), ["pubmed:1"], {"n": "NHOM"})
        assert da_hoi[0] == da_hoi[1] == cau_truy_van_moi("NHOM", "pubmed:1")

    def test_loi_mang_tinh_la_SOT_khong_phai_bo_qua(self):
        """Lỗi mạng lặng lẽ thành 'đạt' đúng là kiểu hỏng cổng này dựng lên để chặn."""
        from tools.do_nhay import kiem_bai_moi_qua_mang

        class Vo:
            def quet_toan_bo(self, q, tran=1, page_size=1):
                raise RuntimeError("mạng hỏng")

        kq = kiem_bai_moi_qua_mang(Vo(), "X", {"pubmed:1": "mồi"})
        assert not kq.dat and kq.bo_sot == ["pubmed:1"]

    def test_hoi_dung_mot_cau_moi_bai(self):
        from tools.do_nhay import MOI_CHONG_DONG, kiem_bai_moi_qua_mang
        dem = []

        class G:
            def quet_toan_bo(self, q, tran=1, page_size=1):
                dem.append(q)
                return [], 1

        kq = kiem_bai_moi_qua_mang(G(), "X")
        assert len(dem) == len(MOI_CHONG_DONG) and kq.dat

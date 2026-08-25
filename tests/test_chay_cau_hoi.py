"""Test bộ chạy nhiều câu hỏi + phép đo khởi động lạnh.

PHÉP ĐO ĐANG ĐƯỢC KIỂM: bài tổng quan hệ thống mà truy vấn MỞ ĐẦU gặt được có
lọt vào kho CHÍNH không. Sót bài tổng quan về đúng chủ đề = lỗ hổng độ nhạy đo
được, phát hiện với 0 phút chuyên gia.

Ranh giới quan trọng nhất bộ test này giữ:

  gặt được 0 bài tổng quan  !=  đạt

Không có gì để đo thì phải IM LẶNG, không được báo qua. Đây đúng là kiểu lỗi
mà 'cột Verified' của Spark mắc: trường không có ràng buộc nào thì mặc định đẹp.
"""

from __future__ import annotations

import json

import pytest

from tools.chay_cau_hoi import KetQuaCau, chay_mot_cau, khung_tu_cau

CAU = {
    "ma": "nhin-an-hit-sac", "dang": "harm", "uu_tien": 1, "rui_ro": "chết người",
    "cau_hoi": "Thời gian nhịn ăn trước mổ và nguy cơ hít sặc",
    "dau_ra_can_co": "số giờ nhịn theo loại thức ăn",
    "pham_vi": ['KW:"Preoperative Care"'],
    "mat_khao_sat": ['KW:"Fasting"'],
    "doi_chieu": ['"prolonged fasting"'],
    "ket_cuc": ["pulmonary aspiration", "gastric volume"],
}


class Doc:
    def __init__(self, sid, bac=None):
        self.source_id = sid
        self.evidence_level = bac
        self.uid = sid

    def model_dump(self, mode=None):
        return {"source_id": self.source_id, "evidence_level": self.evidence_level}


class Gia:
    """Fetcher giả: trả tổng quan cho truy vấn mở đầu, kho cho truy vấn chính."""

    def __init__(self, tong_quan, kho, no=False):
        self.tong_quan, self.kho, self.no = tong_quan, kho, no
        self.loai_bai: dict = {}
        self.da_hoi: list[str] = []

    def quet_toan_bo(self, q, tran=1, page_size=1000):
        self.da_hoi.append(q)
        if self.no:
            raise RuntimeError("mạng hỏng")
        ds = self.tong_quan if "PUB_TYPE" in q else self.kho
        return ds, len(ds)


class TestPhepDoKhoiDongLanh:
    """Sau khi gỡ mệnh đề đối chiếu, truy vấn mở đầu là TẬP CON CHẶT của truy
    vấn chính, nên phép so chồng lấn luôn ra 100% và KHÔNG nói lên điều gì.

    Bộ test này khoá đúng chỗ đó: con số độ phủ vẫn tính được, nhưng `dat` phải
    là False vì phép đo vô hiệu. Báo '✓' cho một phép đo không thể thất bại là
    đúng kiểu cột 'Verified' tự khai.
    """

    def test_do_phu_van_tinh_duoc(self):
        tq = [Doc("europepmc:MED:1", 2), Doc("europepmc:MED:2", 1)]
        kho = tq + [Doc(f"europepmc:MED:{i}") for i in range(10, 60)]
        kq, docs = chay_mot_cau(Gia(tq, kho), CAU)
        assert kq.do_phu_tong_quan == 1.0 and len(docs) == 52

    def test_do_phu_100_van_KHONG_duoc_bao_dat(self):
        """Đây là ràng buộc quan trọng nhất của cả bộ test này."""
        tq = [Doc("europepmc:MED:1", 2)]
        kq, _ = chay_mot_cau(Gia(tq, tq), CAU)
        assert kq.do_phu_tong_quan == 1.0
        assert not kq.co_hieu_luc and not kq.dat

    def test_kho_sot_tong_quan_van_do_duoc_ty_le(self):
        tq = [Doc(f"europepmc:MED:{i}", 2) for i in range(1, 6)]
        kho = tq[:2] + [Doc("europepmc:MED:99")]        # sót 3/5
        kq, _ = chay_mot_cau(Gia(tq, kho), CAU)
        assert not kq.dat and kq.do_phu_tong_quan == 0.4

    def test_chay_du_bon_truy_van(self):
        """2 truy vấn chính + 2 truy vấn bỏ-một-mệnh-đề (phép đo thay thế)."""
        g = Gia([Doc("europepmc:MED:1", 2)], [Doc("europepmc:MED:1")])
        chay_mot_cau(g, CAU)
        assert len(g.da_hoi) == 4
        assert "PUB_TYPE" in g.da_hoi[0] and "PUB_TYPE" not in g.da_hoi[1]

    def test_ghi_lai_ket_qua_bo_tung_menh_de(self):
        g = Gia([Doc("europepmc:MED:1", 2)], [Doc("europepmc:MED:1")])
        kq, _ = chay_mot_cau(g, CAU)
        assert set(kq.thieu) == {"pham_vi", "mat_khao_sat"}


class TestKhongCoGiDeDoThiKhongDuocBaoQua:
    """'Cột Verified' của Spark: trường không ràng buộc thì mặc định đẹp."""

    def test_gat_duoc_0_tong_quan_KHONG_phai_dat(self):
        kq, _ = chay_mot_cau(Gia([], [Doc(f"europepmc:MED:{i}") for i in range(50)]), CAU)
        assert kq.so_tong_quan == 0 and not kq.dat

    def test_kho_rong_cung_khong_phai_dat(self):
        assert not chay_mot_cau(Gia([], []), CAU)[0].dat

    def test_do_phu_khong_chia_cho_khong(self):
        assert KetQuaCau("x", "harm").do_phu_tong_quan == 0.0


class TestLoiKhongLamSapCaLuot:
    def test_loi_mang_duoc_ghi_lai_khong_nem_ra(self):
        kq, docs = chay_mot_cau(Gia([], [], no=True), CAU)
        assert kq.loi and "mạng hỏng" in kq.loi and docs == []

    def test_cau_loi_khong_bao_gio_tinh_la_dat(self):
        assert not chay_mot_cau(Gia([], [], no=True), CAU)[0].dat

    def test_luon_tra_ve_cap_ke_ca_khi_loi(self):
        """Kiểu trả về đổi theo nhánh là cách nơi gọi lặng lẽ xử sai một nhánh."""
        for g in (Gia([], [], no=True), Gia([Doc("europepmc:MED:1", 2)], [Doc("europepmc:MED:1")])):
            ra = chay_mot_cau(g, CAU)
            assert isinstance(ra, tuple) and len(ra) == 2 and isinstance(ra[1], list)


class TestDemBacChungCu:
    def test_gom_ca_bai_chua_phan_loai(self):
        kho = [Doc("europepmc:MED:1", 1), Doc("europepmc:MED:2", None),
               Doc("europepmc:MED:3", None)]
        kq, _ = chay_mot_cau(Gia([Doc("europepmc:MED:1", 1)], kho), CAU)
        assert kq.bac == {1: 1, None: 2}


class TestChayThatTrenHoSoTienMe:
    """Chạy trên chính hồ sơ thật, không phải dữ liệu dựng cho vừa test."""

    @staticmethod
    def _ho_so():
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent / "tools/profiles/tien_me_cau_hoi.json"
        return json.loads(p.read_text(encoding="utf-8"))["cau_hoi"]

    def test_moi_cau_uu_tien_1_dung_duoc_khung(self):
        u1 = [c for c in self._ho_so() if c["uu_tien"] == 1]
        assert len(u1) == 6
        assert all(khung_tu_cau(c).thanh_truy_van() for c in u1)

    def test_ba_cau_dau_du_ba_dang_khac_nhau(self):
        """Chọn ba dạng khác nhau là chủ ý — để lộ ra khung có thiên vị 'điều trị' không."""
        ba = [c for c in self._ho_so() if c["uu_tien"] == 1][:3]
        assert len({c["dang"] for c in ba}) == 3

    def test_chay_duoc_cau_that_qua_fetcher_gia(self):
        c = [x for x in self._ho_so() if x["ma"] == "nhin-an-hit-sac"][0]
        tq = [Doc("europepmc:MED:1", 2)]
        kq, _ = chay_mot_cau(Gia(tq, tq + [Doc("europepmc:MED:2")]), c)
        assert kq.dang == "harm" and kq.da_tai == 2

    def test_khong_cau_that_nao_con_loc_theo_doi_chieu(self):
        """Đối chiếu đã thành tiêu chí sàng, không còn là bộ lọc lúc tìm.

        Chốt bằng CẤU TRÚC chứ không bằng chuỗi: so chuỗi sẽ báo oan ở câu
        tê-vùng-vs-mê-toàn-thân, nơi 'general anesthesia' vừa là MẶT KHẢO SÁT
        vừa là ĐỐI CHIẾU. Cùng chữ, hai vai — đúng cái bẫy đã mắc một lần khi
        kiểm mù kết cục.

        Cách chốt đúng: đổi sạch danh sách đối chiếu, truy vấn không được đổi.
        """
        for c in self._ho_so():
            goc = khung_tu_cau(c).thanh_truy_van()
            if not (c.get("doi_chieu") or []):
                continue
            khac = khung_tu_cau({**c, "doi_chieu": ['"một cụm hoàn toàn khác"']})
            assert khac.thanh_truy_van() == goc, c["ma"]


class TestCLI:
    def test_ma_khong_ton_tai_bao_ro(self, capsys):
        from tools.chay_cau_hoi import main
        assert main(["--ma", "khong-co-cau-nay"]) == 2
        assert "Không có câu hỏi mã" in capsys.readouterr().out

    def test_ho_so_thieu_bi_nem_loi_ro(self, tmp_path):
        from tools.chay_cau_hoi import main
        with pytest.raises(FileNotFoundError):
            main(["--ho-so", str(tmp_path / "khong-co.json")])

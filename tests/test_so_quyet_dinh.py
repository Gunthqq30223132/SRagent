"""Test kho bất biến + sổ quyết định nối thêm.

Ranh giới mà bộ test này giữ, xếp theo mức nguy hiểm nếu để lọt:

  1. Quyết định gắn nhầm kho  -> sàng trên tập bài này, báo cáo trên tập bài khác
  2. Loại không lý do         -> PRISMA mất số liệu, không khôi phục được
  3. Dòng hỏng bị nuốt        -> một bài biến mất, không ai biết để đi tìm
  4. Đổi ý bị giấu            -> mất dấu vết chỗ tiêu chí đang mơ hồ
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from tools.so_quyet_dinh import (
    QuyetDinh,
    Quyet,
    SoQuyetDinh,
    van_tay_kho,
    van_tay_tu_tep,
)

VT = van_tay_kho(["europepmc:MED:1", "europepmc:MED:2", "europepmc:MED:3"])


def qd(ma: str, quyet=Quyet.GIU, ly_do="", nguoi="gun", vt=VT, tc="v1"):
    return QuyetDinh(ma=ma, quyet_dinh=quyet, ly_do=ly_do, nguoi_sang=nguoi,
                     phien_ban_tieu_chi=tc, van_tay_kho=vt)


@pytest.fixture
def so(tmp_path):
    return SoQuyetDinh(tmp_path / "quyet_dinh.jsonl", VT)


class TestVanTayKho:
    """'Bất biến' mà không kiểm được thì chỉ là lời hứa."""

    def test_cung_tap_ma_thi_cung_van_tay_du_khac_thu_tu(self):
        assert van_tay_kho(["b", "a", "c"]) == van_tay_kho(["c", "b", "a"])

    def test_them_mot_ban_ghi_la_doi_van_tay(self):
        """Thêm bài nghĩa là tập cần sàng đã khác — quyết định cũ không còn phủ hết."""
        assert van_tay_kho(["a", "b"]) != van_tay_kho(["a", "b", "c"])

    def test_bot_mot_ban_ghi_la_doi_van_tay(self):
        assert van_tay_kho(["a", "b", "c"]) != van_tay_kho(["a", "b"])

    def test_van_tay_mang_so_luong_de_nguoi_doc_duoc(self):
        assert van_tay_kho(["a", "b", "c"]).endswith(":3")

    def test_dinh_dang_lai_tep_KHONG_lam_mat_cong_sang(self, tmp_path):
        """Băm danh sách mã, không băm byte thô — chủ ý, không phải tình cờ."""
        br = [{"source_id": "a"}, {"source_id": "b"}]
        g = tmp_path / "gon.json"
        d = tmp_path / "dep.json"
        g.write_text(json.dumps({"ban_ghi": br}), encoding="utf-8")
        d.write_text(json.dumps({"ban_ghi": br}, indent=4), encoding="utf-8")
        assert van_tay_tu_tep(g)[0] == van_tay_tu_tep(d)[0]

    def test_ban_ghi_khong_co_ma_bi_tu_choi(self, tmp_path):
        p = tmp_path / "x.json"
        p.write_text(json.dumps({"ban_ghi": [{"title": "không mã"}]}), encoding="utf-8")
        with pytest.raises(ValueError, match="không có source_id"):
            van_tay_tu_tep(p)


class TestQuyetDinhGanNhamKhoBiChan:
    """Rủi ro số 1: sàng trên tập bài này rồi báo cáo trên tập bài khác."""

    def test_ghi_van_tay_khac_bi_tu_choi_ngay(self, so):
        with pytest.raises(ValueError, match="Kho đã đổi"):
            so.ghi(qd("europepmc:MED:1", vt=van_tay_kho(["x", "y"])))

    def test_khong_ghi_gi_khi_mot_dong_trong_lo_sai_van_tay(self, so):
        """Cả lô bị từ chối, không ghi nửa vời — nửa vời khó phát hiện hơn hẳn."""
        with pytest.raises(ValueError):
            so.ghi_nhieu([qd("europepmc:MED:1"), qd("europepmc:MED:2", vt="sha256:la:9")])
        assert so.doc().quyet_dinh == []

    def test_doc_bo_qua_dong_van_tay_la_nhung_BAO_ra(self, so, tmp_path):
        so.ghi(qd("europepmc:MED:1"))
        # Giả lập sổ bị trộn từ kho khác (chép tay, gộp tệp...)
        la = qd("europepmc:MED:9", vt="sha256:khac:3")
        with so.duong_dan.open("a", encoding="utf-8") as f:
            f.write(json.dumps(la.model_dump(mode="json"), ensure_ascii=False) + "\n")
        kq = so.doc()
        assert len(kq.quyet_dinh) == 1
        assert kq.van_tay_la == {"sha256:khac:3": 1}


class TestLoaiPhaiCoLyDo:
    """Rủi ro số 2: PRISMA đòi đếm số bài loại THEO TỪNG LÝ DO."""

    def test_loai_khong_ly_do_bi_tu_choi(self):
        with pytest.raises(ValidationError, match="không dựng được PRISMA"):
            qd("europepmc:MED:1", Quyet.LOAI)

    def test_ly_do_qua_ngan_bi_tu_choi(self):
        with pytest.raises(ValidationError):
            qd("europepmc:MED:1", Quyet.LOAI, ly_do="x")

    def test_giu_khong_can_ly_do(self):
        assert qd("europepmc:MED:1", Quyet.GIU).ly_do == ""

    def test_nghi_ngo_khong_can_ly_do(self):
        """Nghi ngờ là để đẩy phán đoán xuống tầng sau, không phải để giải trình."""
        assert qd("europepmc:MED:1", Quyet.NGHI_NGO).quyet_dinh is Quyet.NGHI_NGO

    def test_loai_co_ly_do_thi_nhan(self):
        assert qd("europepmc:MED:1", Quyet.LOAI, ly_do="nghiên cứu trên động vật")


class TestChiNoiThem:
    def test_ghi_roi_doc_lai_duoc(self, so):
        so.ghi_nhieu([qd("europepmc:MED:1"), qd("europepmc:MED:2")])
        assert len(so.doc().quyet_dinh) == 2

    def test_ghi_lan_hai_khong_de_len_lan_mot(self, so):
        so.ghi(qd("europepmc:MED:1"))
        so.ghi(qd("europepmc:MED:2"))
        assert len(so.doc().quyet_dinh) == 2

    def test_doi_y_thi_dong_sau_thang(self, so):
        so.ghi(qd("europepmc:MED:1", Quyet.GIU))
        so.ghi(qd("europepmc:MED:1", Quyet.LOAI, ly_do="đọc kỹ lại thì ngoài phạm vi"))
        assert so.doc().theo_ma["europepmc:MED:1"].quyet_dinh is Quyet.LOAI

    def test_doi_y_van_giu_lich_su(self, so):
        """Đổi quyết định phải NHÌN THẤY ĐƯỢC, không phải lặng lẽ xảy ra."""
        so.ghi(qd("europepmc:MED:1", Quyet.GIU))
        so.ghi(qd("europepmc:MED:1", Quyet.LOAI, ly_do="đọc kỹ lại thì ngoài phạm vi"))
        kq = so.doc()
        assert len(kq.quyet_dinh) == 2
        assert kq.da_doi_y == {"europepmc:MED:1": 2}

    def test_khong_doi_y_thi_khong_bao(self, so):
        so.ghi_nhieu([qd("europepmc:MED:1"), qd("europepmc:MED:2")])
        assert so.doc().da_doi_y == {}

    def test_so_chua_ton_tai_doc_ra_rong_khong_no(self, so):
        assert so.doc().quyet_dinh == [] and so.thong_ke()["tong_quyet_dinh"] == 0


class TestDongHongKhongBiNuot:
    """Rủi ro số 3: một dòng mất là một bài mất khỏi PRISMA."""

    def test_dong_rac_bi_bao_ra(self, so):
        so.ghi(qd("europepmc:MED:1"))
        with so.duong_dan.open("a", encoding="utf-8") as f:
            f.write("{ đây không phải JSON\n")
        kq = so.doc()
        assert len(kq.quyet_dinh) == 1
        assert len(kq.dong_hong) == 1 and kq.dong_hong[0][0] == 2

    def test_dong_hong_khong_lam_mat_dong_sau_no(self, so):
        """Sập giữa chừng mất tối đa MỘT dòng, không mất cả sổ."""
        so.ghi(qd("europepmc:MED:1"))
        with so.duong_dan.open("a", encoding="utf-8") as f:
            f.write('{"ma": "cut giua chung\n')
        so.ghi(qd("europepmc:MED:2"))
        kq = so.doc()
        assert {q.ma for q in kq.quyet_dinh} == {"europepmc:MED:1", "europepmc:MED:2"}
        assert len(kq.dong_hong) == 1

    def test_dong_trong_khong_tinh_la_hong(self, so):
        so.ghi(qd("europepmc:MED:1"))
        with so.duong_dan.open("a", encoding="utf-8") as f:
            f.write("\n\n")
        assert so.doc().dong_hong == []


class TestChayTiepNhieuBuoi:
    def test_con_lai_bo_ma_da_quyet(self, so):
        so.ghi(qd("europepmc:MED:1"))
        assert so.con_lai(["europepmc:MED:1", "europepmc:MED:2", "europepmc:MED:3"]) == [
            "europepmc:MED:2", "europepmc:MED:3"]

    def test_chua_quyet_gi_thi_con_nguyen(self, so):
        assert len(so.con_lai(["a", "b", "c"])) == 3

    def test_con_lai_giu_dung_thu_tu_kho(self, so):
        so.ghi(qd("europepmc:MED:2"))
        assert so.con_lai(["europepmc:MED:3", "europepmc:MED:2", "europepmc:MED:1"]) == [
            "europepmc:MED:3", "europepmc:MED:1"]


class TestThongKePRISMA:
    def test_dem_theo_quyet_dinh(self, so):
        so.ghi_nhieu([
            qd("europepmc:MED:1", Quyet.GIU),
            qd("europepmc:MED:2", Quyet.LOAI, ly_do="nghiên cứu trên động vật"),
            qd("europepmc:MED:3", Quyet.NGHI_NGO),
        ])
        assert so.thong_ke()["theo_quyet_dinh"] == {"giu": 1, "loai": 1, "nghi_ngo": 1}

    def test_dem_loai_theo_tung_ly_do(self, so):
        so.ghi_nhieu([
            qd("europepmc:MED:1", Quyet.LOAI, ly_do="nghiên cứu trên động vật"),
            qd("europepmc:MED:2", Quyet.LOAI, ly_do="nghiên cứu trên động vật"),
            qd("europepmc:MED:3", Quyet.LOAI, ly_do="không có nhóm đối chứng"),
        ])
        assert so.thong_ke()["loai_theo_ly_do"] == {
            "nghiên cứu trên động vật": 2, "không có nhóm đối chứng": 1}

    def test_dem_theo_nguoi_sang_de_so_nguoi_voi_may(self, so):
        so.ghi_nhieu([
            qd("europepmc:MED:1", nguoi="gun"),
            qd("europepmc:MED:2", nguoi="may:sang-loc@v1"),
        ])
        assert so.thong_ke()["theo_nguoi_sang"] == {"gun": 1, "may:sang-loc@v1": 1}

    def test_doi_y_chi_dem_MOT_lan_o_tong(self, so):
        """Tổng quyết định là số BÀI, không phải số dòng ghi."""
        so.ghi(qd("europepmc:MED:1", Quyet.GIU))
        so.ghi(qd("europepmc:MED:1", Quyet.LOAI, ly_do="đọc kỹ lại thì ngoài phạm vi"))
        tk = so.thong_ke()
        assert tk["tong_quyet_dinh"] == 1 and tk["tong_dong_ghi"] == 2

    def test_bao_ro_dang_tron_nhieu_phien_ban_tieu_chi(self, so):
        """Tiêu chí đổi giữa chừng thì quyết định trước và sau KHÔNG so được."""
        so.ghi(qd("europepmc:MED:1", tc="v1"))
        so.ghi(qd("europepmc:MED:2", tc="v2"))
        assert so.thong_ke()["phien_ban_tieu_chi"] == ["v1", "v2"]


class TestTruongBatBuoc:
    @pytest.mark.parametrize("truong", ["ma", "nguoi_sang", "phien_ban_tieu_chi"])
    def test_truong_rong_bi_tu_choi(self, truong):
        tham_so = dict(ma="a", quyet_dinh=Quyet.GIU, nguoi_sang="gun",
                       phien_ban_tieu_chi="v1", van_tay_kho=VT)
        tham_so[truong] = "   "
        with pytest.raises(ValidationError):
            QuyetDinh(**tham_so)

    def test_co_dau_thoi_gian_tu_dong(self):
        assert qd("europepmc:MED:1").luc is not None


class TestCLIXemSo:
    """CLI là thứ Gun chạy thật, nên nó phải chịu được sổ chưa có và sổ bẩn."""

    @staticmethod
    def _kho(tmp_path, n=3):
        p = tmp_path / "kho.json"
        p.write_text(json.dumps({"ban_ghi": [
            {"source_id": f"europepmc:MED:{i}"} for i in range(1, n + 1)
        ]}), encoding="utf-8")
        return p

    def test_kho_khong_ton_tai_bao_ro(self, tmp_path, capsys):
        from tools.xem_so import main
        assert main([str(tmp_path / "khong-co.json")]) == 2
        assert "quet_that" in capsys.readouterr().out

    def test_chua_co_so_van_chay_duoc(self, tmp_path, capsys):
        """Lần đầu tiên chạy thì chưa có sổ — không được nổ."""
        from tools.xem_so import main
        assert main([str(self._kho(tmp_path))]) == 0
        ra = capsys.readouterr().out
        assert "(chưa có)" in ra and "còn 3 bài chưa ai nhìn" in ra

    def test_quyet_het_va_so_sach_thi_bao_xong(self, tmp_path, capsys):
        from tools.xem_so import main
        kho = self._kho(tmp_path)
        vt, ma = van_tay_tu_tep(kho)
        SoQuyetDinh(kho.with_name("kho_quyet_dinh.jsonl"), vt).ghi_nhieu(
            [qd(m, vt=vt) for m in ma])
        assert main([str(kho)]) == 0
        assert "✓ Đã ra quyết định cho toàn bộ kho, sổ sạch" in capsys.readouterr().out

    def test_quyet_het_nhung_tron_tieu_chi_thi_KHONG_bao_xong(self, tmp_path, capsys):
        """Đủ số lượng mà trộn hai bộ tiêu chí vẫn chưa dựng được PRISMA."""
        from tools.xem_so import main
        kho = self._kho(tmp_path, n=2)
        vt, ma = van_tay_tu_tep(kho)
        SoQuyetDinh(kho.with_name("kho_quyet_dinh.jsonl"), vt).ghi_nhieu([
            qd(ma[0], vt=vt, tc="v1"), qd(ma[1], vt=vt, tc="v2")])
        assert main([str(kho)]) == 0
        ra = capsys.readouterr().out
        assert "TRỘN NHIỀU PHIÊN BẢN TIÊU CHÍ" in ra
        assert "phải xử trước khi dựng PRISMA" in ra

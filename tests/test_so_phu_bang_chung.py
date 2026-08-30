"""Kiểm thử V1 — sổ phủ bằng chứng. Viết TỪ ĐẶC TẢ, trước khi tồn tại mã cài đặt.

VAI: AG-2 (viết kiểm thử). Người viết tệp này KHÔNG được đọc mã cài đặt và
KHÔNG được sửa `tools/**`. Đặc tả: `docs/DAC_TA_V1_SO_PHU.md`.

VÌ SAO TỆP NÀY ĐỎ LÚC MỚI TẠO — đó là kết quả mong đợi, không phải hỏng:

Kiểm thử viết ra TRƯỚC khi có mã thì về mặt vật lý không thể chỉ mô tả lại mã đó.
Đây là rào cản chính chặn chế độ hỏng nguy hiểm nhất của một tác nhân nhanh: viết
mã rồi tự viết kiểm thử cho chính mã ấy, và kiểm thử luôn xanh vì nó chép lại
hành vi thay vì chép lại đặc tả.

PHẠM VI — chỉ LỚP 1 (đơn vị, dữ liệu dựng nhỏ).

Lớp 2 (đối chứng trên dữ liệu AnesthOS thật, khớp N1-N6) CỐ Ý không nằm ở đây:
nó là lệnh nghiệm thu do AG-3 chạy, cần cây dữ liệu AnesthOS có mặt. Nhét nó vào
pytest sẽ khiến bộ kiểm thử đỏ trên mọi máy không có repo kia — biến trạng thái
'thiếu dữ liệu' thành 'mã sai', đúng kiểu lẫn lộn mà cả hệ này dựng lên để chặn.

Lớp 3 (kiểm chéo hai nguồn) không áp dụng cho V1 vì V1 chưa chạm nguồn nào.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _mo_dun():
    """Nạp mô-đun cần kiểm.

    Chưa có -> TRƯỢT kèm thông điệp rõ. KHÔNG dùng skip/xfail: bỏ qua một kiểm
    thử sẽ khiến 'chưa làm' trông giống 'đã qua', và `scripts/gate_m6.sh` cấm.
    """
    try:
        import tools.so_phu_bang_chung as m
        return m
    except ImportError as e:
        pytest.fail(
            f"Chưa có tools/so_phu_bang_chung.py ({e}). "
            "ĐỎ đúng thiết kế: AG-2 viết kiểm thử trước, AG-1 cài đặt sau. "
            "Đặc tả: docs/DAC_TA_V1_SO_PHU.md"
        )


def _dung_kho(tmp: Path, tep: dict[str, object]) -> Path:
    """Dựng một cây dữ liệu giả để kiểm quy tắc duyệt."""
    d = tmp / "data"
    d.mkdir(exist_ok=True)
    for ten, noi_dung in tep.items():
        (d / ten).write_text(json.dumps(noi_dung, ensure_ascii=False), encoding="utf-8")
    return d


# ---------------------------------------------------------------- §2.1 duyệt cây

class TestQuyTacDuyetCay:
    """Đặc tả §2.1. Toàn bộ tiêu chuẩn nghiệm thu treo trên quy tắc này."""

    def test_bo_qua_khoa_bat_dau_bang_gach_duoi(self, tmp_path):
        m = _mo_dun()
        d = _dung_kho(tmp_path, {"a.json": {"_metadata": {"x": 1, "y": 2}, "dose": "5 mg"}})
        assert len(m.quet_khang_dinh(d)) == 1

    def test_danh_sach_KE_THUA_khoa_cua_tu_dien_cha(self, tmp_path):
        """Ví dụ chốt trong đặc tả: {"routes": ["IV","PO"]} -> 2 lá, cùng khoá.

        Đây là chỗ dễ cài sai nhất: coi phần tử danh sách là vô danh sẽ làm mất
        khoá, mà mất khoá thì không xếp được mức rủi ro.
        """
        m = _mo_dun()
        d = _dung_kho(tmp_path, {"a.json": {"routes": ["IV", "PO"]}})
        ds = m.quet_khang_dinh(d)
        assert len(ds) == 2
        assert {h.khoa for h in ds} == {"routes"}

    def test_moi_kieu_vo_huong_deu_tinh_la_mot_la(self, tmp_path):
        m = _mo_dun()
        d = _dung_kho(tmp_path, {"a.json": {"p": "chuoi", "q": 5, "r": 1.5, "s": True, "t": None}})
        assert len(m.quet_khang_dinh(d)) == 5

    def test_tu_dien_long_nhau_van_duyet_het(self, tmp_path):
        m = _mo_dun()
        d = _dung_kho(tmp_path, {"a.json": {"x": {"y": {"dose": "1 mg", "max": "2 mg"}}}})
        assert len(m.quet_khang_dinh(d)) == 2

    def test_rong_thi_khong_sinh_la_nao(self, tmp_path):
        m = _mo_dun()
        d = _dung_kho(tmp_path, {"a.json": {"x": {}, "y": []}})
        assert m.quet_khang_dinh(d) == []


# ------------------------------------------------------------ §2.2 loại khỏi phạm vi

class TestLoaiTepKhaiXuatXu:
    def test_provenance_manifest_KHONG_tinh_la_khang_dinh(self, tmp_path):
        """Nó là siêu dữ liệu VỀ nguồn, không phải điều app nói với bác sĩ.

        Đếm nhầm nó chính là lỗi đã lọt vào bản kế hoạch được duyệt (137 lá).
        """
        m = _mo_dun()
        d = _dung_kho(tmp_path, {
            "provenance_manifest.json": {"files": {"a.json": {"source": "X", "citation": "Y"}}},
            "drugs.json": {"dose": "5 mg"},
        })
        ds = m.quet_khang_dinh(d)
        assert len(ds) == 1 and ds[0].khoa == "dose"


# ------------------------------------------------------------------ §2.3 xếp hạng

class TestXepHangRuiRo:
    @staticmethod
    def _rui_ro(tmp_path, m, khoa):
        d = _dung_kho(tmp_path, {"a.json": {khoa: "gia tri nao do"}})
        ds = m.quet_khang_dinh(d)
        return ds[0].muc_rui_ro if ds else None

    @pytest.mark.parametrize("khoa", [
        "critical", "dose", "smartDose", "max", "periop", "redFlags",
        "route", "routes", "weightBasis", "concentrations", "withEpi", "plain",
        "timeToDeath",
    ])
    def test_uu_tien_1_sai_thi_chet_nguoi(self, tmp_path, khoa):
        assert self._rui_ro(tmp_path, _mo_dun(), khoa) == 1

    @pytest.mark.parametrize("khoa", [
        "preferred", "cautions", "contraindications", "interactions",
        "timing", "conditional", "severity", "bleedingRisk",
    ])
    def test_uu_tien_2_hai_nang(self, tmp_path, khoa):
        assert self._rui_ro(tmp_path, _mo_dun(), khoa) == 2

    @pytest.mark.parametrize("khoa", ["name", "id", "aliases", "category",
                                      "label", "unit", "icon", "color", "textColor"])
    def test_nhan_va_trinh_bay_KHONG_can_bang_chung(self, tmp_path, khoa):
        """Nhãn phải được tách hẳn khỏi khẳng định lâm sàng, không phải xếp ưu tiên thấp."""
        m = _mo_dun()
        d = _dung_kho(tmp_path, {"a.json": {khoa: "gia tri", "dose": "5 mg"}})
        ds = m.quet_khang_dinh(d)
        assert [h.khoa for h in ds] == ["dose"]

    def test_khoa_la_thi_mac_dinh_uu_tien_3_KHONG_phai_1(self, tmp_path):
        """Đặc tả §2.3. Bộ dữ liệu có 292 khoá hiếm; mặc định cao sẽ thổi phồng
        nhóm nguy hiểm bằng nhiễu và làm hỏng chính công dụng của xếp hạng."""
        assert self._rui_ro(tmp_path, _mo_dun(), "mot_khoa_chua_tung_gap") == 3

    @pytest.mark.parametrize("khoa,muc", [("timing", 2), ("conditional", 2),
                                          ("smartDose", 1), ("weightBasis", 1),
                                          ("max", 1), ("timeToDeath", 1)])
    def test_khoa_gay_tranh_cai_xep_theo_mau_gia_tri_that(self, tmp_path, khoa, muc):
        """Đặc tả §2.4 — xếp bằng mẫu giá trị thật, không bằng suy đoán từ tên khoá.

        `timing` nghe như thời điểm dùng thuốc nhưng giá trị thật là "after
        delivery" / "on indication" — thời điểm XÉT NGHIỆM. `smartDose` nghe lạ
        nhưng là LIỀU. Suy đoán từ tên sẽ xếp ngược cả hai.
        """
        assert self._rui_ro(tmp_path, _mo_dun(), khoa) == muc


# ----------------------------------------------------------------- §3 ràng buộc

class TestRangBuocBatBien:
    def test_R1_muc_phu_SUY_RA_khong_gan_tay(self, tmp_path):
        """Trường tự khai độ tin cậy là chế độ hỏng đã gặp ở đợt kiểm toán trước."""
        m = _mo_dun()
        h = m.HoSoBangChung(duong_dan="a.json#x", khoa="dose",
                            khang_dinh="5 mg", muc_rui_ro=1)
        with pytest.raises((AttributeError, ValueError, TypeError)):
            h.muc_phu = m.MucPhu.CO_CHUOI_DAY_DU

    def test_ho_so_moi_la_KHONG_CO(self, tmp_path):
        m = _mo_dun()
        h = m.HoSoBangChung(duong_dan="a.json#x", khoa="dose",
                            khang_dinh="5 mg", muc_rui_ro=1)
        assert h.muc_phu is m.MucPhu.KHONG_CO

    def test_chi_co_nguon_cap_tep_thi_la_CHI_CO_NGUON(self):
        m = _mo_dun()
        h = m.HoSoBangChung(duong_dan="a.json#x", khoa="dose", khang_dinh="5 mg",
                            muc_rui_ro=1, nguon_khai="ASRA 2018 4th ed")
        assert h.muc_phu is m.MucPhu.CHI_CO_NGUON

    def test_R2_chuoi_day_du_doi_DU_CA_BA_manh(self):
        m = _mo_dun()
        h = m.HoSoBangChung(
            duong_dan="a.json#x", khoa="dose", khang_dinh="5 mg", muc_rui_ro=1,
            nguon_khai="ASRA 2018 4th ed",
            doi_chieu_nguoc=m.TrangThai.DAT,
            bo_ba=[("5 mg", "dựa trên", "pubmed:26095867")],
            bac_chung_cu=3,
        )
        assert h.muc_phu is m.MucPhu.CO_CHUOI_DAY_DU

    @pytest.mark.parametrize("thieu", ["doi_chieu_nguoc", "bo_ba", "bac_chung_cu"])
    def test_R2_thieu_MOT_manh_thi_CHUA_day_du(self, thieu):
        """Thiếu một mắt là chưa đầy đủ. Nới chỗ này là mở đường cho tự khai."""
        m = _mo_dun()
        day_du = dict(
            duong_dan="a.json#x", khoa="dose", khang_dinh="5 mg", muc_rui_ro=1,
            nguon_khai="ASRA 2018 4th ed",
            doi_chieu_nguoc=m.TrangThai.DAT,
            bo_ba=[("5 mg", "dựa trên", "pubmed:26095867")],
            bac_chung_cu=3,
        )
        day_du[thieu] = {"doi_chieu_nguoc": m.TrangThai.KHONG_KIEM_DUOC,
                         "bo_ba": [], "bac_chung_cu": None}[thieu]
        assert m.HoSoBangChung(**day_du).muc_phu is not m.MucPhu.CO_CHUOI_DAY_DU

    def test_R3_duong_dan_duy_nhat_trong_toan_bo_ket_qua(self, tmp_path):
        """Trùng đường dẫn thì không gắn bằng chứng vào đâu được."""
        m = _mo_dun()
        d = _dung_kho(tmp_path, {
            "a.json": {"x": {"dose": "1 mg"}, "y": {"dose": "2 mg"}},
            "b.json": [{"dose": "3 mg"}, {"dose": "4 mg"}],
        })
        ds = m.quet_khang_dinh(d)
        duong = [h.duong_dan for h in ds]
        assert len(duong) == len(set(duong)) == 4

    def test_duong_dan_neu_ro_ten_tep(self, tmp_path):
        m = _mo_dun()
        d = _dung_kho(tmp_path, {"drugs.json": {"propofol": {"max": "2"}}})
        assert m.quet_khang_dinh(d)[0].duong_dan.startswith("drugs.json#")


class TestKhongChamMangKhongGhiDuLieu:
    """R4 + R5 — kiểm bằng CẤU TRÚC mã nguồn, vì hành vi này khó bắt lúc chạy."""

    @staticmethod
    def _nguon() -> str:
        p = Path(__file__).resolve().parent.parent / "tools" / "so_phu_bang_chung.py"
        if not p.exists():
            pytest.fail("Chưa có tools/so_phu_bang_chung.py — ĐỎ đúng thiết kế.")
        return p.read_text(encoding="utf-8")

    @pytest.mark.parametrize("cam", ["httpx", "requests", "urllib.request", "socket"])
    def test_R5_khong_nhap_thu_vien_mang(self, cam):
        """V1 phải chạy được khi mất mạng."""
        assert cam not in self._nguon()

    @pytest.mark.parametrize("cam", ["write_text", "unlink", "rmtree"])
    def test_R4_khong_ghi_de_len_du_lieu_AnesthOS(self, cam):
        """Chỉ đọc. Repo khác, quyết định khác."""
        assert cam not in self._nguon()


class TestBaoCao:
    def test_bao_cao_neu_ro_so_khang_dinh_KHONG_CO_gi_chong_lung(self, tmp_path):
        """Công dụng chính của V1: làm cho sự THIẾU VẮNG nhìn thấy được."""
        m = _mo_dun()
        d = _dung_kho(tmp_path, {"a.json": {"dose": "5 mg", "max": "2"}})
        ra = m.bao_cao_phu(m.quet_khang_dinh(d))
        assert "2" in ra and ("không có" in ra.lower() or "chưa" in ra.lower())

    def test_bao_cao_tach_rieng_tung_muc_rui_ro(self, tmp_path):
        """Gộp ba mức thành một số làm mất chính thứ dùng để xếp thứ tự công việc."""
        m = _mo_dun()
        d = _dung_kho(tmp_path, {"a.json": {"dose": "5 mg", "preferred": "X", "ghi_chu_la": "Y"}})
        ra = m.bao_cao_phu(m.quet_khang_dinh(d))
        assert ra.count("1") and ra.count("2") and ra.count("3")

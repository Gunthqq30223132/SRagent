"""Kiểm thử A0 — biểu mẫu bằng chứng cấp dòng. Viết TỪ ĐẶC TẢ, trước khi có mã.

VAI: AG-2 (viết kiểm thử). Người viết tệp này KHÔNG đọc mã cài đặt và KHÔNG sửa
`tools/**`. Đặc tả: `docs/DAC_TA_A0.md`.

VÌ SAO TỆP NÀY ĐỎ LÚC MỚI TẠO — đó là kết quả mong đợi, không phải hỏng. Kiểm thử
viết trước khi có mã thì về mặt vật lý không thể chỉ mô tả lại mã đó.

PHẠM VI — chỉ LỚP 1 (đơn vị, mẫu dựng tay).

Lớp 2 (đối chứng trên dữ liệu AnesthOS thật, khớp A0.Đ1–Đ8) CỐ Ý không nằm ở đây:
nó là lệnh nghiệm thu do AG-3 chạy, cần cây dữ liệu AnesthOS có mặt. Nhét vào
pytest sẽ khiến bộ kiểm thử đỏ trên mọi máy không có kho kia — biến 'thiếu dữ
liệu' thành 'mã sai', đúng kiểu lẫn lộn cả hệ này dựng lên để chặn.

Ký hiệu: xem `docs/QUY_UOC_KY_HIEU.md`. R-series dưới đây là A0.R1–A0.R6.
"""

from __future__ import annotations

from decimal import Decimal

import pytest


# Mọi tên A0 phải có mặt thì một kiểm thử trong tệp này mới có nghĩa.
_TEN_A0 = ("ToaDoNguon", "DongThuan", "LyDoKhongKiemDuoc", "SoNhapNhang",
           "the_so", "van_tay_bo_ba")


def _mo_dun():
    """Nạp mô-đun cần kiểm, và ĐÒI mọi tên A0 phải tồn tại.

    Vì sao đòi cả tên, không chỉ đòi nạp được: mô-đun đã tồn tại từ V1. Nếu chỉ
    kiểm `import` thì một loạt kiểm thử A0 sẽ XANH ngay khi chưa có dòng mã A0
    nào — xanh vì `pytest.raises` bắt trúng `AttributeError`, vì pydantic ném
    'không có trường này', hoặc vì `inspect.getsource()` đang đọc mã V1. Xanh vì
    những lý do đó KHÔNG chứng minh được gì, và tệ hơn: chúng xanh trước khi có
    mã và vẫn xanh sau khi có mã, tức KHÔNG BAO GIỜ ĐỎ.

    Một kiểm thử chưa từng đỏ thì không có bằng chứng nào nói nó đang kiểm cái gì.

    KHÔNG dùng skip/xfail: bỏ qua khiến 'chưa làm' trông giống 'đã qua', và
    `scripts/gate_m6.sh` cấm.
    """
    try:
        import tools.so_phu_bang_chung as m
    except ImportError as e:  # pragma: no cover
        pytest.fail(f"Chưa có tools/so_phu_bang_chung.py ({e}).")
    thieu = [t for t in _TEN_A0 if not hasattr(m, t)]
    if thieu or not hasattr(m.MucPhu, "DA_DOI_CHIEU"):
        pytest.fail(
            f"Mô-đun chưa có thành phần A0: {thieu or ['MucPhu.DA_DOI_CHIEU']}.\n"
            "Đây là trạng thái xuất phát ĐÚNG: kiểm thử có trước mã.\n"
            "Việc của AG-1: cài theo docs/DAC_TA_A0.md cho tới khi tệp này xanh."
        )
    return m


def _ho_so(m, **thay_doi):
    """Hồ sơ tối thiểu hợp lệ; `thay_doi` ghi đè từng trường."""
    goc = dict(duong_dan="a.json#x", khoa="dose", khang_dinh="5 mg", muc_rui_ro=1)
    goc.update(thay_doi)
    return m.HoSoBangChung(**goc)


def _toa_do(m, trich, ma="pmid:1", loai="huong_dan", vi_tri="bảng 3"):
    return m.ToaDoNguon(ma_tai_lieu=ma, loai_tai_lieu=loai,
                        vi_tri=vi_tri, trich_nguyen_van=trich)


def _khong_co_so_truoc(ra: str, duong_dan: str) -> bool:
    """Luật L7: không một CHỮ SỐ nào được in ra trước đường dẫn nguồn dữ liệu.

    Chặt có chủ đích. Luật này sinh ra từ một sự cố thật: một lượt nghiệm thu
    chạy nhầm thư mục, cả sáu số thô đều khớp, nhưng kết luận chính bị đảo ngược
    và không gì trong báo cáo cho thấy điều đó. Nới ra để cho phép "số vô hại"
    đứng trước là mở lại đúng khe đó.
    """
    if duong_dan not in ra:
        return False
    return not any(c.isdigit() for c in ra[: ra.index(duong_dan)])


# ------------------------------------------------------------- §2.1 toạ độ nguồn

class TestToaDoNguon:
    def test_dung_duoc_khi_du_bon_truong(self):
        m = _mo_dun()
        t = _toa_do(m, "không quá 4.5 mg/kg")
        assert t.trich_nguyen_van == "không quá 4.5 mg/kg"

    @pytest.mark.parametrize("trich", ["", "   ", "\n\t "])
    def test_trich_dan_rong_thi_nem_loi_LUC_DUNG(self, trich):
        """Toạ độ không có trích dẫn thì không phải toạ độ — chặn ngay lúc dựng.

        Bắt ValueError CỤ THỂ, không bắt Exception trần: `pytest.raises(Exception)`
        cũng bắt trúng `AttributeError: module has no attribute 'ToaDoNguon'`, nên
        kiểm thử vẫn xanh cả khi AG-1 chưa cài gì. Pydantic gói lỗi kiểm định
        thành ValidationError, vốn là con của ValueError.
        """
        m = _mo_dun()
        with pytest.raises(ValueError):
            _toa_do(m, trich)


# ------------------------------------------------------------ §2.2 bóc thẻ số

class TestTheSo:
    def test_so_thap_phan_don_gian(self):
        m = _mo_dun()
        assert m.the_so("4.5") == {Decimal("4.5")}

    def test_so_0_thua_KHONG_tao_gia_tri_khac(self):
        """4.50 và 4.5 là MỘT giá trị — so Decimal, không so chuỗi."""
        m = _mo_dun()
        assert m.the_so("4.50") == m.the_so("4.5")

    def test_nhieu_so_trong_mot_chuoi(self):
        m = _mo_dun()
        assert m.the_so("5-10 mg PO once daily") == {Decimal("5"), Decimal("10")}

    @pytest.mark.parametrize("gach", ["–", "—", "−"])
    def test_moi_loai_gach_noi_deu_duoc_chuan_hoa(self, gach):
        m = _mo_dun()
        assert m.the_so(f"5{gach}10 mg") == {Decimal("5"), Decimal("10")}

    def test_dau_phay_1_2_chu_so_la_DAU_THAP_PHAN(self):
        m = _mo_dun()
        assert m.the_so("4,5 mg/kg") == {Decimal("4.5")}

    def test_khong_co_so_thi_tap_RONG(self):
        m = _mo_dun()
        assert m.the_so("IV") == set()

    def test_tra_ve_TAP_HOP_khong_phai_danh_sach(self):
        m = _mo_dun()
        assert isinstance(m.the_so("5 mg và 5 mL"), set)
        assert m.the_so("5 mg và 5 mL") == {Decimal("5")}


class TestSoNhapNhang:
    """Bước 4 của §2.2: thà dừng còn hơn đoán."""

    def test_phay_dung_3_chu_so_thi_NEM_LOI(self):
        m = _mo_dun()
        with pytest.raises(m.SoNhapNhang):
            m.the_so("1,500 mg")

    def test_ca_CARVEDILOL_that_khong_duoc_doc_thanh_3125(self):
        """Liều thật là 3,125 mg (phẩy = thập phân). Đoán 'phẩy+3 số = hàng nghìn'
        sẽ ra 3125 mg — sai 1000 lần trên một chẹn beta không chọn lọc, và sai IM
        LẶNG vì con số vẫn 'khớp'."""
        m = _mo_dun()
        with pytest.raises(m.SoNhapNhang):
            m.the_so("3,125–25 mg PO BD")

    def test_ty_le_pha_loang_adrenaline_cung_la_nhap_nhang(self):
        m = _mo_dun()
        with pytest.raises(m.SoNhapNhang):
            m.the_so("1:10,000 = 100 mcg/mL")

    def test_SoNhapNhang_la_ValueError(self):
        """Chỗ gọi cũ bắt ValueError vẫn không lọt lỗi này ra ngoài."""
        m = _mo_dun()
        assert issubclass(m.SoNhapNhang, ValueError)

    def test_phay_4_chu_so_tro_len_KHONG_nhap_nhang(self):
        """Chỉ đúng 3 chữ số mới nhập nhằng."""
        m = _mo_dun()
        m.the_so("1,5000 mg")  # không được ném


# --------------------------------------------------- §2.2 nội dung truy được

class TestNoiDungTruyDuoc:
    def test_chua_co_toa_do_thi_KHONG_KIEM_DUOC(self):
        m = _mo_dun()
        h = _ho_so(m, khang_dinh="4.5")
        assert h.noi_dung_truy_duoc is m.TrangThai.KHONG_KIEM_DUOC
        assert h.ly_do_khong_kiem is m.LyDoKhongKiemDuoc.CHUA_CO_TOA_DO

    def test_so_co_trong_trich_dan_thi_DAT(self):
        m = _mo_dun()
        h = _ho_so(m, khang_dinh="4.5",
                   nguon=[_toa_do(m, "...not to exceed 4.5 mg/kg...")])
        assert h.noi_dung_truy_duoc is m.TrangThai.DAT
        assert h.ly_do_khong_kiem is None

    def test_so_0_thua_van_DAT(self):
        m = _mo_dun()
        h = _ho_so(m, khang_dinh="4.50",
                   nguon=[_toa_do(m, "maximum 4.5 mg/kg")])
        assert h.noi_dung_truy_duoc is m.TrangThai.DAT

    def test_KHONG_duoc_khop_chuoi_con(self):
        """'5' không được khớp vào '500'. Khớp chuỗi con cho ĐẠT sai."""
        m = _mo_dun()
        h = _ho_so(m, khang_dinh="5",
                   nguon=[_toa_do(m, "total 500 mg over 24 hours")])
        assert h.noi_dung_truy_duoc is m.TrangThai.TRUOT

    def test_thieu_mot_trong_nhieu_so_thi_TRUOT(self):
        m = _mo_dun()
        h = _ho_so(m, khang_dinh="5-10 mg",
                   nguon=[_toa_do(m, "starting at 5 mg")])
        assert h.noi_dung_truy_duoc is m.TrangThai.TRUOT

    def test_khang_dinh_thuan_chu_thi_KHONG_KIEM_DUOC(self):
        m = _mo_dun()
        h = _ho_so(m, khang_dinh="IV",
                   nguon=[_toa_do(m, "administer intravenously")])
        assert h.noi_dung_truy_duoc is m.TrangThai.KHONG_KIEM_DUOC
        assert h.ly_do_khong_kiem is m.LyDoKhongKiemDuoc.KHANG_DINH_KHONG_SO

    def test_so_nhap_nhang_thi_KHONG_KIEM_DUOC_khong_vo(self):
        """Ngoại lệ phải bị bắt ở đây, không được nổ ra ngoài."""
        m = _mo_dun()
        h = _ho_so(m, khang_dinh="1,500 mg",
                   nguon=[_toa_do(m, "up to 1,500 mg daily")])
        assert h.noi_dung_truy_duoc is m.TrangThai.KHONG_KIEM_DUOC
        assert h.ly_do_khong_kiem is m.LyDoKhongKiemDuoc.SO_NHAP_NHANG

    def test_trich_dan_nhap_nhang_cung_KHONG_KIEM_DUOC(self):
        """Nhập nhằng ở phía trích dẫn cũng không được lặng lẽ cho TRƯỢT."""
        m = _mo_dun()
        h = _ho_so(m, khang_dinh="25",
                   nguon=[_toa_do(m, "3,125–25 mg PO BD")])
        assert h.noi_dung_truy_duoc is m.TrangThai.KHONG_KIEM_DUOC
        assert h.ly_do_khong_kiem is m.LyDoKhongKiemDuoc.SO_NHAP_NHANG


# ------------------------------------------------------------ §2.3 vân tay bộ ba

class TestVanTayBoBa:
    def test_dinh_dang_sha256_16_hex(self):
        m = _mo_dun()
        v = m.van_tay_bo_ba("a", "b", "c")
        assert v.startswith("sha256:")
        hex16 = v.split(":", 1)[1]
        assert len(hex16) == 16
        assert all(c in "0123456789abcdef" for c in hex16)

    def test_tat_dinh_cung_dau_vao_cung_ket_qua(self):
        m = _mo_dun()
        assert m.van_tay_bo_ba("a", "b", "c") == m.van_tay_bo_ba("a", "b", "c")

    @pytest.mark.parametrize("vi_tri", [0, 1, 2])
    def test_doi_BAT_KY_thanh_phan_nao_cung_doi_van_tay(self, vi_tri):
        m = _mo_dun()
        goc = ["a", "b", "c"]
        khac = list(goc)
        khac[vi_tri] = "KHAC"
        assert m.van_tay_bo_ba(*goc) != m.van_tay_bo_ba(*khac)

    def test_khong_lan_thanh_phan_a_b_c_voi_ab_c(self):
        """Ghép chuỗi ẩu thì ('ab','c','d') và ('a','bc','d') ra cùng vân tay."""
        m = _mo_dun()
        assert m.van_tay_bo_ba("ab", "c", "d") != m.van_tay_bo_ba("a", "bc", "d")


class TestVanTayConHieuLuc:
    def test_chua_tham_dinh_thi_KHONG_hieu_luc(self):
        m = _mo_dun()
        assert _ho_so(m).van_tay_con_hieu_luc is False

    def test_thieu_mot_trong_hai_thi_KHONG_hieu_luc(self):
        m = _mo_dun()
        assert _ho_so(m, van_tay_tham_dinh="sha256:aaaaaaaaaaaaaaaa").van_tay_con_hieu_luc is False
        assert _ho_so(m, van_tay_hien_tai="sha256:aaaaaaaaaaaaaaaa").van_tay_con_hieu_luc is False

    def test_bang_nhau_thi_CON_hieu_luc(self):
        m = _mo_dun()
        v = "sha256:aaaaaaaaaaaaaaaa"
        assert _ho_so(m, van_tay_tham_dinh=v, van_tay_hien_tai=v).van_tay_con_hieu_luc is True

    def test_khac_nhau_thi_HET_hieu_luc(self):
        """Nguồn đổi hoặc mã rút đổi → chữ ký cũ thôi bảo chứng."""
        m = _mo_dun()
        h = _ho_so(m, van_tay_tham_dinh="sha256:aaaaaaaaaaaaaaaa",
                   van_tay_hien_tai="sha256:bbbbbbbbbbbbbbbb")
        assert h.van_tay_con_hieu_luc is False


# ------------------------------------------------------- §2.4 bốn trạng thái đồng thuận

class TestDongThuan:
    def test_khong_nguon_nao_thi_MOT_NGUON(self):
        m = _mo_dun()
        assert _ho_so(m).dong_thuan is m.DongThuan.MOT_NGUON

    def test_dung_mot_nguon_thi_MOT_NGUON(self):
        m = _mo_dun()
        h = _ho_so(m, nguon=[_toa_do(m, "4.5 mg/kg", ma="pmid:1")],
                   pha_he={"pmid:1": ["pmid:1978"]})
        assert h.dong_thuan is m.DongThuan.MOT_NGUON

    def test_hai_nguon_cung_bai_goc_thi_CHUNG_TO_TIEN(self):
        m = _mo_dun()
        h = _ho_so(m,
                   nguon=[_toa_do(m, "4.5", ma="pmid:1"), _toa_do(m, "4.5", ma="pmid:2")],
                   pha_he={"pmid:1": ["pmid:12345"], "pmid:2": ["pmid:12345"]})
        assert h.dong_thuan is m.DongThuan.CHUNG_TO_TIEN

    def test_hai_nguon_goc_khac_nhau_thi_DOC_LAP(self):
        m = _mo_dun()
        h = _ho_so(m,
                   nguon=[_toa_do(m, "4.5", ma="pmid:1"), _toa_do(m, "4.5", ma="pmid:2")],
                   pha_he={"pmid:1": ["pmid:111"], "pmid:2": ["pmid:222"]})
        assert h.dong_thuan is m.DongThuan.DOC_LAP

    def test_giao_nhau_MOT_PHAN_van_la_CHUNG_TO_TIEN(self):
        """Chồng lấn một bài cũng đủ gom về một cụm."""
        m = _mo_dun()
        h = _ho_so(m,
                   nguon=[_toa_do(m, "4.5", ma="pmid:1"), _toa_do(m, "4.5", ma="pmid:2")],
                   pha_he={"pmid:1": ["pmid:111", "pmid:999"],
                           "pmid:2": ["pmid:222", "pmid:999"]})
        assert h.dong_thuan is m.DongThuan.CHUNG_TO_TIEN

    def test_gom_cum_BAC_CAU_ba_nguon_hai_cum(self):
        """A∩B=∅, B∩C≠∅, A∩C=∅ → hai cụm {A} và {B,C} → DOC_LAP."""
        m = _mo_dun()
        h = _ho_so(m,
                   nguon=[_toa_do(m, "4.5", ma="A"), _toa_do(m, "4.5", ma="B"),
                          _toa_do(m, "4.5", ma="C")],
                   pha_he={"A": ["p1"], "B": ["p2"], "C": ["p2", "p3"]})
        assert h.dong_thuan is m.DongThuan.DOC_LAP

    def test_gom_cum_BAC_CAU_ba_nguon_MOT_cum(self):
        """A-B nối qua B-C: cả ba về một cụm dù A∩C=∅."""
        m = _mo_dun()
        h = _ho_so(m,
                   nguon=[_toa_do(m, "4.5", ma="A"), _toa_do(m, "4.5", ma="B"),
                          _toa_do(m, "4.5", ma="C")],
                   pha_he={"A": ["p1"], "B": ["p1", "p2"], "C": ["p2"]})
        assert h.dong_thuan is m.DongThuan.CHUNG_TO_TIEN


class TestA0_R3_ThuTuUuTien:
    """A0.R3 — bước 'không đo được' phải chạy TRƯỚC bước 'độc lập'.

    Đảo thứ tự hai bước này là bẫy đồng thuận ảo quay lại, lần này núp trong mã.
    """

    def test_thieu_pha_he_thi_KHONG_DO_DUOC_chu_KHONG_phai_DOC_LAP(self):
        """Ca then chốt: một nguồn không khai phả hệ, nguồn kia khai gốc khác.
        Nhìn qua tưởng độc lập — nhưng không đo được thì không được kết luận."""
        m = _mo_dun()
        h = _ho_so(m,
                   nguon=[_toa_do(m, "4.5", ma="pmid:1"), _toa_do(m, "nhãn FDA", ma="spl:9")],
                   pha_he={"pmid:1": ["pmid:111"]})  # spl:9 không khai
        assert h.dong_thuan is m.DongThuan.KHONG_DO_DUOC_DOC_LAP

    def test_pha_he_RONG_cung_la_KHONG_DO_DUOC(self):
        m = _mo_dun()
        h = _ho_so(m,
                   nguon=[_toa_do(m, "4.5", ma="pmid:1"), _toa_do(m, "nhãn", ma="spl:9")],
                   pha_he={"pmid:1": ["pmid:111"], "spl:9": []})
        assert h.dong_thuan is m.DongThuan.KHONG_DO_DUOC_DOC_LAP

    def test_khong_nguon_nao_khai_pha_he_van_la_KHONG_DO_DUOC(self):
        m = _mo_dun()
        h = _ho_so(m, nguon=[_toa_do(m, "4.5", ma="a"), _toa_do(m, "4.5", ma="b")],
                   pha_he={})
        assert h.dong_thuan is m.DongThuan.KHONG_DO_DUOC_DOC_LAP

    def test_CA_PHAN_BIET_hai_nguon_chung_goc_cong_mot_nguon_KHONG_khai(self):
        """Ca DUY NHẤT phơi được việc đảo thứ tự bước 2 và bước 3.

        Ba nguồn: A và B cùng dẫn p1, C không khai phả hệ.

            đúng thứ tự (bước 2 trước)  → KHONG_DO_DUOC_DOC_LAP
            đảo thứ tự (gom cụm trước)  → CHUNG_TO_TIEN

        Các ca R3 khác đều chỉ có MỘT nguồn khai phả hệ, nên gom cụm ra đúng một
        cụm từ một nguồn — hai cách cài cùng chỉ về một đáp án, và ca đó không
        phân biệt được gì. Thiếu ca này thì bẫy đồng thuận ảo quay lại được, lần
        này núp trong mã.
        """
        m = _mo_dun()
        h = _ho_so(m,
                   nguon=[_toa_do(m, "4.5", ma="A"), _toa_do(m, "4.5", ma="B"),
                          _toa_do(m, "nhãn FDA", ma="C")],
                   pha_he={"A": ["p1"], "B": ["p1"]})  # C không khai
        assert h.dong_thuan is m.DongThuan.KHONG_DO_DUOC_DOC_LAP

    def test_CA_PHAN_BIET_hai_nguon_goc_khac_cong_mot_nguon_KHONG_khai(self):
        """Biến thể: A và B gốc KHÁC nhau, C không khai.
        Đảo thứ tự sẽ ra DOC_LAP. Đúng thứ tự vẫn phải là KHONG_DO_DUOC."""
        m = _mo_dun()
        h = _ho_so(m,
                   nguon=[_toa_do(m, "4.5", ma="A"), _toa_do(m, "4.5", ma="B"),
                          _toa_do(m, "nhãn FDA", ma="C")],
                   pha_he={"A": ["p1"], "B": ["p2"]})
        assert h.dong_thuan is m.DongThuan.KHONG_DO_DUOC_DOC_LAP


# ------------------------------------------------------------- §2.5 thang mức phủ

def _da_doi_chieu(m, **thay_doi):
    """Hồ sơ đủ ba mắt của bậc DA_DOI_CHIEU."""
    v = "sha256:aaaaaaaaaaaaaaaa"
    goc = dict(khang_dinh="4.5", nguon_khai="ASRA 2018",
               nguon=[_toa_do(m, "not to exceed 4.5 mg/kg")],
               van_tay_tham_dinh=v, van_tay_hien_tai=v)
    goc.update(thay_doi)
    return _ho_so(m, **goc)


class TestMucPhu:
    def test_ho_so_tran_la_KHONG_CO(self):
        m = _mo_dun()
        assert _ho_so(m).muc_phu is m.MucPhu.KHONG_CO

    def test_chi_co_nguon_cap_tep_thi_NGUON_CAP_TEP(self):
        m = _mo_dun()
        assert _ho_so(m, nguon_khai="ASRA 2018").muc_phu is m.MucPhu.NGUON_CAP_TEP

    def test_du_ba_mat_thi_DA_DOI_CHIEU(self):
        m = _mo_dun()
        assert _da_doi_chieu(m).muc_phu is m.MucPhu.DA_DOI_CHIEU

    def test_bac_DA_DOI_CHIEU_ton_tai_trong_thang(self):
        """Thang phải có đủ 4 bậc — 3 bậc là thang đã mất sức phân biệt."""
        m = _mo_dun()
        assert {x.name for x in m.MucPhu} == {
            "KHONG_CO", "NGUON_CAP_TEP", "DA_DOI_CHIEU", "CO_CHUOI_DAY_DU"}


class TestA0_R2_DaDoiChieuDoiDuCaBa:
    @pytest.mark.parametrize("thieu,gia_tri", [
        ("nguon", []),                                  # thiếu toạ độ
        ("khang_dinh", "IV"),                           # nội dung không ĐẠT
        ("van_tay_hien_tai", "sha256:bbbbbbbbbbbbbbbb"),  # vân tay hết hiệu lực
    ])
    def test_thieu_MOT_mat_thi_TUT_ve_NGUON_CAP_TEP(self, thieu, gia_tri):
        """Thiếu một mắt là chưa đối chiếu. Nới chỗ này là mở đường cho tự khai.

        Khẳng định BẬC CHÍNH XÁC, không dùng `is not`: `is not DA_DOI_CHIEU` vẫn
        xanh khi cài đặt trả một bậc CAO HƠN. Một cổng chống tự khai mà kiểm bằng
        `is not` thì không chặn được đúng thứ nó sinh ra để chặn.
        """
        m = _mo_dun()
        h = _da_doi_chieu(m, **{thieu: gia_tri})
        assert h.muc_phu is m.MucPhu.NGUON_CAP_TEP

    def test_so_khong_khop_trich_dan_thi_TUT_ve_NGUON_CAP_TEP(self):
        m = _mo_dun()
        h = _da_doi_chieu(m, khang_dinh="9.9")
        assert h.noi_dung_truy_duoc is m.TrangThai.TRUOT
        assert h.muc_phu is m.MucPhu.NGUON_CAP_TEP


class TestA0_R4_VanTayHetHanThiTutHang:
    def test_van_tay_lech_thi_KHONG_cao_hon_NGUON_CAP_TEP(self):
        """Đủ mọi điều kiện khác, nhưng nguồn đã đổi → tụt về nguồn cấp tệp.
        Tụt hạng là thuộc tính TÍNH RA, không phải tiến trình chạy nền."""
        m = _mo_dun()
        h = _da_doi_chieu(m, van_tay_hien_tai="sha256:bbbbbbbbbbbbbbbb",
                          pha_he={"pmid:1": ["pmid:111"]},
                          bac_chung_cu=3, do_manh="1C")
        assert h.muc_phu is m.MucPhu.NGUON_CAP_TEP

    def test_van_tay_lech_ma_khong_co_nguon_khai_thi_KHONG_CO(self):
        m = _mo_dun()
        h = _da_doi_chieu(m, nguon_khai=None,
                          van_tay_hien_tai="sha256:bbbbbbbbbbbbbbbb")
        assert h.muc_phu is m.MucPhu.KHONG_CO


class TestChuoiDayDu:
    def _day_du(self, m, **thay_doi):
        goc = dict(
            nguon=[_toa_do(m, "not to exceed 4.5 mg/kg", ma="pmid:1"),
                   _toa_do(m, "maximum 4.5 mg/kg", ma="pmid:2")],
            pha_he={"pmid:1": ["pmid:111"], "pmid:2": ["pmid:222"]},
            bac_chung_cu=3, do_manh="1C",
        )
        goc.update(thay_doi)
        return _da_doi_chieu(m, **goc)

    def test_du_moi_thu_thi_CO_CHUOI_DAY_DU(self):
        m = _mo_dun()
        assert self._day_du(m).muc_phu is m.MucPhu.CO_CHUOI_DAY_DU

    @pytest.mark.parametrize("thieu,gia_tri", [
        ("pha_he", {}),
        ("bac_chung_cu", None),
        ("do_manh", None),
    ])
    def test_thieu_mot_manh_thi_TUT_ve_DA_DOI_CHIEU(self, thieu, gia_tri):
        """Bậc chính xác, không `is not` — xem lý do ở TestA0_R2."""
        m = _mo_dun()
        assert self._day_du(m, **{thieu: gia_tri}).muc_phu is m.MucPhu.DA_DOI_CHIEU

    def test_dong_thuan_KHONG_DO_DUOC_thi_CHUA_day_du(self):
        """Không đo được tính độc lập thì không được coi là có chuỗi đầy đủ."""
        m = _mo_dun()
        h = self._day_du(m, pha_he={"pmid:1": ["pmid:111"]})  # pmid:2 không khai
        assert h.dong_thuan is m.DongThuan.KHONG_DO_DUOC_DOC_LAP
        assert h.muc_phu is m.MucPhu.DA_DOI_CHIEU

    def test_KHONG_co_toa_do_thi_du_manh_khac_van_KHONG_len_chuoi_day_du(self):
        """`CO_CHUOI_DAY_DU` phải CỘNG DỒN lên `DA_DOI_CHIEU`, không xét độc lập.

        Ca này là ca duy nhất phơi được lỗi đó: đủ phả hệ, bậc chứng cứ và GRADE,
        nhưng KHÔNG có toạ độ nguồn. Một cài đặt xét `CO_CHUOI_DAY_DU` tách rời
        sẽ trả `CO_CHUOI_DAY_DU` và qua hết mọi kiểm thử còn lại.

        Trên dữ liệu thật lỗi này cũng không lộ, vì Đ3 = 0 dù cài đúng hay sai —
        kho chưa có `pha_he` nào. Nên chỉ ca dựng tay bắt được.
        """
        m = _mo_dun()
        h = _ho_so(m, khang_dinh="4.5", nguon_khai="ASRA 2018",
                   pha_he={"pmid:1": ["pmid:111"], "pmid:2": ["pmid:222"]},
                   bac_chung_cu=3, do_manh="1C")
        assert h.muc_phu is m.MucPhu.NGUON_CAP_TEP


# ------------------------------------------------------------------ A0.R1 bất biến

class TestA0_R1_KhongCoSetter:
    """Trường tự khai độ tin cậy là chế độ hỏng đã gặp ở đợt kiểm toán trước."""

    @pytest.mark.parametrize("ten", [
        "muc_phu", "dong_thuan", "noi_dung_truy_duoc",
        "van_tay_con_hieu_luc", "ly_do_khong_kiem",
    ])
    def test_moi_thuoc_tinh_suy_ra_deu_KHONG_gan_tay_duoc(self, ten):
        """Phải ĐỌC ĐƯỢC trước, rồi mới đòi GÁN KHÔNG ĐƯỢC.

        Chỉ đòi `setattr` ném lỗi thì không phân biệt được 'thuộc tính suy ra,
        không có setter' với 'thuộc tính KHÔNG TỒN TẠI' — pydantic ném ở cả hai
        ca. Kiểm thử kiểu đó xanh trước khi có mã và xanh sau khi có mã, tức
        không bao giờ đỏ, tức không chứng minh gì.
        """
        m = _mo_dun()
        h = _ho_so(m)
        assert hasattr(type(h), ten), f"{ten} chưa tồn tại — chưa nói được gì về setter"
        gia_tri = getattr(h, ten)
        with pytest.raises((AttributeError, ValueError, TypeError)):
            setattr(h, ten, "bịa")
        assert getattr(h, ten) == gia_tri, f"{ten} đã bị đổi — có setter thật"


# ------------------------------------------------- A0.R5, A0.R6 — kiểm cấu trúc mã

class TestA0_R5_R6_KhongMangKhongGhi:
    """Kiểm trên VĂN BẢN mã nguồn, không phải trên hành vi.

    Kiểm hành vi chỉ chứng minh 'lần chạy này không gọi mạng'; kiểm văn bản chứng
    minh 'không có đường nào để gọi'.
    """

    def _nguon(self):
        import inspect
        return inspect.getsource(_mo_dun())

    @pytest.mark.parametrize("cam", [
        "httpx", "requests", "urllib.request", "urlopen", "socket",
        "http.client", "aiohttp", "subprocess",
    ])
    def test_R6_khong_nhap_thu_vien_mang(self, cam):
        assert cam not in self._nguon()

    @pytest.mark.parametrize("cam", [
        "write_text", "write_bytes", "unlink", "rmtree", "os.remove", "os.rename",
        "shutil.copy", "json.dump(", ".write(", "mkdir",
    ])
    def test_R5_khong_goi_ham_ghi_hay_xoa(self, cam):
        """A0.R5 bảo vệ kho AnesthOS khỏi bị ghi đè — ràng buộc nặng nhất về hậu
        quả trong cả A0. Danh sách 4 chuỗi của bản trước để lọt `open(...,'w')`,
        `.write(`, `json.dump(`, `os.rename`, `shutil.copy`."""
        assert cam not in self._nguon()

    def test_R5_khong_mo_tep_o_che_do_GHI(self):
        nguon = self._nguon()
        for che_do in ['"w"', "'w'", '"a"', "'a'", '"w+"', "'w+'", '"wb"', "'wb'"]:
            assert f"open(" not in nguon or che_do not in nguon, \
                f"có dấu hiệu mở tệp ở chế độ ghi: {che_do}"

    def test_khong_them_thu_vien_ngoai_ngoai_pydantic(self):
        """A0 không thêm phụ thuộc. NetworkX để A3, và chỉ khi A1 chứng minh cần."""
        nguon = self._nguon()
        for cam in ["networkx", "pyvis", "llama_index", "pandas", "numpy"]:
            assert cam not in nguon


# ------------------------------------------ §4 · luật L7, L8 — hành vi lệnh chạy

class TestLuatNguonDuLieu:
    """L7 và L8 canh đúng sự cố đã xảy ra thật: AG-1 chạy nghiệm thu nhằm vào một
    thư mục thiếu `provenance_manifest.json`. Cả sáu số thô đều khớp đặc tả, nhưng
    KẾT LUẬN CHÍNH bị đảo ngược, và không gì trong báo cáo cho thấy điều đó.

    Hai luật này kiểm được ở lớp 1 bằng `tmp_path`, không cần cây dữ liệu AnesthOS.
    """

    def _thu_muc_co_manifest(self, tmp_path):
        (tmp_path / "drugs.json").write_text('{"a":{"dose":"5 mg"}}', encoding="utf-8")
        (tmp_path / "provenance_manifest.json").write_text(
            '{"drugs.json":{"citation":"Stoelting","synthetic":true}}', encoding="utf-8")
        return tmp_path

    def test_CHINH_PHEP_KIEM_bat_duoc_ca_vi_pham(self):
        """Chốt canh phải tự chứng minh nó có răng.

        Bản trước viết `... or "1" in ra[:vi_tri]` — một cửa thoát: chuỗi "16417"
        có chứa "1", nên một cài đặt in số TRƯỚC nguồn dữ liệu vẫn qua. Phép kiểm
        chưa từng bắt được gì thì không có bằng chứng nào nói nó đang canh cái gì.
        """
        d = "/du/lieu"
        assert _khong_co_so_truoc(f"Nguồn: {d}\n23 tệp\n16417 khẳng định\n", d)
        assert not _khong_co_so_truoc(f"Tổng số khẳng định: 16417\nNguồn: {d}\n", d)
        assert not _khong_co_so_truoc(f"Đọc 23 tệp\n{d}\n", d)
        assert not _khong_co_so_truoc("không in đường dẫn nào", d)

    def test_L7_in_duong_dan_va_so_tep_TRUOC_moi_con_so_khac(self, tmp_path, capsys):
        m = _mo_dun()
        thu_muc = self._thu_muc_co_manifest(tmp_path)
        m.main(["--du-lieu", str(thu_muc)])
        ra = capsys.readouterr().out
        duong_dan = str(thu_muc.resolve())
        assert duong_dan in ra, "không in đường dẫn TUYỆT ĐỐI"
        assert _khong_co_so_truoc(ra, duong_dan), \
            "có con số in ra TRƯỚC đường dẫn nguồn — vi phạm L7"

    def test_L8_thieu_manifest_thi_DUNG_khong_chay_tiep(self, tmp_path):
        """Không đọc được nguồn KHÔNG có nghĩa là không có nguồn."""
        m = _mo_dun()
        (tmp_path / "drugs.json").write_text('{"a":{"dose":"5 mg"}}', encoding="utf-8")
        ma_thoat = m.main(["--du-lieu", str(tmp_path)])
        assert ma_thoat != 0, "thiếu provenance_manifest.json mà vẫn trả mã thoát 0"

    def test_L8_co_manifest_thi_chay_binh_thuong(self, tmp_path):
        m = _mo_dun()
        assert m.main(["--du-lieu", str(self._thu_muc_co_manifest(tmp_path))]) == 0


# --------------------------------------- §2.2 · loại trừ trường `references`

class TestLoaiTruTruongReferences:
    def test_chuoi_trich_dan_KHONG_di_qua_phep_kiem_so(self):
        """Cho chuỗi trích dẫn qua phép kiểm liều nghĩa là coi NĂM XUẤT BẢN và
        SỐ TẬP như thể chúng là liều thuốc."""
        m = _mo_dun()
        h = _ho_so(m, khoa="references",
                   khang_dinh="Walker BJ et al. Anesthesiology 2018;129:721-32",
                   nguon=[_toa_do(m, "một trích dẫn khác hẳn")])
        assert h.noi_dung_truy_duoc is m.TrangThai.KHONG_KIEM_DUOC
        assert h.ly_do_khong_kiem is m.LyDoKhongKiemDuoc.KHANG_DINH_KHONG_SO

    def test_khoa_khac_co_so_thi_VAN_kiem(self):
        """Chỉ `references` được loại, không loại lây sang khoá khác."""
        m = _mo_dun()
        h = _ho_so(m, khoa="dose", khang_dinh="4.5",
                   nguon=[_toa_do(m, "not to exceed 4.5 mg/kg")])
        assert h.noi_dung_truy_duoc is m.TrangThai.DAT

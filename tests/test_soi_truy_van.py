"""Test công cụ soi truy vấn.

Toàn bộ giá trị của công cụ này nằm ở việc tách BA tình huống mà nếu gộp lại
thì người sửa sẽ đi sửa nhầm chỗ:

  cú pháp sai        -> sửa tên trường
  cú pháp đúng, bài  -> sửa giả định về dữ liệu, đừng đụng cú pháp
  mồi không có
  dùng được          -> giữ nguyên

Bộ test này chốt đúng ranh giới đó.
"""

from __future__ import annotations

from tools.soi_truy_van import KetQua, soi


class GiaLap:
    """Fetcher giả: tra bảng đã dựng sẵn thay vì gọi mạng."""

    def __init__(self, bang: dict[str, int]):
        self.bang = bang
        self.da_hoi: list[str] = []

    def quet_toan_bo(self, q, tran=1, page_size=1):
        self.da_hoi.append(q)
        if q not in self.bang:
            raise RuntimeError(f"truy vấn không hiểu: {q}")
        return [], self.bang[q]


class TestPhanBietBaTinhHuong:
    def test_cu_phap_sai_khi_dung_mot_minh_ra_khong(self):
        r = KetQua("thử", 'SAI:"x"', mot_minh=0, voi_bai_moi=0)
        assert r.hong and "CÚ PHÁP SAI" in r.chan_doan

    def test_cu_phap_dung_nhung_bai_moi_khong_co_thuoc_tinh(self):
        """KHÔNG phải lỗi của ta — đây là phát hiện về dữ liệu."""
        r = KetQua("thử", "PUB_YEAR:1999", mot_minh=50_000, voi_bai_moi=0)
        assert not r.hong
        assert "không mang thuộc tính" in r.chan_doan

    def test_dung_duoc(self):
        r = KetQua("thử", "SRC:MED", mot_minh=40_000_000, voi_bai_moi=1)
        assert not r.hong and "dùng được" in r.chan_doan

    def test_menh_de_hong_khong_bi_lan_voi_menh_de_hep(self):
        """Mệnh đề rất hẹp nhưng đúng cú pháp KHÔNG được xếp chung với sai cú pháp."""
        hep = KetQua("hẹp", 'TITLE:"một cụm rất hiếm"', mot_minh=3, voi_bai_moi=0)
        sai = KetQua("sai", 'KHONGCO:"x"', mot_minh=0, voi_bai_moi=0)
        assert not hep.hong and sai.hong


class TestSoiHoiDuHaiCau:
    def test_moi_menh_de_hoi_rieng_va_hoi_kem_bai_moi(self):
        g = GiaLap({
            'MESH:"A"': 100,
            'EXT_ID:26095867 AND (MESH:"A")': 1,
        })
        kq = soi(g, "26095867", {"mesh": 'MESH:"A"'})
        assert len(g.da_hoi) == 2
        assert kq[0].mot_minh == 100 and kq[0].voi_bai_moi == 1

    def test_loi_mang_tinh_la_khong_ket_qua_khong_lam_sap(self):
        """Một mệnh đề hỏng không được làm chết cả phiên soi — mất hết chẩn đoán."""
        g = GiaLap({'MESH:"A"': 5, 'EXT_ID:1 AND (MESH:"A")': 1})
        kq = soi(g, "1", {"tốt": 'MESH:"A"', "vỡ": 'KHONGCO:"x"'})
        assert len(kq) == 2
        assert kq[0].voi_bai_moi == 1
        assert kq[1].mot_minh == 0 and kq[1].hong

    def test_soi_giu_dung_thu_tu_menh_de(self):
        g = GiaLap({f'M{i}': i for i in range(1, 4)}
                   | {f'EXT_ID:9 AND (M{i})': 0 for i in range(1, 4)})
        kq = soi(g, "9", {f"m{i}": f"M{i}" for i in range(1, 4)})
        assert [r.ten for r in kq] == ["m1", "m2", "m3"]


class TestLuoiNhomXBaiMoi:
    """Lưới trả lời câu đắt hơn soi từng mệnh đề: nhóm nào loại nhầm bài nào."""

    @staticmethod
    def _gia_lap(cho_qua: dict[str, set[str]]):
        """cho_qua: tên nhóm -> tập PMID mà nhóm đó cho lọt."""
        from tools.soi_truy_van import NHOM_TRUY_VAN

        class G:
            def quet_toan_bo(self, q, tran=1, page_size=1):
                pmid = q.split("EXT_ID:")[1].split(" ")[0]
                for ten, md in NHOM_TRUY_VAN.items():
                    if md in q:
                        return [], int(pmid in cho_qua.get(ten, set()))
                return [], 0
        return G()

    def test_moi_nhom_qua_het_thi_khong_co_thu_pham(self, capsys):
        from tools.soi_truy_van import NHAN_MOI, NHOM_TRUY_VAN, in_luoi, soi_nhom
        moi = list(NHAN_MOI)
        tat_ca = {m.rsplit(":", 1)[-1] for m in moi}
        g = self._gia_lap({t: tat_ca for t in NHOM_TRUY_VAN})
        assert in_luoi(soi_nhom(g, moi, NHOM_TRUY_VAN), moi) == []
        assert "4/4" in capsys.readouterr().out

    def test_neu_dung_ten_nhom_loai_nham(self, capsys):
        from tools.soi_truy_van import NHAN_MOI, NHOM_TRUY_VAN, in_luoi, soi_nhom
        moi = list(NHAN_MOI)
        tat_ca = {m.rsplit(":", 1)[-1] for m in moi}
        cho_qua = {t: tat_ca for t in NHOM_TRUY_VAN}
        cho_qua["loại bài / bậc CC"] = tat_ca - {"40448969"}   # DOAC25 bị loại
        thu_pham = in_luoi(soi_nhom(self._gia_lap(cho_qua), moi, NHOM_TRUY_VAN), moi)
        assert thu_pham == ["loại bài / bậc CC"]
        assert "3/4" in capsys.readouterr().out

    def test_bai_phai_qua_MOI_nhom_moi_duoc_tinh(self):
        """Truy vấn nối bằng AND — qua 3/4 nhóm vẫn là bị loại."""
        from tools.soi_truy_van import NHAN_MOI, NHOM_TRUY_VAN, soi_nhom
        moi = list(NHAN_MOI)
        tat_ca = {m.rsplit(":", 1)[-1] for m in moi}
        cho_qua = {t: tat_ca for t in NHOM_TRUY_VAN}
        cho_qua["kho MEDLINE"] = tat_ca - {"26095867"}
        luoi = soi_nhom(self._gia_lap(cho_qua), moi, NHOM_TRUY_VAN)
        assert not all(h["pubmed:26095867"] for h in luoi.values())

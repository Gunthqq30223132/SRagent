"""Test hàng đợi bàn giao Spark → SR-Agent.

Mỗi lớp test dưới đây chặn MỘT lỗi đã ĐO ĐƯỢC trong bộ dữ liệu Spark cũ
(27 file, 21 ngày, đọc ngày 2026-08-23), không phải lỗi giả định:
  - mã bài hỏng 22/22 dòng do Sheets ép kiểu số
  - bài 2606.01770 có 2 Doc nhưng 0 dòng tracker, không ai biết
  - nhật ký báo thành công cho đúng lần thất bại đó
  - cột 'Trạng Thái Kiểm Định' ghi 'Verified' ở 22/22 dòng, không ai kiểm gì
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from pydantic import ValidationError

from tools.sources.hang_doi import PhieuQuet, doc_hang_doi, kiem_do_tuoi

PHIEU_TOT = {
    "ma_phieu": "2026-08-24_chong-dong_pubmed",
    "ngay_quet": "2026-08-24",
    "nguon": "pubmed",
    "cau_hoi": "Quản lý chống đông trước, trong và sau mổ",
    "chuoi_truy_van": '("Anticoagulants"[Mesh]) AND ("Perioperative Care"[Mesh])',
    "so_ket_qua_tho": 412,
    "so_da_sang": 60,
    "ids": ["pubmed:26095867", "pubmed:41073233"],
    "loai_tru": [{"id": "pubmed:11111111", "ly_do": "nghiên cứu trên động vật"}],
}


def phieu(**ghi_de) -> dict:
    return {**PHIEU_TOT, **ghi_de}


class TestMaBaiKhongBiHong:
    """Lỗi #1: Sheets đọc '2606.01435' thành số rồi in ra '260.601.435'."""

    def test_ma_giu_nguyen_qua_json(self):
        p = PhieuQuet.model_validate(phieu(ids=["pubmed:2606.01435"]))
        assert p.ids == ["pubmed:2606.01435"]

    def test_so_khong_bi_ep_kieu(self, tmp_path):
        """Vòng qua đĩa rồi đọc lại — mã phải nguyên vẹn từng ký tự."""
        f = tmp_path / "p.json"
        f.write_text(json.dumps(phieu(ids=["arxiv:2606.01435"])), encoding="utf-8")
        assert doc_hang_doi(tmp_path).phieu_hop_le[0].ids == ["arxiv:2606.01435"]


class TestSoHocTuKhaiPhaiNhatQuan:
    """Một trường tự khai không ràng buộc thì vô giá trị — xem cột 'Verified'.

    Không cần biết Spark có trung thực không; chỉ cần các con số nó khai
    cộng lại được với nhau.
    """

    def test_sang_nhieu_hon_tim_duoc_bi_tu_choi(self):
        with pytest.raises(ValidationError, match="không thể sàng nhiều hơn"):
            PhieuQuet.model_validate(phieu(so_ket_qua_tho=10, so_da_sang=50))

    def test_giu_cong_loai_vuot_qua_da_sang_bi_tu_choi(self):
        with pytest.raises(ValidationError, match="đã sàng"):
            PhieuQuet.model_validate(phieu(
                so_da_sang=2,
                ids=["pubmed:1", "pubmed:2"],
                loai_tru=[{"id": "pubmed:3", "ly_do": "ngoài phạm vi tuổi"}],
            ))

    def test_vua_giu_vua_loai_cung_mot_bai_bi_tu_choi(self):
        with pytest.raises(ValidationError, match="mâu thuẫn nội tại"):
            PhieuQuet.model_validate(phieu(
                ids=["pubmed:26095867"],
                loai_tru=[{"id": "pubmed:26095867", "ly_do": "không phải người lớn"}],
            ))

    def test_so_hop_le_thi_di_qua(self):
        assert PhieuQuet.model_validate(PHIEU_TOT).so_ket_qua_tho == 412


class TestKhongDuocIMLANG:
    """Lỗi #2 và #3: mất bài, và nhật ký báo thành công cho lần thất bại."""

    def test_quet_ra_0_bai_phai_giai_thich(self):
        with pytest.raises(ValidationError, match="là một KẾT QUẢ"):
            PhieuQuet.model_validate(phieu(ids=[], loai_tru=[]))

    def test_quet_ra_0_bai_co_giai_thich_thi_hop_le(self):
        p = PhieuQuet.model_validate(phieu(
            ids=[], loai_tru=[], ghi_chu="PubMed trả 0 kết quả cho khoảng ngày này"))
        assert p.ids == []

    def test_ly_do_loai_tru_mot_chu_bi_tu_choi(self):
        with pytest.raises(ValidationError, match="quá ngắn"):
            PhieuQuet.model_validate(phieu(
                loai_tru=[{"id": "pubmed:1", "ly_do": "-"}]))

    def test_id_trung_trong_cung_phieu_bi_bat(self):
        """2606.01770 từng được tạo Doc hai lần mà không ai phát hiện."""
        with pytest.raises(ValidationError, match="ID lặp"):
            PhieuQuet.model_validate(phieu(
                ids=["pubmed:26095867", "pubmed:26095867"]))


class TestTruyVanPhaiNguyenVan:
    """Không có chuỗi truy vấn nguyên văn thì không dựng được sơ đồ PRISMA."""

    def test_mo_ta_bang_loi_bi_tu_choi(self):
        with pytest.raises(ValidationError, match="NGUYÊN VĂN"):
            PhieuQuet.model_validate(phieu(chuoi_truy_van="tìm về chống đông"))

    def test_chuoi_boolean_that_di_qua(self):
        assert PhieuQuet.model_validate(PHIEU_TOT).chuoi_truy_van.startswith('("Anti')


class TestMaPhieu:
    @pytest.mark.parametrize("xau", [
        "2026-08-24", "chong-dong_pubmed", "24-08-2026_x_y", "2026-08-24_Chống_pubmed",
    ])
    def test_dinh_dang_sai_bi_tu_choi(self, xau):
        with pytest.raises(ValidationError, match="sai định dạng"):
            PhieuQuet.model_validate(phieu(ma_phieu=xau))


class TestDocThuMuc:
    def test_doc_nhieu_phieu(self, tmp_path):
        for i, ngay in enumerate(["2026-08-22", "2026-08-23"], 1):
            (tmp_path / f"p{i}.json").write_text(json.dumps(phieu(
                ma_phieu=f"{ngay}_chong-dong_pubmed", ngay_quet=ngay)),
                encoding="utf-8")
        kq = doc_hang_doi(tmp_path)
        assert len(kq.phieu_hop_le) == 2 and kq.tong_id == 4

    def test_phieu_hong_khong_lam_dung_ca_me(self, tmp_path):
        (tmp_path / "tot.json").write_text(json.dumps(PHIEU_TOT), encoding="utf-8")
        (tmp_path / "hong.json").write_text("{khong phai json", encoding="utf-8")
        kq = doc_hang_doi(tmp_path)
        assert len(kq.phieu_hop_le) == 1 and len(kq.phieu_hong) == 1

    def test_phieu_hong_khong_bi_nuot_im_lang(self, tmp_path):
        """Bỏ qua thầm lặng chính là cách bài 2606.01770 biến mất."""
        (tmp_path / "hong.json").write_text('{"ma_phieu": "sai"}', encoding="utf-8")
        kq = doc_hang_doi(tmp_path)
        assert kq.phieu_hong and "hong.json" == kq.phieu_hong[0][0]

    def test_thu_muc_khong_ton_tai_bao_loi_ro_rang(self, tmp_path):
        kq = doc_hang_doi(tmp_path / "khong-co")
        assert "Google Drive" in kq.phieu_hong[0][1]


class TestPhatHienVANGMAT:
    """Chế độ hỏng nguy hiểm nhất không phải ghi sai, mà là KHÔNG GHI GÌ."""

    def test_hang_doi_rong_bi_canh_bao(self, tmp_path):
        assert "RỖNG" in kiem_do_tuoi(doc_hang_doi(tmp_path))

    def test_phieu_cu_bi_canh_bao(self, tmp_path):
        (tmp_path / "p.json").write_text(json.dumps(phieu(
            ma_phieu="2026-08-01_chong-dong_pubmed", ngay_quet="2026-08-01")),
            encoding="utf-8")
        canh_bao = kiem_do_tuoi(doc_hang_doi(tmp_path), hom_nay=date(2026, 8, 24))
        assert "CŨ" in canh_bao and "23 ngày" in canh_bao

    def test_phieu_moi_khong_canh_bao(self, tmp_path):
        (tmp_path / "p.json").write_text(json.dumps(PHIEU_TOT), encoding="utf-8")
        assert kiem_do_tuoi(doc_hang_doi(tmp_path), hom_nay=date(2026, 8, 24)) is None

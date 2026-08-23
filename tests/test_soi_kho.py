"""Test bộ soi kho — công cụ trả lời 'vì sao gần nửa kho chưa phân loại'.

Câu hỏi mà bộ test này chốt ranh giới, vì gộp hai thứ lại là mất khả năng sửa:

  bản ghi KHÔNG mang nhãn nào   -> MEDLINE không nói gì về thiết kế nghiên cứu
  bản ghi mang nhãn ta chưa xếp -> BẢNG XẾP BẬC CỦA TA thiếu

Một bên không sửa được, một bên sửa được. Báo cáo gộp chung thì người đọc không
biết mình đang ở tình huống nào.
"""

from __future__ import annotations

import json

import pytest

from tools.soi_kho import (
    de_xuat_bo_sung,
    dem_nhan,
    doc_kho,
    kiem_trung,
    nhan_cua_chua_phan_loai,
    phan_bo_nam,
)


def br(source_id, bac, nhan, ngay="2021-06-09T00:00:00Z"):
    return {"source_id": source_id, "evidence_level": bac,
            "loai_bai_goc": nhan, "published_date": ngay}


KHO = [
    br("europepmc:MED:1", 3, ["Randomized Controlled Trial", "Journal Article"]),
    br("europepmc:MED:2", None, ["Journal Article"]),
    br("europepmc:MED:3", None, ["Journal Article", "Comparative Study"]),
    br("europepmc:MED:4", None, []),
    br("europepmc:MED:5", 1, ["Meta-Analysis"], None),
]


class TestPhanBietHaiKieuChuaPhanLoai:
    def test_ban_ghi_khong_nhan_duoc_dem_rieng(self):
        assert nhan_cua_chua_phan_loai(KHO)["(KHÔNG có nhãn nào)"] == 1

    def test_ban_ghi_co_nhan_thi_dem_theo_nhan(self):
        c = nhan_cua_chua_phan_loai(KHO)
        assert c["Journal Article"] == 2 and c["Comparative Study"] == 1

    def test_khong_dem_ban_ghi_da_xep_bac(self):
        """Bản ghi đã có bậc không được lẫn vào phần chẩn đoán 'chưa phân loại'."""
        assert "Randomized Controlled Trial" not in nhan_cua_chua_phan_loai(KHO)

    def test_khong_tao_khoa_rac(self):
        assert "" not in nhan_cua_chua_phan_loai(KHO)


class TestDeXuatBoSung:
    def test_bo_nhan_da_co_trong_bang(self):
        from collections import Counter
        assert de_xuat_bo_sung(Counter({"Meta-Analysis": 500}), toi_thieu=1) == []

    def test_bo_nhan_vo_nghia(self):
        """'Journal Article' có trên gần như mọi bản ghi nên không nói gì về thiết kế."""
        from collections import Counter
        assert de_xuat_bo_sung(Counter({"Journal Article": 9999}), toi_thieu=1) == []

    def test_giu_nhan_that_su_moi(self):
        from collections import Counter
        assert de_xuat_bo_sung(
            Counter({"Comparative Study": 300}), toi_thieu=20
        ) == [("Comparative Study", 300)]

    def test_bo_nhan_qua_hiem(self):
        """Nhãn lác đác vài bài không đáng sửa bảng xếp bậc."""
        from collections import Counter
        assert de_xuat_bo_sung(Counter({"Nhãn Lạ": 3}), toi_thieu=20) == []

    def test_bo_dong_khong_phai_nhan(self):
        from collections import Counter
        assert de_xuat_bo_sung(
            Counter({"(KHÔNG có nhãn nào)": 900}), toi_thieu=1
        ) == []

    def test_khong_tu_them_vao_bang(self):
        """Công cụ ĐỀ XUẤT, không sửa. Xếp bậc là phán đoán phương pháp luận."""
        from collections import Counter
        from tools.sources.pubmed import EVIDENCE_RANK
        truoc = dict(EVIDENCE_RANK)
        de_xuat_bo_sung(Counter({"Comparative Study": 300}))
        assert EVIDENCE_RANK == truoc


class TestDemVaKiemTra:
    def test_dem_nhan_toan_kho(self):
        assert dem_nhan(KHO)["Journal Article"] == 3

    def test_bat_ma_trung(self):
        assert kiem_trung(KHO + [KHO[0]]) == [("europepmc:MED:1", 2)]

    def test_kho_sach_thi_khong_bao_trung(self):
        assert kiem_trung(KHO) == []

    def test_phan_bo_nam_gom_ca_ban_ghi_thieu_ngay(self):
        n = phan_bo_nam(KHO)
        assert n["2021"] == 4 and n["?"] == 1


class TestDocKho:
    def test_thieu_tep_thi_dung_han(self, tmp_path):
        with pytest.raises(SystemExit, match="quet_that"):
            doc_kho(tmp_path / "khong-co.json")

    def test_tep_sai_dinh_dang_bi_tu_choi(self, tmp_path):
        p = tmp_path / "x.json"
        p.write_text(json.dumps({"linh tinh": 1}), encoding="utf-8")
        with pytest.raises(SystemExit, match="không phải tệp kho"):
            doc_kho(p)

    def test_doc_duoc_tep_dung(self, tmp_path):
        p = tmp_path / "kho.json"
        p.write_text(json.dumps({"ban_ghi": KHO, "kho_bao_co": 9}), encoding="utf-8")
        assert len(doc_kho(p)["ban_ghi"]) == 5


class TestKhoCuKhongCoNhanGoc:
    def test_bao_ro_la_tep_ban_cu(self, tmp_path, capsys):
        """Kho tải bằng bản cũ đã VỨT nhãn gốc — phải nói thẳng, đừng báo 0 nhãn."""
        from tools.soi_kho import main
        p = tmp_path / "cu.json"
        p.write_text(json.dumps({"ban_ghi": [
            {"source_id": "europepmc:MED:1", "evidence_level": None},
        ], "kho_bao_co": 1}), encoding="utf-8")
        assert main([str(p)]) == 1
        assert "bản cũ" in capsys.readouterr().out

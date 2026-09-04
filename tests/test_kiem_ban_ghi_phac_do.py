"""Tường lửa số phải có ĐƯỜNG CHẠY THẬT, và phải có đủ ba trạng thái.

Cơ chế [8] của docs/SO_CO_CHE.md được vẽ đứng chắn trước AnesthOS nhưng trước đây không
đường chạy sản xuất nào gọi nó. Bộ kiểm thử này khoá hai thứ lại:

1. Tường lửa thật sự BẮT được ca vi phạm dựng sẵn (không chỉ chạy xanh).
2. "Không kiểm được" KHÔNG được tính là "đạt" — check_output trả passed=True cho khẳng
   định không có mỏ neo số, nên lớp bọc phải tự tách VÔ HIỆU ra.
"""

import json

from tools.kiem_ban_ghi_phac_do import DAT, TRUOT, VO_HIEU, chay, kiem_mot_ban_ghi

NGUYEN_VAN = (
    "Lidocaine without epinephrine (also called plain lidocaine) - 5 mg/kg "
    "(maximum total dose: 300 mg)"
)


def ban_ghi(khang_dinh, nguyen_van=NGUYEN_VAN, **thay_doi):
    r = {
        "ma_doi_chieu": "lidocaine.maxDoseMgPerKg.plain",
        "diem_quyet_dinh": "Q1",
        "khang_dinh": khang_dinh,
        "trich_nguyen_van": nguyen_van,
    }
    r.update(thay_doi)
    return r


def test_so_co_trong_nguyen_van_thi_DAT():
    trang_thai, _ = kiem_mot_ban_ghi(ban_ghi("5"))
    assert trang_thai == DAT


def test_so_KHONG_co_trong_nguyen_van_thi_TRUOT():
    """Ca vi phạm dựng sẵn — chứng minh phép kiểm này thật sự bắt được gì đó."""
    trang_thai, ly_do = kiem_mot_ban_ghi(ban_ghi("4.5"))
    assert trang_thai == TRUOT
    assert "4.5" in ly_do


def test_khong_boc_duoc_mo_neo_thi_VO_HIEU_chu_khong_phai_DAT():
    """check_output trả passed=True ở đây. Gộp vào ĐẠT là đúng kiểu hỏng cần chặn."""
    from tools.guard.firewall import check_output

    ket = check_output("one-third", [NGUYEN_VAN], domain="clinical", strict=True)
    assert ket.passed is True and ket.anchors_checked == 0  # tường lửa trần nói "đạt"

    trang_thai, _ = kiem_mot_ban_ghi(ban_ghi("one-third"))
    assert trang_thai == VO_HIEU  # lớp bọc phải nói khác


def test_khong_co_nguyen_van_thi_VO_HIEU():
    """Sau khi gỡ nguyên văn nguồn thương mại (X4), trường này rỗng — không được thành ĐẠT."""
    for rong in (None, "", "   "):
        trang_thai, ly_do = kiem_mot_ban_ghi(ban_ghi("5", nguyen_van=rong))
        assert trang_thai == VO_HIEU
        assert "nguyên văn" in ly_do


def test_so_nam_LOT_trong_so_lon_hon_khong_duoc_tinh_la_khop():
    """'30' không được coi là khớp chỉ vì nguồn có '300'."""
    trang_thai, _ = kiem_mot_ban_ghi(ban_ghi("30"))
    assert trang_thai == TRUOT


# --- Hành vi ở mức lệnh: mã thoát và luật L7 -------------------------------------------

def _chay_tep(tmp_path, ban_ghi_list):
    tep = tmp_path / "ban_ghi.json"
    tep.write_text(json.dumps(ban_ghi_list, ensure_ascii=False), encoding="utf-8")
    return tep


def test_ma_thoat_phan_biet_TRUOT_voi_VO_HIEU(tmp_path, capsys):
    assert chay(_chay_tep(tmp_path, [ban_ghi("5")])) == 0
    capsys.readouterr()
    assert chay(_chay_tep(tmp_path, [ban_ghi("4.5")])) == 1        # TRƯỢT
    capsys.readouterr()
    assert chay(_chay_tep(tmp_path, [ban_ghi("one-third")])) == 3  # VÔ HIỆU, khác hẳn ĐẠT
    capsys.readouterr()


def test_tep_khong_doc_duoc_la_VO_HIEU_chu_khong_phai_DAT(tmp_path, capsys):
    assert chay(tmp_path / "khong-ton-tai.json") == 2
    assert "VÔ HIỆU" in capsys.readouterr().out


def test_L7_in_nguon_du_lieu_truoc_moi_con_so(tmp_path, capsys):
    """Luật L7: nguồn dữ liệu (đường dẫn tuyệt đối + số bản ghi) đứng trước mọi số khác."""
    chay(_chay_tep(tmp_path, [ban_ghi("5"), ban_ghi("4.5")]))
    dong = [d for d in capsys.readouterr().out.splitlines() if d.strip()]
    assert dong[0].startswith("NGUỒN DỮ LIỆU")
    assert str(tmp_path) in dong[0]
    assert dong[1].startswith("SỐ BẢN GHI")
    assert "2" in dong[1]

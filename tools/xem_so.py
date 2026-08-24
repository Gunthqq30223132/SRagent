"""Xem tiến độ sàng lọc: kho còn bao nhiêu chưa quyết, PRISMA đang ra sao.

    python3 tools/xem_so.py kho_chong_dong.json
    python3 tools/xem_so.py kho_chong_dong.json --so quyet_dinh.jsonl

Chạy HOÀN TOÀN NGOẠI TUYẾN. Sàng lọc 13.000 bài không xong trong một buổi, nên
câu hỏi 'đang tới đâu rồi' phải trả lời được bất cứ lúc nào mà không tốn gì.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.so_quyet_dinh import SoQuyetDinh, van_tay_tu_tep


def _muc(t: str) -> None:
    print(f"\n{'─' * 66}\n{t}\n{'─' * 66}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Xem tiến độ sàng lọc")
    ap.add_argument("kho", type=Path)
    ap.add_argument("--so", type=Path, default=None,
                    help="mặc định: <tên kho>_quyet_dinh.jsonl cạnh tệp kho")
    a = ap.parse_args(argv)

    if not a.kho.exists():
        print(f"Không thấy kho {a.kho}. Chạy tools/quet_that.py trước.")
        return 2
    duong_so = a.so or a.kho.with_name(a.kho.stem + "_quyet_dinh.jsonl")

    van_tay, ma_kho = van_tay_tu_tep(a.kho)
    so = SoQuyetDinh(duong_so, van_tay)
    tk = so.thong_ke()
    con = so.con_lai(ma_kho)

    print("=" * 66)
    print("TIẾN ĐỘ SÀNG LỌC")
    print("=" * 66)
    print(f"  Kho      : {a.kho}")
    print(f"  Sổ       : {duong_so}{'' if duong_so.exists() else '  (chưa có)'}")
    print(f"  Vân tay  : {van_tay}")

    _muc("TIẾN ĐỘ")
    tong = len(ma_kho)
    xong = tong - len(con)
    print(f"  Bản ghi trong kho : {tong:,}".replace(",", "."))
    print(f"  Đã ra quyết định  : {xong:,}".replace(",", "."), end="")
    print(f"  ({xong / tong:.1%})" if tong else "")
    print(f"  CÒN LẠI           : {len(con):,}".replace(",", "."))

    if tk["theo_quyet_dinh"]:
        _muc("PHÂN BỐ QUYẾT ĐỊNH")
        ten = {"giu": "giữ", "loai": "loại", "nghi_ngo": "nghi ngờ"}
        for k, v in sorted(tk["theo_quyet_dinh"].items()):
            print(f"  {ten.get(k, k):<12}{v:>8,}".replace(",", "."))

    if tk["loai_theo_ly_do"]:
        _muc("LOẠI THEO LÝ DO  (đây chính là số liệu PRISMA)")
        for ly_do, n in sorted(tk["loai_theo_ly_do"].items(), key=lambda x: -x[1])[:15]:
            print(f"  {n:>6,}".replace(",", ".") + f"  {ly_do[:56]}")

    if tk["theo_nguoi_sang"]:
        _muc("AI SÀNG")
        for ng, n in sorted(tk["theo_nguoi_sang"].items(), key=lambda x: -x[1]):
            print(f"  {ng:<28}{n:>8,}".replace(",", "."))

    # Ba mục dưới đây là CẢNH BÁO, không phải thống kê. In cuối để không bị trôi.
    canh_bao = False

    if len(tk["phien_ban_tieu_chi"]) > 1:
        canh_bao = True
        _muc("⚠ SỔ ĐANG TRỘN NHIỀU PHIÊN BẢN TIÊU CHÍ")
        print(f"  {', '.join(tk['phien_ban_tieu_chi'])}")
        print("  Quyết định ra dưới hai bộ tiêu chí khác nhau thì KHÔNG so được")
        print("  với nhau, và gộp lại thành một sơ đồ PRISMA là sai.")

    if tk["dong_hong"]:
        canh_bao = True
        _muc(f"⚠ {len(tk['dong_hong'])} DÒNG HỎNG TRONG SỔ")
        for so_dong, loi in tk["dong_hong"][:10]:
            print(f"  dòng {so_dong}: {loi[:70]}")
        print("  Mỗi dòng hỏng là một bài mất khỏi PRISMA. Xem lại rồi ghi lại.")

    if tk["van_tay_la"]:
        canh_bao = True
        _muc("⚠ SỔ CÓ QUYẾT ĐỊNH THUỘC KHO KHÁC")
        for vt, n in tk["van_tay_la"].items():
            print(f"  {vt} — {n} dòng (đã bỏ qua)")
        print("  Chúng được ra trên một tập bài khác. Không tính vào kho này.")

    if tk["da_doi_y"]:
        _muc(f"ĐÃ ĐỔI Ý · {len(tk['da_doi_y'])} bài")
        print("  Không phải lỗi — chỉ-nối-thêm nghĩa là đổi ý được, và lịch sử")
        print("  vẫn còn. Nhưng bài bị lật đi lật lại là dấu hiệu tiêu chí đang")
        print("  mơ hồ ở đúng chỗ đó.")
        for ma, n in sorted(tk["da_doi_y"].items(), key=lambda x: -x[1])[:8]:
            print(f"    {ma} × {n}")

    _muc("KẾT LUẬN")
    if con:
        print(f"  Chưa xong — còn {len(con):,} bài chưa ai nhìn.".replace(",", "."))
        print("  Chưa dựng được PRISMA hoàn chỉnh từ sổ này.")
    elif canh_bao:
        print("  Đã quyết hết, NHƯNG có cảnh báo ở trên phải xử trước khi dựng PRISMA.")
    else:
        print("  ✓ Đã ra quyết định cho toàn bộ kho, sổ sạch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

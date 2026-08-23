"""Soi kho đã tải về: nhãn nào có thật, vì sao gần nửa kho 'chưa phân loại'.

    python3 tools/soi_kho.py kho_chong_dong.json

VÌ SAO CẦN TỆP NÀY — một con số từ lần chạy thật:

  CHƯA PHÂN LOẠI    2.459 / 5.000   (49%)

Gần nửa kho không được xếp bậc chứng cứ. Câu hỏi đúng KHÔNG phải 'làm sao xếp
bậc cho chúng' mà là 'chúng đang mang nhãn gì'. Vì bảng EVIDENCE_RANK là GIẢ
THIẾT của ta về tập nhãn mà NLM dùng — và giả thiết thì phải đối chiếu với dữ
liệu thật, không phải mở rộng bằng cách đoán thêm.

Công cụ này chạy HOÀN TOÀN NGOẠI TUYẾN trên file kho. Đó là chủ ý: sau khi đã
tốn công tải 13.000 bản ghi, mọi câu hỏi về chúng phải trả lời được mà không
phải gọi mạng lần nữa. Kho tải về một lần, soi bao nhiêu lần cũng được.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.sources.pubmed import EVIDENCE_RANK

# Nhãn có mặt gần như trên mọi bản ghi MEDLINE nên không nói lên thiết kế nghiên
# cứu. Liệt kê tường minh để báo cáo không đề xuất thêm chúng vào bảng xếp bậc.
NHAN_VO_NGHIA = {"journal article", "english abstract", "historical article"}


def doc_kho(duong_dan: Path) -> dict:
    if not duong_dan.exists():
        raise SystemExit(f"Không thấy tệp {duong_dan}. Chạy tools/quet_that.py trước.")
    data = json.loads(duong_dan.read_text(encoding="utf-8"))
    if "ban_ghi" not in data:
        raise SystemExit(f"{duong_dan} không phải tệp kho (thiếu khoá 'ban_ghi').")
    return data


def dem_nhan(ban_ghi: list[dict]) -> Counter:
    c: Counter = Counter()
    for r in ban_ghi:
        for nhan in r.get("loai_bai_goc") or []:
            c[nhan] += 1
    return c


def nhan_cua_chua_phan_loai(ban_ghi: list[dict]) -> Counter:
    """Nhãn xuất hiện trên các bản ghi KHÔNG xếp được bậc. Đây là câu trả lời thật."""
    c: Counter = Counter()
    for r in ban_ghi:
        if r.get("evidence_level") is not None:
            continue
        nhan = r.get("loai_bai_goc") or []
        if not nhan:
            # Bản ghi KHÔNG mang nhãn nào khác hẳn bản ghi mang nhãn ta chưa xếp
            # bậc: một bên là MEDLINE không nói gì, bên kia là bảng của ta thiếu.
            c["(KHÔNG có nhãn nào)"] += 1
        for n in nhan:
            c[n] += 1
    return c


def de_xuat_bo_sung(chua: Counter, toi_thieu: int = 20) -> list[tuple[str, int]]:
    """Nhãn nào đủ phổ biến và CHƯA có trong bảng xếp bậc thì đáng cân nhắc thêm.

    Không tự thêm. Xếp bậc chứng cứ là phán đoán phương pháp luận, phải do người
    quyết. Công cụ chỉ đưa ra danh sách kèm số đếm để phán đoán đó dựa trên dữ
    liệu thay vì trí nhớ.
    """
    return [
        (n, s) for n, s in chua.most_common()
        if s >= toi_thieu
        and n.lower() not in EVIDENCE_RANK
        and n.lower() not in NHAN_VO_NGHIA
        and not n.startswith("(")
    ]


def kiem_trung(ban_ghi: list[dict]) -> list[tuple[str, int]]:
    c = Counter(r.get("source_id", "") for r in ban_ghi)
    return [(k, v) for k, v in c.items() if v > 1]


def phan_bo_nam(ban_ghi: list[dict]) -> Counter:
    c: Counter = Counter()
    for r in ban_ghi:
        ngay = r.get("published_date")
        c[ngay[:4] if ngay else "?"] += 1
    return c


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Soi kho đã tải về")
    ap.add_argument("kho", nargs="?", default="kho_chong_dong.json", type=Path)
    ap.add_argument("--dau", type=int, default=15, help="in bao nhiêu nhãn đầu bảng")
    a = ap.parse_args(argv)

    data = doc_kho(a.kho)
    br = data["ban_ghi"]
    tong_kho = data.get("kho_bao_co", 0)

    print("=" * 70)
    print(f"SOI KHO · {a.kho}")
    print("=" * 70)
    print(f"  Kho báo có   : {tong_kho:,}".replace(",", "."))
    print(f"  Có trong tệp : {len(br):,}".replace(",", "."))
    if tong_kho and len(br) < tong_kho:
        print(f"  ⚠ THIẾU {tong_kho - len(br):,} bản ghi — kho chưa đủ.".replace(",", "."))

    if not any("loai_bai_goc" in r for r in br):
        print("\n  ⚠ Tệp kho này KHÔNG có 'loai_bai_goc' — được tạo bởi bản cũ.")
        print("    Nhãn gốc đã bị vứt lúc tải, không soi được. Chạy lại quet_that.py.")
        return 1

    chua = [r for r in br if r.get("evidence_level") is None]
    print(f"\n  Chưa phân loại: {len(chua):,}".replace(",", "."), end="")
    print(f" ({len(chua) / len(br):.0%})" if br else "")

    print(f"\n{'─' * 70}\nNHÃN TRÊN CÁC BẢN GHI CHƯA PHÂN LOẠI\n{'─' * 70}")
    nhan_chua = nhan_cua_chua_phan_loai(br)
    if not nhan_chua:
        print("  (không có bản ghi nào chưa phân loại)")
    for n, s in nhan_chua.most_common(a.dau):
        print(f"  {n:<48}{s:>8,}".replace(",", "."))

    de_xuat = de_xuat_bo_sung(nhan_chua)
    print(f"\n{'─' * 70}\nĐỀ XUẤT CÂN NHẮC THÊM VÀO BẢNG XẾP BẬC\n{'─' * 70}")
    if de_xuat:
        for n, s in de_xuat[:a.dau]:
            print(f"  {n:<48}{s:>8,}".replace(",", "."))
        print("\n  KHÔNG tự thêm. Xếp bậc chứng cứ là phán đoán phương pháp luận,")
        print("  phải do người quyết. Đây chỉ là danh sách kèm số đếm để phán đoán")
        print("  đó dựa trên dữ liệu thật thay vì trí nhớ.")
    else:
        print("  Không nhãn nào đủ phổ biến mà chưa có trong bảng.")
        print("  Vậy 'chưa phân loại' chủ yếu là bài chỉ mang nhãn chung chung")
        print("  ('Journal Article'), tức là MEDLINE thật sự không nói gì về")
        print("  thiết kế nghiên cứu của chúng — không phải bảng của ta thiếu.")

    print(f"\n{'─' * 70}\nTOÀN KHO · {a.dau} nhãn phổ biến nhất\n{'─' * 70}")
    for n, s in dem_nhan(br).most_common(a.dau):
        co = "" if n.lower() in EVIDENCE_RANK else "  (không xếp bậc)"
        print(f"  {n:<40}{s:>8,}".replace(",", ".") + co)

    print(f"\n{'─' * 70}\nPHÂN BỐ NĂM\n{'─' * 70}")
    nam = phan_bo_nam(br)
    gan_day = sorted((k for k in nam if k.isdigit()), reverse=True)[:8]
    for k in gan_day:
        print(f"  {k}{nam[k]:>8,}".replace(",", "."))
    cu = sum(v for k, v in nam.items() if k.isdigit() and k < gan_day[-1]) if gan_day else 0
    if cu:
        print(f"  trước {gan_day[-1]}{cu:>4,}".replace(",", "."))

    trung = kiem_trung(br)
    print(f"\n{'─' * 70}\nKIỂM TRÙNG\n{'─' * 70}")
    if trung:
        print(f"  ⚠ {len(trung)} mã xuất hiện nhiều lần trong cùng kho:")
        for k, v in trung[:10]:
            print(f"      {k} × {v}")
    else:
        print("  ✓ Không mã nào lặp — phân trang cursor không nhả trùng.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

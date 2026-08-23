"""Soi truy vấn: tìm ĐÚNG mệnh đề nào làm truy vấn không ra kết quả.

    python3 tools/soi_truy_van.py
    python3 tools/soi_truy_van.py --ma 26095867

VÌ SAO CẦN TỆP NÀY:

Truy vấn Europe PMC đầu tiên cho độ nhạy 0/4 — sót cả bốn bài mồi. 0/4 quá
tuyệt đối để là "siết hơi quá tay"; nó là dấu hiệu một mệnh đề nào đó sai cú
pháp và kéo cả truy vấn về rỗng. Nhưng đoán xem mệnh đề nào thì tốn lượt thử
của người dùng, mà mỗi lượt thử là một vòng đi-về.

Nên thay vì đoán, ta ĐO. Với mỗi mệnh đề, hỏi Europe PMC hai câu:

  A. Mệnh đề này đứng MỘT MÌNH có ra kết quả nào không?
  B. Mệnh đề này AND với bài mồi đã biết có ra bài đó không?

Hai câu đó phân biệt được hai nguyên nhân hoàn toàn khác nhau — và đây là toàn
bộ giá trị của công cụ này:

  A=0            -> TÊN TRƯỜNG hoặc cú pháp SAI. Europe PMC không hiểu ta hỏi gì.
  A>0 nhưng B=0  -> Cú pháp ĐÚNG, nhưng bài mồi thật sự không mang thuộc tính đó.
                    Đây là phát hiện về DỮ LIỆU, không phải lỗi của ta.

Không tách được hai thứ này thì người sửa sẽ đi sửa cú pháp trong khi vấn đề
nằm ở giả định về dữ liệu, hoặc ngược lại.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.sources.europepmc import EuropePMCFetcher

# Từng mệnh đề của truy vấn, tách rời để soi riêng. Gồm cả các BIẾN THỂ TÊN
# TRƯỜNG đang nghi ngờ — vì nghi ngờ chính là thứ cần đo, không phải thứ để cãi.
MENH_DE_MAC_DINH: dict[str, str] = {
    "mesh (MESH:)":            'MESH:"Anticoagulants"',
    "mesh (MESH_HEADING:)":    'MESH_HEADING:"Anticoagulants"',
    "mesh (KW:)":              'KW:"Anticoagulants"',
    "loại bài (PUB_TYPE:)":    'PUB_TYPE:"Randomized Controlled Trial"',
    "loại bài (PUB_TYPE hoa)": 'PUB_TYPE:"randomized controlled trial"',
    "kho con (SRC:MED)":       "SRC:MED",
    "từ khoá trần":            "anticoagulants",
    "tiêu đề (TITLE:)":        'TITLE:"bridging"',
    "tóm tắt (ABSTRACT:)":     'ABSTRACT:"anticoagulation"',
    "năm (PUB_YEAR:)":         "PUB_YEAR:2015",
}


# Ba nhóm mệnh đề của truy vấn thật, tách rời để biết nhóm nào loại bài nào.
# Dùng KW: vì phép đo đã loại MESH: (đúng cú pháp nhưng không lôi được bài mồi).
NHOM_TRUY_VAN: dict[str, str] = {
    "thuốc chống đông": (
        'KW:"Anticoagulants" OR KW:"Warfarin" '
        'OR KW:"Heparin, Low-Molecular-Weight" OR KW:"Factor Xa Inhibitors" '
        "OR rivaroxaban OR apixaban OR dabigatran OR enoxaparin"
    ),
    "giai đoạn chu phẫu": (
        'KW:"Perioperative Care" OR KW:"Preoperative Care" '
        'OR KW:"Postoperative Care" OR KW:"Perioperative Period" '
        "OR perioperative OR bridging"
    ),
    "loại bài / bậc CC": (
        'PUB_TYPE:"Meta-Analysis" OR PUB_TYPE:"Systematic Review" '
        'OR PUB_TYPE:"Randomized Controlled Trial" '
        'OR PUB_TYPE:"Practice Guideline"'
    ),
    "kho MEDLINE": "SRC:MED",
}

# Nhãn ngắn để in thành bảng. Mô tả đầy đủ nằm ở do_nhay.MOI_CHONG_DONG.
NHAN_MOI: dict[str, str] = {
    "pubmed:26095867": "BRIDGE",
    "pubmed:34108229": "PERIOP2",
    "pubmed:36462533": "CHEST",
    "pubmed:40448969": "DOAC25",
}


@dataclass
class KetQua:
    ten: str
    menh_de: str
    mot_minh: int          # mệnh đề đứng riêng ra bao nhiêu kết quả
    voi_bai_moi: int       # AND với bài mồi ra bao nhiêu

    @property
    def chan_doan(self) -> str:
        if self.mot_minh == 0:
            return "✗ CÚ PHÁP SAI — Europe PMC không hiểu trường này"
        if self.voi_bai_moi == 0:
            return "△ cú pháp ĐÚNG, nhưng bài mồi không mang thuộc tính này"
        return "✓ dùng được"

    @property
    def hong(self) -> bool:
        return self.mot_minh == 0


def soi(f: EuropePMCFetcher, ma: str, menh_de: dict[str, str]) -> list[KetQua]:
    ra: list[KetQua] = []
    for ten, md in menh_de.items():
        try:
            _, mot_minh = f.quet_toan_bo(md, tran=1, page_size=1)
        except Exception:  # noqa: BLE001
            mot_minh = 0
        try:
            _, cung = f.quet_toan_bo(f"EXT_ID:{ma} AND ({md})", tran=1, page_size=1)
        except Exception:  # noqa: BLE001
            cung = 0
        ra.append(KetQua(ten, md, mot_minh, cung))
    return ra


def soi_nhom(f, moi: list[str], nhom: dict[str, str]) -> dict[str, dict[str, bool]]:
    """Lưới nhóm × bài mồi: nhóm nào loại mất bài nào.

    Soi từng mệnh đề riêng lẻ chỉ trả lời được 'cú pháp có đúng không'. Lưới này
    trả lời câu đắt hơn: sau khi cú pháp đã đúng, ĐIỀU KIỆN NÀO đang loại nhầm
    bài nền tảng. Đó thường là bộ lọc loại bài — vì nó dựa trên nhãn do người
    lập chỉ mục gán, mà nhãn thì không phải lúc nào cũng như ta đoán.
    """
    luoi: dict[str, dict[str, bool]] = {}
    for ten, md in nhom.items():
        hang: dict[str, bool] = {}
        for ma in moi:
            pmid = ma.rsplit(":", 1)[-1]
            try:
                _, n = f.quet_toan_bo(f"EXT_ID:{pmid} AND ({md})", tran=1, page_size=1)
            except Exception:  # noqa: BLE001
                n = 0
            hang[ma] = bool(n)
        luoi[ten] = hang
    return luoi


def in_luoi(luoi: dict[str, dict[str, bool]], moi: list[str]) -> list[str]:
    """In lưới và trả về danh sách nhóm có loại nhầm bài mồi."""
    nhan = [NHAN_MOI.get(m, m.rsplit(":", 1)[-1]) for m in moi]
    print(f"\n{'NHÓM MỆNH ĐỀ':<22}" + "".join(f"{n:>10}" for n in nhan))
    print("─" * (22 + 10 * len(nhan)))
    thu_pham: list[str] = []
    for ten, hang in luoi.items():
        o = "".join(f"{'✓' if hang[m] else '✗':>10}" for m in moi)
        print(f"{ten:<22}{o}")
        if not all(hang.values()):
            thu_pham.append(ten)

    qua_het = [m for m in moi if all(h[m] for h in luoi.values())]
    print("─" * (22 + 10 * len(nhan)))
    o = "".join(f"{'✓' if m in qua_het else '✗':>10}" for m in moi)
    print(f"{'TOÀN BỘ TRUY VẤN':<22}{o}")
    print(f"\n  Độ nhạy dự kiến: {len(qua_het)}/{len(moi)}")
    return thu_pham


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Soi từng mệnh đề của truy vấn")
    ap.add_argument("--ma", default="26095867", help="PMID bài mồi đã biết chắc có thật")
    a = ap.parse_args(argv)

    f = EuropePMCFetcher()

    print("=" * 74)
    print(f"SOI TRUY VẤN · bài mồi PMID {a.ma}")
    print("=" * 74)

    # Chốt tỉnh táo: bài mồi phải tự nó tra được, nếu không thì mọi so sánh
    # phía dưới đều vô nghĩa và ta sẽ đổ oan cho các mệnh đề.
    try:
        _, co = f.quet_toan_bo(f"EXT_ID:{a.ma}", tran=1, page_size=1)
    except Exception as exc:  # noqa: BLE001
        print(f"\n✗ Không gọi được Europe PMC: {type(exc).__name__}: {exc}")
        return 1
    if not co:
        print(f"\n✗ Không tra được bài mồi {a.ma}. Dừng — mọi kết quả dưới sẽ sai.")
        return 1
    print(f"\n✓ Bài mồi tra được (EXT_ID:{a.ma} ra {co} kết quả)\n")

    kq = soi(f, a.ma, MENH_DE_MAC_DINH)

    print(f"{'MỆNH ĐỀ':<26}{'RIÊNG':>12}{'+ BÀI MỒI':>12}  CHẨN ĐOÁN")
    print("─" * 74)
    for r in kq:
        rieng = f"{r.mot_minh:,}".replace(",", ".")
        print(f"{r.ten:<26}{rieng:>12}{r.voi_bai_moi:>12}  {r.chan_doan}")

    hong = [r for r in kq if r.hong]
    print("\n" + "─" * 74)
    if hong:
        print("MỆNH ĐỀ SAI CÚ PHÁP — đây là thứ kéo cả truy vấn về rỗng:")
        for r in hong:
            print(f"  ✗ {r.menh_de}")
    else:
        print("Không mệnh đề nào sai cú pháp.")
        print("Vậy 0/4 đến từ chỗ AND quá nhiều điều kiện cùng lúc, không phải cú pháp.")

    dung_duoc = [r for r in kq if not r.hong and r.voi_bai_moi]
    if dung_duoc:
        print("\nMỆNH ĐỀ DÙNG ĐƯỢC (lôi được bài mồi về):")
        for r in dung_duoc:
            print(f"  ✓ {r.menh_de}")

    print("\n" + "=" * 74)
    print("LƯỚI NHÓM × BÀI MỒI — nhóm nào đang loại nhầm bài nào")
    print("=" * 74)
    moi = list(NHAN_MOI)
    thu_pham = in_luoi(soi_nhom(f, moi, NHOM_TRUY_VAN), moi)
    if thu_pham:
        print("\n  NHÓM LOẠI NHẦM BÀI NỀN TẢNG — phải nới, không được siết thêm:")
        for t in thu_pham:
            print(f"    ✗ {t}")
        print("\n  Nhóm 'loại bài / bậc CC' hay là thủ phạm nhất: nó lọc theo nhãn")
        print("  do người lập chỉ mục gán, mà nhãn không phải lúc nào cũng như ta đoán.")
    else:
        print("\n  ✓ Không nhóm nào loại nhầm. Truy vấn ghép lại sẽ đạt độ nhạy đủ.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

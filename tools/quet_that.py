"""Quét TOÀN BỘ kho qua Europe PMC — SR-Agent tự làm, không nhờ ai chuyển thư.

    python3 tools/quet_that.py
    python3 tools/quet_that.py --truy-van '<chuỗi Europe PMC>' --ra kho.json

Chạy được từ máy Gun vì Europe PMC không chặn (đã kiểm chứng 2026-08-23).

TRÌNH TỰ CÓ CHỦ Ý — đo độ nhạy TRƯỚC khi quét:

  1. Lấy bài mồi  -> truy vấn có lôi về được bài nền tảng đã biết không?
  2. Nếu THỦNG    -> DỪNG. Không quét. Quét bằng truy vấn thủng chỉ tạo ra một
                     kho lớn trông đầy đủ mà thiếu đúng những bài quan trọng.
  3. Nếu ĐẠT      -> quét hết, báo độ phủ thật.

Bước 2 là lý do tồn tại của cả tệp này. Sai lầm dễ mắc nhất khi tối ưu truy vấn
là mừng vì số kết quả giảm, trong khi thứ vừa bị cắt mất là bài quan trọng nhất.

TỆP NÀY KHÔNG GHI PHIẾU SÀNG LỌC. Nó chỉ TẢI VỀ. 'Đã sàng' nghĩa là đã có người
hay máy đọc và ra quyết định giữ/loại từng bài — việc đó chưa xảy ra ở đây. Ghi
một phiếu khai 'đã sàng 1.767' khi mới chỉ tải về đúng là kiểu trường tự khai vô
căn cứ mà cả hệ thống này được dựng lên để chặn.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.do_nhay import MOI_CHONG_DONG, bao_cao, kiem_bai_moi
from tools.sources.europepmc import EuropePMCFetcher

# Truy vấn dịch sang cú pháp Europe PMC từ bản PubMed Spark đã chạy.
# HAI THAY ĐỔI CÓ CHỦ Ý, cả hai đều phải qua phép đo độ nhạy mới được nhận:
#   - BỎ  'surgery'      : quá rộng, đây là thứ kéo phình khối lượng lên 1.767
#   - THÊM MESH "Perioperative Period" : khái niệm này có MeSH chuẩn mà bản cũ bỏ sót
TRUY_VAN = (
    '(MESH:"Anticoagulants" OR MESH:"Warfarin" '
    'OR MESH:"Heparin, Low-Molecular-Weight" OR MESH:"Factor Xa Inhibitors" '
    'OR rivaroxaban OR apixaban OR dabigatran OR enoxaparin) '
    'AND (MESH:"Perioperative Care" OR MESH:"Preoperative Care" '
    'OR MESH:"Postoperative Care" OR MESH:"Perioperative Period" '
    'OR perioperative OR bridging) '
    'AND (PUB_TYPE:"Meta-Analysis" OR PUB_TYPE:"Systematic Review" '
    'OR PUB_TYPE:"Randomized Controlled Trial" OR PUB_TYPE:"Practice Guideline") '
    'AND SRC:MED'
)


def _muc(t: str) -> None:
    print(f"\n{'─' * 68}\n{t}\n{'─' * 68}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Quét toàn bộ kho qua Europe PMC")
    ap.add_argument("--truy-van", default=TRUY_VAN)
    ap.add_argument("--ra", default="kho_chong_dong.json", type=Path)
    ap.add_argument("--tran", type=int, default=5000)
    ap.add_argument("--bo-qua-do-nhay", action="store_true",
                    help="quét dù truy vấn thủng — chỉ dùng khi đang thử nghiệm")
    a = ap.parse_args(argv)

    f = EuropePMCFetcher()

    _muc("BƯỚC 1 — ĐO ĐỘ NHẠY BẰNG BÀI MỒI")
    print(f"  Đang lấy {len(MOI_CHONG_DONG)} bài mồi để xem truy vấn có lôi về được...")
    try:
        moi_docs, _ = f.quet_toan_bo(
            f"({a.truy_van}) AND ("
            + " OR ".join(f"EXT_ID:{m.split(':')[-1]}" for m in MOI_CHONG_DONG)
            + ")",
            tran=50,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ Không gọi được Europe PMC: {type(exc).__name__}")
        print(f"    {str(exc).splitlines()[0]}")
        return 1

    kq = kiem_bai_moi([d.source_id for d in moi_docs])
    print()
    print(bao_cao(kq, "truy vấn Europe PMC"))

    if not kq.dat and not a.bo_qua_do_nhay:
        print()
        print("  DỪNG — không quét bằng truy vấn thủng.")
        print("  Sửa truy vấn cho tới khi lấy đủ bài mồi, rồi chạy lại.")
        print("  (Muốn quét thử bất chấp: thêm --bo-qua-do-nhay)")
        return 1

    _muc("BƯỚC 2 — QUÉT TOÀN BỘ KHO")
    docs, tong = f.quet_toan_bo(a.truy_van, tran=a.tran)
    phu = len(docs) / tong if tong else 0.0

    print(f"  Kho báo có       : {tong:,}".replace(",", "."))
    print(f"  Đã TẢI VỀ được   : {len(docs):,}".replace(",", "."))
    print(f"  Độ phủ tải về    : {phu:.1%}")
    if len(docs) < tong:
        print(f"  ⚠ Thiếu {tong - len(docs)} bản ghi — chạm trần {a.tran}? Tăng --tran.")

    _muc("BƯỚC 3 — PHÂN BỐ BẬC CHỨNG CỨ")
    bac: dict[int | None, int] = {}
    for d in docs:
        bac[d.evidence_level] = bac.get(d.evidence_level, 0) + 1
    ten = {1: "phân tích gộp", 2: "tổng quan hệ thống", 3: "RCT / hướng dẫn",
           4: "hướng dẫn", 5: "thử nghiệm lâm sàng", 6: "quan sát", 7: "tổng quan"}
    for k in sorted(bac, key=lambda x: (x is None, x)):
        nhan = "CHƯA PHÂN LOẠI" if k is None else f"bậc {k} — {ten.get(k, '')}"
        print(f"  {nhan:<34} {bac[k]:>5}")
    if None in bac:
        print("\n  'Chưa phân loại' KHÁC 'bậc thấp'. Không được gộp hai thứ này.")

    a.ra.write_text(json.dumps(
        {"truy_van": a.truy_van, "kho_bao_co": tong, "da_tai_ve": len(docs),
         "ban_ghi": [d.model_dump(mode="json") for d in docs]},
        ensure_ascii=False, indent=2), encoding="utf-8")

    _muc("KẾT LUẬN")
    print(f"  Đã ghi {len(docs)} bản ghi vào {a.ra}")
    print(f"  Độ nhạy bài mồi : {kq.do_nhay:.0%}")
    print(f"  Độ phủ tải về   : {phu:.1%}")
    print()
    print("  Đây là bước TẢI VỀ, chưa phải sàng lọc. Chưa bài nào được đọc và")
    print("  ra quyết định giữ/loại — đừng ghi vào đâu là 'đã sàng'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

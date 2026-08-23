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
#
# DÙNG 'KW:' CHỨ KHÔNG PHẢI 'MESH:' — quyết định này do phép đo, không do phán
# đoán. Bản đầu dùng MESH: và cho độ nhạy 0/4. tools/soi_truy_van.py chỉ ra vì
# sao, và đây là ca tinh vi: MESH:"Anticoagulants" KHÔNG sai cú pháp (đứng riêng
# ra 4.814 kết quả) nhưng KHÔNG lôi được BRIDGE về. Cùng từ khoá đó, KW: ra
# 100.177 — chênh 20 lần. Chỉ mục MESH: của Europe PMC không phải MeSH heading
# của MEDLINE như đã giả định.
#
# ĐÁNH ĐỔI, nói thẳng: KW gồm cả từ khoá tác giả lẫn thuật ngữ chỉ mục, nên RỘNG
# hơn và KÉM CHÍNH XÁC hơn MeSH thật. Với vòng sàng lọc thứ nhất thì đây là chiều
# đánh đổi đúng — thà nhận thêm bài phải loại tay, còn hơn bỏ sót bài mà không ai
# biết là đã bỏ sót. Bài bị loại có vết; bài chưa từng thấy thì không.
#
# BỎ HẲN BỘ LỌC PUB_TYPE KHỎI TRUY VẤN TÌM KIẾM — sai chỗ, không phải sai giá trị.
#
# Bản trước có AND (PUB_TYPE:"Meta-Analysis" OR ... OR "Practice Guideline"), tức
# là biến thiết kế nghiên cứu thành ĐIỀU KIỆN LOẠI TRỪ NGAY Ở CỬA TÌM KIẾM. Ba lý
# do khiến chỗ đó là sai chỗ:
#
#   1. Nhãn loại bài do người lập chỉ mục gán, và gán KHÔNG đều. Một hướng dẫn
#      thực hành có thể chỉ mang nhãn 'Journal Article'. Lọc theo nhãn ở cửa tìm
#      nghĩa là bài bị loại vì CÁCH NÓ ĐƯỢC DÁN NHÃN, không phải vì nó là gì.
#   2. Bài bị loại ở cửa tìm thì KHÔNG ĐỂ LẠI VẾT. Nó không nằm trong tử số lẫn
#      mẫu số, không vào sơ đồ PRISMA, không ai biết nó từng tồn tại. Còn bài bị
#      loại ở vòng sàng thì có mã, có lý do, đếm được.
#   3. Ta ĐÃ CÓ sẵn bộ phân loại thiết kế nghiên cứu tốt hơn: evidence_level đọc
#      từ pubTypeList của từng bản ghi. Nó xếp hạng mà không vứt bỏ, và phân biệt
#      'chưa phân loại' với 'phân loại là yếu'.
#
# Nên bậc chứng cứ chuyển vai: từ ĐIỀU KIỆN LOẠI TRỪ lúc tìm -> TIÊU CHÍ XẾP HẠNG
# lúc sàng. Cái giá là kho to hơn. Nhưng kho to chưa bao giờ là vấn đề kể từ khi
# quét được cả kho trong 2 request — nút thắt nằm ở đường truyền, không ở khối lượng.
TRUY_VAN = (
    '(KW:"Anticoagulants" OR KW:"Warfarin" '
    'OR KW:"Heparin, Low-Molecular-Weight" OR KW:"Factor Xa Inhibitors" '
    'OR rivaroxaban OR apixaban OR dabigatran OR enoxaparin) '
    'AND (KW:"Perioperative Care" OR KW:"Preoperative Care" '
    'OR KW:"Postoperative Care" OR KW:"Perioperative Period" '
    'OR perioperative OR bridging) '
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
        # TỰ CHẨN ĐOÁN NGAY, không bắt người dùng chạy thêm một lệnh nữa. Công cụ
        # nào dừng thì phải nói luôn vì sao nó dừng; báo 'thủng' rồi im lặng chỉ
        # đẩy thêm một vòng đi-về mà thông tin thì hệ thống đã có sẵn trong tay.
        print("  Đang soi xem nhóm mệnh đề nào loại nhầm bài mồi...")
        try:
            from tools.soi_truy_van import NHAN_MOI, NHOM_TRUY_VAN, in_luoi, soi_nhom
            ds = list(NHAN_MOI)
            thu_pham = in_luoi(soi_nhom(f, ds, NHOM_TRUY_VAN), ds)
            if thu_pham:
                print("\n  NHÓM LOẠI NHẦM BÀI NỀN TẢNG:")
                for t in thu_pham:
                    print(f"    ✗ {t}")
        except Exception as exc:  # noqa: BLE001
            print(f"  (không soi được: {type(exc).__name__})")
        print("\n  Sửa truy vấn cho tới khi lấy đủ bài mồi, rồi chạy lại.")
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

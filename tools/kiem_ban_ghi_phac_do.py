"""Chạy tường lửa số trên bản ghi phác đồ — cơ chế [8] của SO_CO_CHE, nay có đường chạy thật.

VÌ SAO CÓ TỆP NÀY

`docs/SO_CO_CHE.md` vẽ [8] tường lửa số đứng chắn ngay trước AnesthOS. Nhưng
`check_output` chỉ được gọi từ `demo/`, `docs/audit/` và `tests/` — KHÔNG đường chạy sản
xuất nào gọi nó. Nghĩa là bản đồ cơ chế đang mô tả một tầng bảo vệ không tồn tại trên
đường đi của dữ liệu: 36 bản ghi thuốc tê, gồm cả liều nhũ tương lipid cấp cứu LAST,
chưa qua bất kỳ phép neo số nào.

Bản ghi phác đồ là chỗ ĐÚNG để đặt tường lửa: nó là nơi duy nhất hiện có mà một khẳng
định (`khang_dinh`) nằm cạnh nguyên văn nguồn của chính nó (`trich_nguyen_van`). Sổ phụ
bằng chứng (`so_phu_bang_chung.py`) KHÔNG phải chỗ đó — nó quét dữ liệu AnesthOS và
không cầm theo nguyên văn nguồn nào để đối chiếu.

BA TRẠNG THÁI, KHÔNG PHẢI HAI (luật L3)

`check_output` trả `passed=True` cho khẳng định không bóc được mỏ neo nào (ví dụ
`"one-third"`, `"CNS symptoms usually present first"`). Đó là "không kiểm được", không
phải "đạt". Bộ kiểm này tách hẳn ra:

    ĐẠT        mọi mỏ neo số đều tìm thấy nguyên văn trong nguồn
    TRƯỢT      có mỏ neo không tìm thấy trong nguồn
    VÔ HIỆU    không bóc được mỏ neo nào, hoặc bản ghi không mang nguyên văn nguồn

Gộp VÔ HIỆU vào ĐẠT chính là kiểu hỏng cả dự án dựng lên để chặn.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.guard.firewall import check_output  # noqa: E402

DAT = "ĐẠT"
TRUOT = "TRƯỢT"
VO_HIEU = "VÔ HIỆU"


def kiem_mot_ban_ghi(ban_ghi: dict) -> tuple[str, str]:
    """Trả (trạng thái, lý do) cho một bản ghi phác đồ."""
    khang_dinh = str(ban_ghi.get("khang_dinh") or "").strip()
    nguyen_van = ban_ghi.get("trich_nguyen_van")

    if not khang_dinh:
        return VO_HIEU, "bản ghi không có khẳng định"
    if not nguyen_van or not str(nguyen_van).strip():
        # Sau khi gỡ nguyên văn nguồn thương mại khỏi kho (ràng buộc C4), trường này
        # còn lại toạ độ + băm. Khi đó phép neo phải chạy trên máy Gun, nơi có nguyên
        # văn — ở đây khai VÔ HIỆU chứ không khai ĐẠT.
        return VO_HIEU, "bản ghi không mang nguyên văn nguồn để đối chiếu"

    ket = check_output(khang_dinh, [str(nguyen_van)], domain="clinical", strict=True)
    if ket.anchors_checked == 0:
        return VO_HIEU, f"không bóc được mỏ neo số nào từ {khang_dinh!r}"
    if not ket.passed:
        ly_do = "; ".join(v.reason for v in ket.violations)
        return TRUOT, ly_do
    return DAT, f"{ket.anchors_checked} mỏ neo khớp nguyên văn"


def chay(duong_dan: Path) -> int:
    # Luật L7: in NGUỒN DỮ LIỆU trước mọi con số khác.
    duong_dan = duong_dan.resolve()
    print(f"NGUỒN DỮ LIỆU : {duong_dan}")
    if not duong_dan.is_file():
        print("KẾT LUẬN      : VÔ HIỆU — không đọc được tệp")
        return 2

    ban_ghi = json.loads(duong_dan.read_text(encoding="utf-8"))
    if not isinstance(ban_ghi, list):
        print("KẾT LUẬN      : VÔ HIỆU — tệp không phải danh sách bản ghi")
        return 2
    print(f"SỐ BẢN GHI    : {len(ban_ghi)}")
    print()

    dem = {DAT: 0, TRUOT: 0, VO_HIEU: 0}
    for i, r in enumerate(ban_ghi):
        trang_thai, ly_do = kiem_mot_ban_ghi(r)
        dem[trang_thai] += 1
        if trang_thai != DAT:
            ma = r.get("ma_doi_chieu") or r.get("diem_quyet_dinh") or f"#{i}"
            print(f"  [{trang_thai}] {ma}: {ly_do}")

    print()
    print(f"ĐẠT     : {dem[DAT]}")
    print(f"TRƯỢT   : {dem[TRUOT]}")
    print(f"VÔ HIỆU : {dem[VO_HIEU]}")

    if dem[TRUOT]:
        print("\nKẾT LUẬN: TRƯỢT — có con số không neo được vào nguồn.")
        return 1
    if dem[VO_HIEU]:
        print("\nKẾT LUẬN: CHƯA KẾT LUẬN ĐƯỢC — còn bản ghi VÔ HIỆU, cần người xem.")
        return 3
    print("\nKẾT LUẬN: ĐẠT — mọi mỏ neo số đều khớp nguyên văn.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chạy tường lửa số trên bản ghi phác đồ")
    ap.add_argument("tep", type=Path, help="tệp JSON bản ghi phác đồ")
    args = ap.parse_args(argv)
    return chay(args.tep)


if __name__ == "__main__":
    sys.exit(main())

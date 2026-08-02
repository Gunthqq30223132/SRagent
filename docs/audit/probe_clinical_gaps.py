#!/usr/bin/env python3
"""Probe kiểm toán — CHỨNG MINH bằng thực nghiệm các lỗ hổng của guard hiện tại.

KHÔNG PHẢI test suite. Đây là tang chứng tái lập được cho D32 (audit kiến trúc).
Script này CỐ Ý cho thấy guard hiện tại LỌT các mẫu tấn công lâm sàng — nó
in ra bảng kết quả và luôn exit 0. Khi các khuyến nghị D32 được hiện thực,
chuyển các ca này thành test thật trong tests/ (kỳ vọng đảo lại: phải CHẶN).

Chạy:  python docs/audit/probe_clinical_gaps.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.guard.firewall import check_output, extract_anchors  # noqa: E402
from tools.guard.outbound import scan  # noqa: E402

# (nhãn, đầu ra LLM, nguồn thật của Lớp A, có PHẢI bị chặn không)
FIREWALL_CASES: list[tuple[str, str, list[str], bool]] = [
    ("A. Liều đơn thuần mg/kg",
     "Khởi mê propofol 2 mg/kg tĩnh mạch chậm.",
     ["Khởi mê propofol 1.5 mg/kg tĩnh mạch chậm."], True),
    ("B. Range hole '2-3 mcg/kg' (cận dưới bịa)",
     "Liều fentanyl 2-3 mcg/kg.",
     ["Liều fentanyl 3 mcg/kg."], True),
    ("C. Range hole khoảng thời gian",
     "Dùng kháng sinh 5-10 ngày.",
     ["Dùng kháng sinh 10 ngày."], True),
    ("D. Số viết bằng chữ",
     "Tiêm hai mg midazolam.",
     ["Tiêm 1 mg midazolam."], True),
    ("E. Substring: '5 mg' khớp nhầm vào '25 mg'",
     "Liều tối đa 5 mg.",
     ["Liều tối đa 25 mg."], True),
    ("F. Substring: '9.9%' khớp nhầm vào '99.9%'",
     "Độ bão hòa 9.9%.",
     ["Độ bão hòa đạt 99.9% ở nhóm chứng."], True),
    ("G. Sai đơn vị mg <-> mcg (lệch 1000 lần)",
     "Adrenaline 1 mg/kg.",
     ["Adrenaline 1 mcg/kg."], True),
    ("H. Nhiễm chéo nguồn (số của tài liệu B gán cho A)",
     "Theo [A], liều là 8 mg.",
     ["Tài liệu A: liều là 4 mg.", "Tài liệu B, chủ đề khác: 8 mg."], True),
    ("I. Đảo cực ngữ nghĩa (số đúng, nghĩa ngược)",
     "KHÔNG được vượt quá 3 mg/kg.",
     ["Được phép dùng tới 3 mg/kg."], True),
    ("Z. CHỨNG DƯƠNG: hằng số kỹ thuật (ca gốc của repo)",
     "Chạy trên port 8081 với O(n²).",
     ["Chạy trên port 8080 với O(n log n)."], True),
]

PHI_PROBES: list[str] = [
    "MSBA 1234567",
    "BHYT DN4010112345678",
    "Nguyễn Văn A, 67 tuổi, nam",
    "ĐT bàn 02838221234",
    "vào viện 12/03/2026",
    "giường 12 khoa GMHS",
    "chẩn đoán u trung thất hiếm gặp",
]


def run_firewall_probe() -> int:
    print("\n" + "=" * 92)
    print("PROBE 1 — Numeric Firewall V24 trước các mẫu số liệu LÂM SÀNG")
    print("=" * 92)
    print(f"{'CA KIỂM THỬ':<52}{'#anchor':>8}  {'KẾT QUẢ':<9}{'ĐÁNH GIÁ'}")
    print("-" * 92)
    holes = 0
    for name, out, srcs, should_block in FIREWALL_CASES:
        verdict = check_output(out, srcs, strict=True)
        blocked = not verdict.passed
        ok = blocked == should_block
        holes += 0 if ok else 1
        print(f"{name:<52}{verdict.anchors_checked:>8}  "
              f"{'CHẶN' if blocked else 'LỌT QUA':<9}"
              f"{'đúng' if ok else '<<< LỖ HỔNG'}")
    print("-" * 92)
    print(f"Lỗ hổng: {holes}/{len(FIREWALL_CASES)}")
    print("\nBóc anchor từ 'Liều fentanyl 2-3 mcg/kg' ->",
          [(a.kind, a.raw) for a in extract_anchors("Liều fentanyl 2-3 mcg/kg.")]
          or "[] (KHÔNG bóc được anchor nào)")
    print("Bóc anchor từ 'propofol 2 mg/kg'         ->",
          [(a.kind, a.raw) for a in extract_anchors("propofol 2 mg/kg")]
          or "[] (KHÔNG bóc được anchor nào)")
    return holes


def run_phi_probe() -> int:
    print("\n" + "=" * 92)
    print("PROBE 2 — Outbound Interceptor trước PHI lâm sàng free-text (G2 De-ID)")
    print("=" * 92)
    note = (
        "BN Nguyễn Văn A, 67 tuổi, nam, MSBA 1234567, giường 12 khoa GMHS, "
        "BHYT DN4010112345678, vào viện 12/03/2026, chẩn đoán u trung thất hiếm gặp, "
        "ĐT bàn 02838221234. Người nhà: ông Nguyễn Văn B, 12 Lê Lợi, Q1."
    )
    findings = scan(note)
    print("Bệnh án mẫu (1 đoạn free-text đầy đủ PHI):")
    print(f"  {note}")
    print(f"\n  -> findings = {[f.rule_id for f in findings] or 'RỖNG — KHÔNG BẮT ĐƯỢC GÌ'}")
    print("\nTách từng trường PHI:")
    missed = 0
    for probe in PHI_PROBES:
        rules = [f.rule_id for f in scan(probe)]
        missed += 0 if rules else 1
        print(f"  {probe:<40} -> {rules or 'LỌT'}")
    print("-" * 92)
    print(f"Trường PHI lọt lưới: {missed}/{len(PHI_PROBES)}")
    return missed


if __name__ == "__main__":
    holes = run_firewall_probe()
    missed = run_phi_probe()
    print("\n" + "=" * 92)
    print(f"TỔNG KẾT: {holes} lỗ hổng firewall, {missed} trường PHI lọt lưới.")
    print("Chi tiết & khuyến nghị: docs/specs/D32-architecture-audit-blindspots.md")
    print("=" * 92)
    sys.exit(0)  # probe kiểm toán — không bao giờ làm đỏ CI

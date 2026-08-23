"""Thử kết nối PubMed thật — chạy được là hệ thống đã đọc được y văn.

    .venv/bin/python demo/thu_pubmed.py
    .venv/bin/python demo/thu_pubmed.py "warfarin neuraxial anesthesia"

KHÔNG cần Ollama, KHÔNG cần khoá API — PubMed miễn phí và không đòi đăng ký.
Đây là mảnh rẻ nhất của First Light, tách ra chạy riêng được.

Mọi lỗi đều in ra bằng tiếng Việt kèm cách khắc phục, không ném vết lỗi Python
thô — người chạy lệnh này không nhất thiết phải đọc được traceback.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CHU_DE_MAC_DINH = "perioperative anticoagulation management"


def main() -> int:
    chu_de = sys.argv[1] if len(sys.argv) > 1 else CHU_DE_MAC_DINH

    try:
        from tools.sources.pubmed import PubMedFetcher
    except ImportError as exc:
        print("✗ Không nạp được mã nguồn.")
        print(f"  Chi tiết: {exc}")
        print("  Khắc phục: chạy lệnh này TỪ THƯ MỤC GỐC của repo SRagent.")
        return 1

    print(f"Chủ đề tìm : {chu_de}")
    print("Đang hỏi PubMed...\n")

    fetcher = PubMedFetcher()
    try:
        ids = fetcher.search(chu_de, max_results=5)
    except Exception as exc:  # noqa: BLE001 - gom mọi lỗi để in thân thiện
        print("✗ KHÔNG KẾT NỐI ĐƯỢC PubMed.")
        print(f"  Chi tiết kỹ thuật: {type(exc).__name__}: {exc}")
        print()
        print("  Ba nguyên nhân thường gặp, thử theo thứ tự:")
        print("   1. Máy chưa vào được mạng — thử mở pubmed.ncbi.nlm.nih.gov trên trình duyệt.")
        print("   2. Mạng bệnh viện chặn — thử lại bằng mạng 4G điện thoại.")
        print("   3. PubMed đang bận — chờ vài phút rồi chạy lại.")
        return 1

    if not ids:
        print("⚠ Kết nối được nhưng không có bài nào khớp. Thử đổi từ khoá tiếng Anh.")
        return 0

    print(f"✓ KẾT NỐI ĐƯỢC. Tìm thấy {len(ids)} bài. Đang tải chi tiết...\n")

    try:
        docs = fetcher.fetch(ids)
    except Exception as exc:  # noqa: BLE001
        print(f"✗ Tìm được ID nhưng tải chi tiết lỗi: {type(exc).__name__}: {exc}")
        return 1

    ten_bac = {1: "Phân tích gộp", 2: "Tổng quan hệ thống", 3: "Thử nghiệm ngẫu nhiên",
               4: "Hướng dẫn", 5: "Thử nghiệm lâm sàng", 6: "Nghiên cứu quan sát",
               7: "Tổng quan tường thuật", 9: "Báo cáo ca"}

    for i, d in enumerate(docs, 1):
        bac = d.evidence_level
        nhan = ten_bac.get(bac, "chưa phân loại") if bac else "chưa phân loại"
        nam = d.published_date.year if d.published_date else "?"
        print(f"{i}. [{nhan}] {nam}")
        print(f"   {d.title[:88]}")
        print(f"   {d.url}")
        so_tu = len((d.abstract or "").split())
        print(f"   Tóm tắt: {so_tu} từ\n")

    print("=" * 62)
    print("✓ XONG. Hệ thống đã đọc được y văn thật từ PubMed.")
    print("  Đây là lần đầu SR-Agent chạm dữ liệu y khoa sống.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

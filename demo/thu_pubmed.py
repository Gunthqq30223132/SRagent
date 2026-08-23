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


def chan_doan() -> int:
    """In NGUYÊN VĂN thứ NCBI trả về, không diễn giải gì.

    Có mặt vì lần chạy thật đầu tiên thất bại mà thông điệp lỗi lại giấu mất
    thân phản hồi — thứ duy nhất đủ để biết nguyên nhân. Một vòng thử bị mất
    vì lý do đó là một vòng quá nhiều.
    """
    import httpx

    from tools.sources.pubmed import ESEARCH

    print("=" * 64)
    print("CHẨN ĐOÁN KẾT NỐI PubMed — gửi toàn bộ kết quả này cho Claude")
    print("=" * 64)

    params = {"db": "pubmed", "term": "anticoagulation", "retmax": "2",
              "tool": "sr-agent"}
    print(f"\nĐịa chỉ gọi : {ESEARCH}")
    print(f"Tham số     : {params}")

    for nhan, headers in (
        ("CÓ User-Agent", {"User-Agent": "sr-agent/0.1"}),
        ("KHÔNG User-Agent", {}),
    ):
        print(f"\n--- Thử {nhan} ---")
        try:
            with httpx.Client(timeout=30, follow_redirects=True,
                              headers=headers) as c:
                r = c.get(ESEARCH, params=params)
            print(f"  Mã HTTP        : {r.status_code}")
            print(f"  Kiểu nội dung  : {r.headers.get('content-type', '(không có)')}")
            print(f"  Nén            : {r.headers.get('content-encoding', '(không nén)')}")
            print(f"  Độ dài thân    : {len(r.content)} byte")
            print(f"  Số lần chuyển hướng: {len(r.history)}")
            for h in r.history:
                print(f"    -> {h.status_code} {h.headers.get('location', '')}")
            print(f"  400 ký tự đầu  :\n{r.text[:400]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {type(exc).__name__}: {exc}")

    print("\n--- Biến môi trường proxy ---")
    import os
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
        print(f"  {k:<14} = {os.environ.get(k) or '(không đặt)'}")

    print("\n" + "=" * 64)
    return 0


def main() -> int:
    if "--chan-doan" in sys.argv:
        return chan_doan()
    chu_de = sys.argv[1] if len(sys.argv) > 1 else CHU_DE_MAC_DINH

    try:
        from tools.sources.pubmed import PubMedFetcher
    except ImportError as exc:
        print("✗ Không nạp được mã nguồn.")
        print(f"  Chi tiết: {exc}")
        print("  Khắc phục: chạy lệnh này TỪ THƯ MỤC GỐC của repo SRagent.")
        return 1

    import os

    fetcher = PubMedFetcher()
    print(f"Chủ đề tìm : {chu_de}")
    print(f"NCBI_EMAIL : {os.getenv('NCBI_EMAIL') or '⚠ CHƯA ĐIỀN — NCBI sẽ chặn'}")
    print(f"NCBI_API_KEY: {'đã có' if os.getenv('NCBI_API_KEY') else '(chưa có, không bắt buộc)'}")

    if not os.getenv("NCBI_EMAIL"):
        print()
        print("⚠ THIẾU EMAIL — gần như chắc chắn sẽ bị NCBI chặn.")
        print("  Chính sách NCBI đòi mọi truy vấn tự động phải kèm email liên hệ.")
        print("  Mở tệp .env trong thư mục này, thêm dòng:")
        print("      NCBI_EMAIL=email-cua-anh@gmail.com")
        print("  rồi chạy lại lệnh này.")
        print()

    print("Đang hỏi PubMed...\n")
    try:
        ids = fetcher.search(chu_de, max_results=5)
    except Exception as exc:  # noqa: BLE001 - gom mọi lỗi để in thân thiện
        print("✗ KHÔNG LẤY ĐƯỢC KẾT QUẢ TỪ PubMed.")
        print(f"  Chi tiết kỹ thuật: {type(exc).__name__}: {exc}")
        print()
        print("  Ba nguyên nhân thường gặp, thử theo thứ tự:")
        print("   1. Máy chưa vào được mạng — thử mở pubmed.ncbi.nlm.nih.gov trên trình duyệt.")
        print("   2. Mạng chặn — thử lại bằng mạng 4G điện thoại.")
        print("   3. PubMed đang bận — chờ vài phút rồi chạy lại.")
        print()
        print("  Nếu vẫn lỗi, chạy lệnh CHẨN ĐOÁN rồi gửi tôi toàn bộ kết quả:")
        print("     .venv/bin/python demo/thu_pubmed.py --chan-doan")
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

"""Cổng kiểm định: đọc hàng đợi Spark → xác minh → báo cáo PRISMA.

    python3 tools/kiem_dinh.py <thư-mục-hàng-đợi>
    python3 tools/kiem_dinh.py ~/Library/CloudStorage/GoogleDrive-<email>/My\\ Drive/0.\\ AnesthOs/hang_doi

BA TẦNG KIỂM, TÁCH RIÊNG CÓ CHỦ Ý:
  Tầng 1 — CẤU TRÚC: phiếu có hợp lệ không (số học, định dạng ID, truy vấn thật).
           Chạy được offline, luôn chạy.
  Tầng 2 — ĐỘ PHỦ : lần quét này phủ bao nhiêu phần kho? Đây là chỗ phân biệt
           "tổng quan hệ thống" với "danh sách đọc". Cũng chạy offline.
  Tầng 3 — NỘI DUNG: từng ID có thật không, có đúng bài đó không. CẦN MẠNG.

Tách ba tầng vì tầng 1-2 cho kết luận ngay cả khi tầng 3 chưa chạy được, và vì
một phiếu hỏng cấu trúc thì không đáng tốn lượt gọi mạng nào để kiểm nội dung.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.sources.hang_doi import KetQuaDoc, PhieuQuet, doc_hang_doi, kiem_do_tuoi

# Dưới ngưỡng này, lần quét là MẪU chứ không phải sàng lọc hệ thống.
# 10% là mốc rộng rãi; tổng quan hệ thống thật thường sàng 100% tiêu đề.
NGUONG_DO_PHU = 0.10


def _muc(text: str) -> None:
    print(f"\n{'─' * 68}\n{text}\n{'─' * 68}")


def tang1_cau_truc(kq: KetQuaDoc) -> bool:
    _muc("TẦNG 1 — CẤU TRÚC PHIẾU")
    print(f"  Phiếu hợp lệ : {len(kq.phieu_hop_le)}")
    print(f"  Phiếu bị từ chối: {len(kq.phieu_hong)}")
    for ten, ly_do in kq.phieu_hong:
        print(f"    ✗ {ten}: {ly_do}")
    canh_bao = kiem_do_tuoi(kq)
    if canh_bao:
        print(f"  ⚠ {canh_bao}")
    return bool(kq.phieu_hop_le)


def tang2_do_phu(phieu: PhieuQuet) -> None:
    """Đo phần kho ĐÃ ĐƯỢC NHÌN, không phải phần được giữ.

    TẠI SAO ĐÂY LÀ TẦNG RIÊNG: chất lượng bài giữ lại có thể xuất sắc trong khi
    độ phủ vẫn gần bằng không — và tuyên bố của một bài tổng quan hệ thống là
    tuyên bố về TOÀN BỘ kho, không phải về chất lượng phần đã xem. Trộn hai thứ
    này là cách một danh sách đọc tự nhận là tổng quan hệ thống.
    """
    _muc(f"TẦNG 2 — ĐỘ PHỦ · {phieu.ma_phieu}")
    tho, sang = phieu.so_ket_qua_tho, phieu.so_da_sang
    ty_le = sang / tho if tho else 0.0
    chua_xem = tho - sang

    print(f"  Truy vấn trả về      : {tho:,}".replace(",", "."))
    print(f"  Đã sàng              : {sang}")
    print(f"  CHƯA AI NHÌN         : {chua_xem:,}".replace(",", "."))
    print(f"  Độ phủ               : {ty_le:.2%}")
    print()
    if ty_le < NGUONG_DO_PHU:
        print(f"  ⚠ DƯỚI NGƯỠNG {NGUONG_DO_PHU:.0%} — đây là MẪU, không phải sàng lọc hệ thống.")
        print("    Bài giữ lại có thể rất tốt, nhưng chúng đến từ thứ tự xếp hạng")
        print("    liên quan của PubMed, không phải từ việc xem hết kho.")
        print("    Chưa dựng được sơ đồ PRISMA từ lần quét này.")
    else:
        print(f"  ✓ Đạt ngưỡng độ phủ {NGUONG_DO_PHU:.0%}.")


def tang3_noi_dung(phieu: PhieuQuet) -> None:
    """Tải bản gốc từ nguồn và đối chiếu. Spark là trinh sát, không phải nguồn."""
    _muc(f"TẦNG 3 — XÁC MINH NỘI DUNG · {len(phieu.ids)} mã")
    if phieu.nguon != "pubmed":
        print(f"  (bỏ qua: chưa có bộ xác minh cho nguồn {phieu.nguon!r})")
        return

    from tools.sources.pubmed import PubMedFetcher

    fetcher = PubMedFetcher()
    try:
        docs = fetcher.fetch(phieu.ids)
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ CHƯA XÁC MINH ĐƯỢC: {type(exc).__name__}")
        print(f"    {str(exc).splitlines()[0]}")
        print()
        print("    Tầng 1 và 2 ở trên VẪN CÓ GIÁ TRỊ — chúng không cần mạng.")
        print("    Nhưng chừng nào tầng 3 chưa chạy, mọi ID trong phiếu vẫn chỉ là")
        print("    LỜI KHAI của Spark, chưa phải dữ kiện. Không được dùng làm chứng cứ.")
        return

    tim_thay = {d.source_id for d in docs}
    thieu = [i for i in phieu.ids if i not in tim_thay]
    for d in docs:
        nam = d.published_date.year if d.published_date else "?"
        print(f"  ✓ {d.source_id:<18} [{nam}] bậc CC={d.evidence_level}")
        print(f"      {d.title[:74]}")
    for i in thieu:
        print(f"  ✗ {i:<18} KHÔNG TỒN TẠI trên PubMed — mã bịa hoặc gõ sai")
    print()
    print(f"  Xác minh được: {len(docs)}/{len(phieu.ids)}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    thu_muc = Path(sys.argv[1]).expanduser()

    print("=" * 68)
    print("CỔNG KIỂM ĐỊNH HÀNG ĐỢI SPARK")
    print(f"Thư mục: {thu_muc}")
    print("=" * 68)

    kq = doc_hang_doi(thu_muc)
    if not tang1_cau_truc(kq):
        print("\nKhông có phiếu hợp lệ — dừng, không tốn lượt gọi mạng nào.")
        return 1

    for phieu in kq.phieu_hop_le:
        tang2_do_phu(phieu)
        tang3_noi_dung(phieu)

    _muc("KẾT LUẬN")
    print(f"  Phiếu đọc được : {len(kq.phieu_hop_le)}")
    print(f"  Tổng mã đề cử  : {kq.tong_id}")
    print("  Trạng thái     : mã ĐỀ CỬ, chưa phải chứng cứ. Cần qua đủ 3 tầng.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

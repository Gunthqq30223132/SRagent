"""Chạy nhiều câu hỏi nghiên cứu trong MỘT lệnh, kèm phép đo khởi động lạnh.

    python3 tools/chay_cau_hoi.py                          # 3 câu ưu tiên 1
    python3 tools/chay_cau_hoi.py --so-cau 6
    python3 tools/chay_cau_hoi.py --ma nhin-an-hit-sac
    python3 tools/chay_cau_hoi.py --ho-so tools/profiles/tien_me_cau_hoi.json

PHÉP ĐO KHỞI ĐỘNG LẠNH — không cần ai đưa bài mồi:

Mỗi câu hỏi chạy HAI truy vấn, và giá trị nằm ở chỗ SO chúng với nhau:

  MỞ ĐẦU  rộng, nhắm vào tổng quan hệ thống và hướng dẫn thực hành.
          Nó tìm ra AI ĐÃ TỔNG KẾT ngành này.
  CHÍNH   hẹp hơn, có thêm mệnh đề đối chiếu, là kho sẽ đem đi sàng.

Rồi hỏi: những bài tổng quan mà truy vấn MỞ ĐẦU tìm được có nằm trong kho
CHÍNH không? Bài tổng quan hệ thống về đúng chủ đề mà kho chính bỏ sót là một
LỖ HỔNG ĐỘ NHẠY ĐO ĐƯỢC — phát hiện với 0 phút của chuyên gia.

VÌ SAO PHÉP NÀY HỢP LỆ dù cả hai truy vấn đều từ một kho: chúng KHÁC NHAU ở
mệnh đề đối chiếu. Nếu thêm mệnh đề đối chiếu làm rụng các bài tổng quan về
đúng chủ đề, thì mệnh đề đó quá chặt — và đó là một kết luận về TRUY VẤN, rút
ra mà không cần biết trước bài nào 'phải có'.

GIỚI HẠN, nói thẳng: đây là phép đo yếu hơn bài mồi do chuyên gia nêu. Nó
không phát hiện được điểm mù CHUNG của cả hai truy vấn. Nó bắt được truy vấn
chính quá chặt; nó KHÔNG chứng minh được truy vấn mở đầu đã đủ rộng.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.dat_cau_hoi import DOI_CHIEU_BAT_BUOC, DangCauHoi, KhungTuyenChon
from tools.sources.europepmc import EuropePMCFetcher

HO_SO_MAC_DINH = ROOT / "tools/profiles/tien_me_cau_hoi.json"


def khung_tu_cau(c: dict) -> KhungTuyenChon:
    return KhungTuyenChon(
        diem_quyet_dinh=c["ma"], dang=DangCauHoi(c["dang"]),
        pham_vi=c["pham_vi"], mat_khao_sat=c["mat_khao_sat"],
        doi_chieu=c.get("doi_chieu") or [], ket_cuc=c["ket_cuc"],
    )


class KetQuaCau:
    """Kết quả chạy một câu hỏi. Giữ cả con số lẫn lý do để in ra được."""

    def __init__(self, ma: str, dang: str):
        self.ma = ma
        self.dang = dang
        self.so_tong_quan = 0
        self.kho_bao_co = 0
        self.da_tai = 0
        self.tong_quan_lot_kho = 0
        self.loi: str | None = None
        self.bac: dict[int | None, int] = {}
        self.co_hieu_luc = True           # phép so mở-đầu-vs-chính có nói lên gì không
        self.thieu: dict[str, tuple[int, int]] = {}   # mệnh đề -> (tìm được, lọt kho)

    @property
    def do_phu_tong_quan(self) -> float:
        """Tỷ lệ bài tổng quan mà kho chính giữ được. Đây là con số cốt lõi."""
        return self.tong_quan_lot_kho / self.so_tong_quan if self.so_tong_quan else 0.0

    @property
    def dat(self) -> bool:
        # Chưa tìm được bài tổng quan nào thì KHÔNG kết luận là đạt — không có
        # gì để đo thì im lặng, chứ không phải là qua.
        # Phép so vô hiệu thì KHÔNG được báo đạt: báo '✓' cho một phép đo không
        # thể thất bại đúng là cột 'Verified' tự khai.
        return (self.loi is None and self.co_hieu_luc
                and self.so_tong_quan > 0 and self.do_phu_tong_quan >= 0.8)


def chay_mot_cau(
    f, c: dict, tran: int = 20000, tran_mo_dau: int = 300,
) -> tuple[KetQuaCau, list]:
    """Chạy một câu hỏi: gặt tổng quan trước, quét kho chính sau, rồi đối chiếu.

    LUÔN trả về cặp (kết quả, bản ghi) — kể cả khi lỗi, lúc đó danh sách rỗng.
    Kiểu trả về thay đổi theo nhánh thành công/thất bại là cách nơi gọi lặng lẽ
    xử sai một trong hai nhánh.
    """
    kq = KetQuaCau(c["ma"], c["dang"])
    k = khung_tu_cau(c)
    kq.co_hieu_luc = k.phep_do_chong_lan_co_hieu_luc()
    try:
        tq, kq.so_tong_quan = f.quet_toan_bo(k.truy_van_mo_dau(), tran=tran_mo_dau)
        docs, kq.kho_bao_co = f.quet_toan_bo(k.thanh_truy_van(), tran=tran)
        # Phép đo THAY THẾ khi phép so trên vô hiệu: bỏ hẳn từng mệnh đề để biết
        # mệnh đề đó đang cắt mất bao nhiêu bài tổng quan.
        trong = {d.source_id for d in docs}
        for ten in ("pham_vi", "mat_khao_sat"):
            ds, tong = f.quet_toan_bo(k.truy_van_thieu(ten), tran=tran_mo_dau)
            kq.thieu[ten] = (tong, sum(1 for d in ds if d.source_id in trong))
    except Exception as exc:  # noqa: BLE001
        kq.loi = f"{type(exc).__name__}: {str(exc).splitlines()[0][:90]}"
        return kq, []

    kq.da_tai = len(docs)
    trong_kho = {d.source_id for d in docs}
    kq.tong_quan_lot_kho = sum(1 for d in tq if d.source_id in trong_kho)
    for d in docs:
        kq.bac[d.evidence_level] = kq.bac.get(d.evidence_level, 0) + 1
    return kq, docs


def _muc(t: str) -> None:
    print(f"\n{'─' * 70}\n{t}\n{'─' * 70}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chạy nhiều câu hỏi nghiên cứu")
    ap.add_argument("--ho-so", type=Path, default=HO_SO_MAC_DINH)
    ap.add_argument("--uu-tien", type=int, default=1)
    ap.add_argument("--so-cau", type=int, default=3)
    ap.add_argument("--ma", default=None, help="chạy đúng một câu theo mã")
    ap.add_argument("--tran", type=int, default=20000)
    ap.add_argument("--thu-muc", type=Path, default=Path("kho"))
    a = ap.parse_args(argv)

    ds = json.loads(a.ho_so.read_text(encoding="utf-8"))["cau_hoi"]
    if a.ma:
        chon = [c for c in ds if c["ma"] == a.ma]
        if not chon:
            print(f"Không có câu hỏi mã {a.ma!r}. Có: {[c['ma'] for c in ds][:8]}")
            return 2
    else:
        chon = [c for c in ds if c["uu_tien"] == a.uu_tien][: a.so_cau]

    print("=" * 70)
    print(f"CHẠY {len(chon)} CÂU HỎI · {a.ho_so.name}")
    print("=" * 70)
    print(f"  Dạng có mặt: {sorted({c['dang'] for c in chon})}")
    print("  Nhiều dạng khác nhau là CHỦ Ý: nếu khung tuyển chọn âm thầm chỉ hợp")
    print("  với 'điều trị', các dạng kia sẽ lộ ra ngay ở đây.")

    f = EuropePMCFetcher()
    a.thu_muc.mkdir(parents=True, exist_ok=True)
    tat_ca: list[KetQuaCau] = []

    for c in chon:
        k = khung_tu_cau(c)
        _muc(f"{c['ma']} · {c['dang']} · ưu tiên {c['uu_tien']} · rủi ro {c['rui_ro']}")
        print(f"  {c['cau_hoi']}")
        print(f"  Đầu ra cần có: {c['dau_ra_can_co']}")
        print(f"  Đối chiếu bắt buộc: {DOI_CHIEU_BAT_BUOC[DangCauHoi(c['dang'])]}")
        if c.get("ghi_chu"):
            print(f"  ⚠ {c['ghi_chu']}")

        kq, docs = chay_mot_cau(f, c, tran=a.tran)
        tat_ca.append(kq)

        if kq.loi:
            print(f"\n  ✗ {kq.loi}")
            continue

        print(f"\n  Tổng quan/hướng dẫn gặt được : {kq.so_tong_quan:,}".replace(",", "."))
        print(f"  Kho chính báo có             : {kq.kho_bao_co:,}".replace(",", "."))
        print(f"  Đã tải về                    : {kq.da_tai:,}".replace(",", "."))
        print(f"  Tổng quan LỌT vào kho chính  : "
              f"{kq.tong_quan_lot_kho}/{kq.so_tong_quan} ({kq.do_phu_tong_quan:.0%})")

        if kq.so_tong_quan == 0:
            print("\n  ⚠ Không gặt được bài tổng quan nào — KHÔNG kết luận được gì.")
            print("    Hoặc truy vấn mở đầu quá hẹp, hoặc chủ đề thật sự chưa ai tổng kết.")
            print("    Hai khả năng này cần hai cách xử khác nhau, phải phân biệt trước.")
        elif not kq.co_hieu_luc:
            print("\n  ⊘ PHÉP SO NÀY VÔ HIỆU — không phải đạt, cũng không phải trượt.")
            print("    Truy vấn mở đầu nay chỉ là truy vấn chính cộng bộ lọc loại bài,")
            print("    tức tập con chặt, nên độ phủ luôn 100%. Báo '✓' ở đây là báo")
            print("    một thành tích không tồn tại. Xem phép đo thay thế bên dưới.")
        elif not kq.dat:
            print("\n  ✗ LỖ HỔNG ĐỘ NHẠY: kho chính bỏ sót bài tổng quan về đúng chủ đề.")
        else:
            print("\n  ✓ Kho chính giữ được phần lớn bài tổng quan đã gặt.")

        if kq.thieu:
            print("\n  MỨC THU HẸP CỦA TỪNG MỆNH ĐỀ (mô tả, KHÔNG phải đạt/trượt):")
            for ten, (tong, lot) in kq.thieu.items():
                ty = lot / tong if tong else 0.0
                print(f"    bỏ {ten:<14} {tong:>7,} bài tổng quan, {lot} nằm trong kho ({ty:.0%})".replace(",", "."))
            print("    Bỏ một mệnh đề làm ĐỔI LUÔN CHỦ ĐỀ, nên bài tìm được không còn")
            print("    bảo đảm liên quan. Con số này CHỈ nói mệnh đề thu hẹp mạnh cỡ nào,")
            print("    KHÔNG nói nó loại nhầm hay không. Đo độ nhạy thật cần danh mục")
            print("    tham khảo của chính các bài tổng quan — chưa dựng.")

        if kq.bac:
            print("\n  Bậc chứng cứ:", "  ".join(
                f"{'?' if b is None else b}={n}"
                for b, n in sorted(kq.bac.items(), key=lambda x: (x[0] is None, x[0]))))

        tep = a.thu_muc / f"{c['ma']}.json"
        tep.write_text(json.dumps({
            "cau_hoi": c["ma"], "dang": c["dang"],
            "truy_van": k.thanh_truy_van(), "truy_van_mo_dau": k.truy_van_mo_dau(),
            "ket_cuc_quan_tam": c["ket_cuc"],
            "kho_bao_co": kq.kho_bao_co, "da_tai_ve": kq.da_tai,
            "ban_ghi": [d.model_dump(mode="json") | {"loai_bai_goc": f.loai_bai.get(d.uid, [])}
                        for d in docs],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  → ghi {kq.da_tai} bản ghi vào {tep}")

    _muc("TỔNG KẾT")
    print(f"  {'CÂU HỎI':<28}{'DẠNG':<12}{'KHO':>9}{'TỔNG QUAN LỌT':>16}")
    print("  " + "─" * 65)
    for kq in tat_ca:
        if kq.loi:
            print(f"  {kq.ma:<28}{kq.dang:<12}{'—':>9}{'lỗi':>16}")
            continue
        print(f"  {kq.ma:<28}{kq.dang:<12}{kq.da_tai:>9,}".replace(",", ".")
              + f"{kq.tong_quan_lot_kho:>7}/{kq.so_tong_quan:<3} "
                f"{'✓' if kq.dat else '✗'}")

    hong = [k for k in tat_ca if not k.dat and not k.loi]
    print()
    if any(k.loi for k in tat_ca):
        print("  Có câu chạy lỗi — xem chi tiết phía trên.")
    if hong:
        print(f"  {len(hong)} câu có lỗ hổng độ nhạy. SỬA TRUY VẤN TRƯỚC KHI SÀNG.")
        print("  Sàng trên kho thủng chỉ tạo ra một danh sách trông đầy đủ mà")
        print("  thiếu đúng những bài quan trọng — và không có gì báo.")
    elif not any(k.loi for k in tat_ca):
        print("  ✓ Cả ba dạng câu hỏi đều chạy được, không câu nào thủng.")
        print("    Khung tuyển chọn xử được nhiều dạng, không chỉ 'điều trị'.")
    print("\n  Đây vẫn là bước TẢI VỀ. Chưa bài nào được đọc và ra quyết định.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

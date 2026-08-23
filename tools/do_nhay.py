"""Đo ĐỘ NHẠY của truy vấn bằng bài mồi — biến "truy vấn tốt không" thành số.

VẤN ĐỀ NÀY GIẢI CÁI GÌ:

Siết truy vấn cho gọn có một rủi ro ngược mà không ai thấy được: mất bài đúng.
Kết quả từ 1.767 xuống 300 trông như tiến bộ, nhưng nếu trong 1.467 bài bị cắt
có bài quan trọng thì đó là thụt lùi — và KHÔNG CÓ TÍN HIỆU NÀO báo. Đây đúng
kiểu hỏng im lặng mà cả dự án này được dựng lên để chống.

CÁCH GIẢI, theo đúng lối đã dùng cho so_khop_ban_chinh_thong(): đừng tranh luận,
hãy đo. Chọn trước một nhúm bài mà BẤT KỲ bài tổng quan tử tế nào về chủ đề này
cũng bắt buộc phải có (bài mồi / seed). Chạy truy vấn. Truy vấn nào không lôi
được bài mồi về là truy vấn thủng — bất kể nó trả về bao nhiêu kết quả.

Đây là kỹ thuật chuẩn trong phương pháp luận tổng quan hệ thống, thường gọi là
'known-item testing'. Nó rẻ, chạy được ngoại tuyến, và cho một con số so sánh
được giữa các phiên bản truy vấn.

GIỚI HẠN PHẢI NÓI RÕ: bài mồi do người chọn, nên phép đo này chỉ nghiêm ngặt
bằng đúng danh sách mồi. Nó bắt được truy vấn thủng; nó KHÔNG chứng minh được
truy vấn đầy đủ. Không có phép đo nào chứng minh được điều đó.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.sources.pubmed import normalize_pubmed_id

# Bài mồi cho chủ đề chống đông chu phẫu. Cả bốn đã được xác minh độc lập:
# mã ↔ tiêu đề khớp với nguồn ngoài PubMed.
MOI_CHONG_DONG: dict[str, str] = {
    "pubmed:26095867": "BRIDGE — RCT nền tảng, bắc cầu chống đông ở rung nhĩ (NEJM 2015)",
    "pubmed:34108229": "PERIOP2 — RCT bắc cầu LMWH sau mổ (BMJ 2021)",
    "pubmed:36462533": "Tổng quan hệ thống + phân tích gộp VKA/DOAC chu phẫu (CHEST 2023)",
    "pubmed:40448969": "Hướng dẫn DOAC 2025, có phần chu phẫu (Intern Med J 2025)",
}


@dataclass
class KetQuaNhay:
    """Kết quả một lần đo độ nhạy."""

    tim_thay: list[str] = field(default_factory=list)
    bo_sot: list[str] = field(default_factory=list)
    mo_ta: dict[str, str] = field(default_factory=dict)

    @property
    def tong_moi(self) -> int:
        return len(self.tim_thay) + len(self.bo_sot)

    @property
    def do_nhay(self) -> float:
        """Tỷ lệ bài mồi lôi về được. 1.0 là điều kiện CẦN, không phải điều kiện ĐỦ."""
        return len(self.tim_thay) / self.tong_moi if self.tong_moi else 0.0

    @property
    def dat(self) -> bool:
        """Sót dù chỉ MỘT bài mồi cũng là trượt.

        Không đặt ngưỡng mềm ở đây có chủ ý: bài mồi là bài đã biết chắc phải có.
        Chấp nhận 'sót 1 trong 4' nghĩa là chấp nhận truy vấn bỏ lọt bài nền tảng
        — và ta sẽ không bao giờ biết nó còn bỏ lọt gì trong phần chưa biết.
        """
        return not self.bo_sot


def kiem_bai_moi(
    ids_truy_van_tra_ve: list[str],
    moi: dict[str, str] | None = None,
) -> KetQuaNhay:
    """So kết quả truy vấn với danh sách bài mồi.

    `ids_truy_van_tra_ve` nhận mọi biến thể mã ('PMID: 123', URL, số trần) —
    chuẩn hoá bằng đúng hàm mà phần còn lại của hệ thống dùng, để phép đo không
    bao giờ báo 'sót' chỉ vì hai bên viết mã khác kiểu.
    """
    moi = MOI_CHONG_DONG if moi is None else moi
    thu_duoc = {
        chuan for chuan in (normalize_pubmed_id(i) for i in ids_truy_van_tra_ve)
        if chuan
    }
    kq = KetQuaNhay(mo_ta=dict(moi))
    for ma in moi:
        (kq.tim_thay if ma in thu_duoc else kq.bo_sot).append(ma)
    return kq


def bao_cao(kq: KetQuaNhay, ten_truy_van: str = "truy vấn") -> str:
    """Dựng báo cáo đọc được cho người."""
    dong = [
        f"ĐỘ NHẠY · {ten_truy_van}",
        f"  Bài mồi lôi về được : {len(kq.tim_thay)}/{kq.tong_moi} ({kq.do_nhay:.0%})",
    ]
    for ma in kq.bo_sot:
        dong.append(f"  ✗ SÓT {ma} — {kq.mo_ta.get(ma, '')}")
    for ma in kq.tim_thay:
        dong.append(f"  ✓ {ma}")
    dong.append("")
    if kq.dat:
        dong += [
            "  ✓ Không sót bài mồi nào.",
            "    Đây là điều kiện CẦN, không phải ĐỦ — truy vấn vẫn có thể bỏ lọt",
            "    những bài ta chưa biết để đưa vào danh sách mồi.",
        ]
    else:
        dong += [
            "  ✗ TRUY VẤN THỦNG — đã sót bài nền tảng đã biết trước.",
            "    Không siết truy vấn thêm nữa cho tới khi vá xong lỗ này.",
            "    Sót bài đã biết nghĩa là gần như chắc chắn còn sót bài chưa biết.",
        ]
    return "\n".join(dong)


def so_sanh_hai_truy_van(
    truoc: KetQuaNhay, sau: KetQuaNhay, so_kq_truoc: int, so_kq_sau: int
) -> str:
    """Chấm một lần siết truy vấn: giảm được bao nhiêu khối lượng, trả giá gì.

    Đây là bảng cân đối mà mọi lần chỉnh truy vấn đều phải trình ra. Giảm khối
    lượng mà tụt độ nhạy KHÔNG phải tối ưu hoá — đó là đánh đổi tính đầy đủ lấy
    sự tiện lợi, và phải gọi đúng tên như vậy.
    """
    giam = (1 - so_kq_sau / so_kq_truoc) if so_kq_truoc else 0.0
    dong = [
        "SO SÁNH HAI PHIÊN BẢN TRUY VẤN",
        f"  Khối lượng : {so_kq_truoc:,} -> {so_kq_sau:,}  (giảm {giam:.0%})".replace(",", "."),
        f"  Độ nhạy    : {truoc.do_nhay:.0%} -> {sau.do_nhay:.0%}",
    ]
    moi_sot = set(sau.bo_sot) - set(truoc.bo_sot)
    if moi_sot:
        dong.append("")
        dong.append("  ✗ TỪ CHỐI: lần siết này làm SÓT THÊM bài mồi:")
        for ma in sorted(moi_sot):
            dong.append(f"      {ma} — {sau.mo_ta.get(ma, '')}")
        dong.append("    Khối lượng giảm được không bù nổi cho bài nền tảng bị mất.")
    elif sau.dat:
        dong.append("")
        dong.append("  ✓ NHẬN: khối lượng giảm mà không mất bài mồi nào.")
    return "\n".join(dong)

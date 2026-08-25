"""NGUỒN TỔNG HỢP NGOÀI — chuẩn vàng do chuyên gia ngoài biên tập.

VÌ SAO CÓ TỆP NÀY — nó vá đúng lỗ hổng lớn nhất còn lại của hệ:

Kế hoạch T1 định đo độ nhạy bằng danh mục tham khảo của tổng quan hệ thống TRONG
KHO. Nhưng tổng quan đó được tìm ra BẰNG CHÍNH TRUY VẤN ĐANG BỊ KIỂM. Nên nếu
truy vấn có điểm mù, ta không bao giờ gặp bài tổng quan sẽ phơi bày điểm mù đó.

  Chuẩn vàng nằm Ở HẠ NGUỒN của thứ nó đang kiểm -> vòng lặp khép kín một phần.

UpToDate phá được vòng đó: bài được tìm theo TÊN CHỦ ĐỀ, không qua truy vấn nào
của ta. Danh mục tham khảo do biên tập viên dựng, họ chưa từng thấy truy vấn của
ta. Chuẩn vàng nằm HOÀN TOÀN Ở THƯỢNG NGUỒN.

Đó là toàn bộ lý do tệp này đáng tồn tại.

────────────────────────────────────────────────────────────────────────
PHÉP ĐO NÀY CHỈ CHẠY MỘT CHIỀU — đọc kỹ trước khi báo cáo bất cứ số nào
────────────────────────────────────────────────────────────────────────

UpToDate là nguồn TAM CẤP: biên tập viên CHỌN bài để trích, không trích hết. Nên:

  kho SÓT một bài UpToDate trích  ->  LỖ HỔNG ĐÃ ĐƯỢC XÁC NHẬN     (kết luận được)
  kho CHỨA ĐỦ bài UpToDate trích  ->  KHÔNG chứng minh kho đã đủ    (KHÔNG kết luận được)

Phép đo chứng minh được THẤT BẠI, không chứng minh được THÀNH CÔNG. Vì vậy
trạng thái tốt nhất nó trả về là `KHONG_PHAT_HIEN_LO_HONG`, không phải "đạt".

Gọi nó là "đạt" chính là cột 'Verified' tự khai của Spark mọc lại lần nữa: một
trường không thể thất bại thì mặc định đẹp.

────────────────────────────────────────────────────────────────────────
RANH GIỚI BẮT BUỘC: UpToDate LÀM ĐỀ THI CHO BỘ SÀNG, KHÔNG LÀM BỘ SÀNG
────────────────────────────────────────────────────────────────────────

Cám dỗ rất lớn và rất sai: "giữ bài UpToDate có trích, loại bài nó không trích".

Làm vậy là hỏng ba tầng cùng lúc:
  1. Đó là sàng theo KẾT LUẬN của người khác — vi phạm nguyên tắc mù kết cục đã
     được cài vào cấu trúc `KhungTuyenChon.thanh_truy_van()`.
  2. Nó nhập luôn thiên lệch của UpToDate (thiên lệch công bố, thiên lệch chọn bài).
  3. Nếu đầu ra của SR-Agent = trích dẫn của UpToDate thì SR-Agent KHÔNG THÊM GÌ.
     Cả hệ này dựng lên để tìm thứ một bản tổng hợp thủ công có thể đã bỏ sót.

Dùng đúng: chạy bộ sàng của ta LÊN các bài UpToDate trích. Bộ sàng loại nhầm một
bài trong đó -> cờ đỏ cho BỘ SÀNG, không phải cờ đỏ cho bài.

────────────────────────────────────────────────────────────────────────
BẢN QUYỀN
────────────────────────────────────────────────────────────────────────

Chỉ lưu MÃ BÀI (PMID/DOI) vào kho mã nguồn. Không đưa văn bản, khuyến cáo, hay
bản PDF của UpToDate vào repo. Danh mục trích dẫn là dữ kiện thư mục và dùng để
truy về bài gốc — đó là thao tác học thuật thông thường; nội dung biên tập thì
không.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

# Số mục tra được TỐI THIỂU để phép đo có khả năng phát hiện ra thứ gì đó.
#
# Đây là NGƯỠNG TỰ KHAI, không phải hằng số tìm ra được. Lý do phải có nó: tra
# được 2/150 trích dẫn rồi báo "không phát hiện lỗ hổng" là báo về độ mù của
# phép đo chứ không phải về chất lượng của kho. Dưới ngưỡng này -> VÔ HIỆU.
TOI_THIEU_DE_KET_LUAN = 5

_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
_PMID_CO_NHAN = re.compile(r"\bPMID:?\s*(\d{4,8})\b", re.IGNORECASE)
_NAM = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
_DAU_MUC = re.compile(r"^\s*(\d{1,3})[.)]\s+(.*)$")


class KetLuan(str, Enum):
    """Ba trạng thái. Không có trạng thái 'đạt' — xem phần đầu tệp."""

    CO_LO_HONG = "CÓ LỖ HỔNG"
    KHONG_PHAT_HIEN_LO_HONG = "không phát hiện lỗ hổng"
    VO_HIEU = "VÔ HIỆU"


def ma_tran(ma: str) -> str:
    """Rút phần định danh trần để so khớp giữa các hệ đánh mã khác nhau.

    Cùng một bài mang ba tên tuỳ nơi: `pubmed:26095867` ·
    `europepmc:MED:26095867` · `26095867`. So chuỗi thẳng sẽ báo SÓT một bài
    đang nằm sẵn trong kho — lỗi này đã suýt khiến tôi kết tội Spark bịa mã.
    """
    return ma.rsplit(":", 1)[-1].strip().lower()


@dataclass
class MucThamKhao:
    """Một mục trong danh mục tham khảo. CHƯA phải chuẩn vàng cho tới khi tra được."""

    nguyen_van: str
    so: int | None = None
    pmid: str | None = None
    doi: str | None = None
    nam: int | None = None

    @property
    def ma(self) -> str | None:
        return f"pubmed:{self.pmid}" if self.pmid else None

    @property
    def tra_duoc_ngay(self) -> bool:
        """Tra được NGAY = có PMID hoặc DOI in thẳng trong trích dẫn.

        Mục chỉ có tên tác giả + tạp chí + năm thì phải tra qua mạng, và việc
        tra đó BẮT BUỘC phải khắt khe: một mục khớp NHẦM còn tệ hơn một mục
        không tra được. Không tra được thì lộ ra ở mẫu số; khớp nhầm thì âm
        thầm dịch cả tử số lẫn mẫu số mà không ai thấy.
        """
        return bool(self.pmid or self.doi)


def tach_danh_muc(van_ban: str) -> list[MucThamKhao]:
    """Bóc danh mục tham khảo đánh số thành từng mục.

    Mục bị ngắt dòng giữa chừng phải được nối lại: bản in PDF xuống dòng theo
    bề rộng trang, nên một trích dẫn thường nằm trên 2-3 dòng. Cắt theo dòng sẽ
    biến một trích dẫn thành ba mảnh vụn không tra được mảnh nào.
    """
    muc: list[MucThamKhao] = []
    dang_gom: list[str] = []
    so_hien: int | None = None

    def chot() -> None:
        if not dang_gom:
            return
        raw = " ".join(x.strip() for x in dang_gom).strip()
        if len(raw) >= 12:
            muc.append(_dung_muc(raw, so_hien))

    for dong in van_ban.splitlines():
        m = _DAU_MUC.match(dong)
        if m:
            chot()
            so_hien = int(m.group(1))
            dang_gom = [m.group(2)]
        elif dong.strip():
            dang_gom.append(dong)
        else:
            chot()
            dang_gom, so_hien = [], None
    chot()
    return muc


def _dung_muc(raw: str, so: int | None) -> MucThamKhao:
    pm = _PMID_CO_NHAN.search(raw)
    doi = _DOI.search(raw)
    nam = _NAM.findall(raw)
    return MucThamKhao(
        nguyen_van=raw,
        so=so,
        pmid=pm.group(1) if pm else None,
        doi=doi.group(0).rstrip(".;,") if doi else None,
        # Trích dẫn có thể chứa nhiều số 4 chữ số (số trang, số tập). Năm xuất
        # bản theo quy ước trích dẫn là số hợp lệ CUỐI cùng.
        nam=int(nam[-1]) if nam else None,
    )


@dataclass
class KetQuaDoiChieu:
    """Đối chiếu tập chuẩn vàng với kho. Xem phần 'một chiều' ở đầu tệp."""

    co_trong_kho: list[str] = field(default_factory=list)
    sot: list[str] = field(default_factory=list)
    khong_tra_duoc: list[MucThamKhao] = field(default_factory=list)
    ten_chu_de: str = ""

    @property
    def so_tra_duoc(self) -> int:
        return len(self.co_trong_kho) + len(self.sot)

    @property
    def tong_muc(self) -> int:
        return self.so_tra_duoc + len(self.khong_tra_duoc)

    @property
    def ty_le_tra_duoc(self) -> float:
        return self.so_tra_duoc / self.tong_muc if self.tong_muc else 0.0

    @property
    def ket_luan(self) -> KetLuan:
        if self.so_tra_duoc < TOI_THIEU_DE_KET_LUAN:
            return KetLuan.VO_HIEU
        return KetLuan.CO_LO_HONG if self.sot else KetLuan.KHONG_PHAT_HIEN_LO_HONG

    @property
    def do_phu(self) -> float | None:
        """None khi vô hiệu — CỐ Ý, không phải thiếu sót.

        Trả 0.0 hay 1.0 cho một phép đo vô hiệu là cách con số vô nghĩa lọt vào
        bảng báo cáo rồi được đọc như con số thật. Đã mất một lần vì chuyện này
        ở phép so chồng lấn.
        """
        if self.ket_luan is KetLuan.VO_HIEU:
            return None
        return len(self.co_trong_kho) / self.so_tra_duoc


def doi_chieu_voi_kho(
    muc: list[MucThamKhao],
    kho_ids: list[str],
    ten_chu_de: str = "",
) -> KetQuaDoiChieu:
    """Bài nào chuyên gia ngoài trích mà kho ta KHÔNG có?

    Chỉ đối chiếu mục tra được ngay. Mục chưa tra được không tính là sót — nó
    chưa được chứng minh là tồn tại, và tính nó là sót sẽ đổ lỗi cho truy vấn
    về một bài có thể không có thật.
    """
    trong_kho = {ma_tran(x) for x in kho_ids}
    kq = KetQuaDoiChieu(ten_chu_de=ten_chu_de)
    for m in muc:
        if not m.tra_duoc_ngay:
            kq.khong_tra_duoc.append(m)
            continue
        khoa = ma_tran(m.ma) if m.ma else (m.doi or "").lower()
        (kq.co_trong_kho if khoa in trong_kho else kq.sot).append(m.ma or m.doi or m.nguyen_van)
    return kq


def bao_cao(kq: KetQuaDoiChieu) -> str:
    dong = [
        f"ĐỐI CHIẾU VỚI NGUỒN TỔNG HỢP NGOÀI — {kq.ten_chu_de or '(chưa đặt tên)'}",
        f"  Mục trong danh mục   : {kq.tong_muc}",
        f"  Tra được ngay        : {kq.so_tra_duoc} ({kq.ty_le_tra_duoc:.0%})",
        f"  KẾT LUẬN             : {kq.ket_luan.value}",
    ]
    if kq.ket_luan is KetLuan.VO_HIEU:
        dong += [
            "",
            f"  ⊘ Dưới {TOI_THIEU_DE_KET_LUAN} mục tra được thì phép đo không phát hiện",
            "    được gì. Con số độ phủ CỐ Ý bỏ trống — đây là độ mù của phép đo,",
            "    không phải nhận xét về kho.",
        ]
        return "\n".join(dong)

    dong.append(f"  Kho chứa             : {len(kq.co_trong_kho)}/{kq.so_tra_duoc} ({kq.do_phu:.0%})")
    if kq.sot:
        dong += ["", f"  ✗ SÓT {len(kq.sot)} bài chuyên gia ngoài có trích:"]
        dong += [f"      {m}" for m in kq.sot[:20]]
        if len(kq.sot) > 20:
            dong.append(f"      ... còn {len(kq.sot) - 20} bài")
        dong += ["", "    Đây là lỗ hổng ĐÃ XÁC NHẬN của truy vấn. Không tự sửa truy vấn"]
        dong.append("    cho đến khi xem xong danh sách trên — sửa để phép đo xanh là")
        dong.append("    cách làm hỏng phép đo.")
    else:
        dong += [
            "",
            "  ✓ Không phát hiện lỗ hổng — LƯU Ý: đây KHÔNG phải 'kho đã đủ'.",
            "    Nguồn tam cấp chỉ trích bài biên tập viên chọn, nên phép đo này",
            "    chứng minh được thất bại chứ không chứng minh được thành công.",
        ]
    return "\n".join(dong)

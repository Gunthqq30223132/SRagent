"""Hàng đợi bàn giao Spark → SR-Agent, dưới dạng THƯ MỤC FILE, không phải API.

VÌ SAO LÀ THƯ MỤC:
SR-Agent chạy trên máy Mac và KHÔNG có khoá API Google. Dựng OAuth/service
account chỉ để đọc vài phiếu JSON là chi phí lớn cho một việc nhỏ. Google Drive
for Desktop đã đồng bộ thư mục Drive thành thư mục cục bộ — nên hàng đợi chỉ
cần là một thư mục, và cả hai phía đọc/ghi bằng thao tác file thường.
Không khoá, không OAuth, không mã mạng, và đồng bộ hai chiều miễn phí.

VÌ SAO MỖI LẦN QUÉT LÀ MỘT FILE MỚI:
Ghi thêm vào một file chung đòi đọc-sửa-ghi, mà Spark thì không có khoá đồng bộ
— hai lần chạy chồng nhau sẽ đè mất dữ liệu của nhau. Tạo file mới là thao tác
Spark đã chứng minh làm tốt 21/21 ngày, và nó **chỉ-thêm theo cấu tạo**: không
có đường nào để sửa hỏng phiếu cũ.

VÌ SAO ĐƠN VỊ LÀ "LẦN QUÉT" CHỨ KHÔNG PHẢI "BÀI BÁO":
PRISMA cần số liệu ở mức lần quét — chuỗi truy vấn, tổng số trúng, số loại trừ
và lý do. Mỗi bài một file sẽ làm mất đúng những con số đó.

NGUYÊN TẮC TRUNG TÂM: Spark là TRINH SÁT, không phải NGUỒN.
Phiếu chỉ mang MÃ BÀI. Nội dung do SR-Agent tự tải lại từ nguồn gốc.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

MA_PHIEU_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_[a-z0-9\-]+_[a-z0-9\-]+$")


class BanLoaiTru(BaseModel):
    """Một bài bị Spark loại, kèm lý do. Đầu vào bắt buộc của sơ đồ PRISMA."""

    id: str
    ly_do: str

    @field_validator("ly_do")
    @classmethod
    def _ly_do_phai_co_noi_dung(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5:
            raise ValueError(
                "Lý do loại trừ quá ngắn — PRISMA đòi lý do đọc được, "
                "không phải một chữ hay dấu gạch"
            )
        return v


class PhieuQuet(BaseModel):
    """Kết quả MỘT lần quét của Spark. Bất biến sau khi ghi."""

    ma_phieu: str
    ngay_quet: date
    nguon: str
    cau_hoi: str
    chuoi_truy_van: str
    so_ket_qua_tho: int = Field(ge=0)
    so_da_sang: int = Field(ge=0)
    ids: list[str] = []
    loai_tru: list[BanLoaiTru] = []
    ghi_chu: str = ""

    @field_validator("ma_phieu")
    @classmethod
    def _dinh_dang_ma_phieu(cls, v: str) -> str:
        if not MA_PHIEU_RE.match(v):
            raise ValueError(
                f"ma_phieu {v!r} sai định dạng. Cần: <ngày>_<chủ-đề>_<nguồn>, "
                f"ví dụ '2026-08-24_chong-dong_pubmed'"
            )
        return v

    @field_validator("chuoi_truy_van")
    @classmethod
    def _truy_van_phai_nguyen_van(cls, v: str) -> str:
        """Đòi DẤU HIỆU CẤU TRÚC, không chỉ đòi độ dài.

        Kiểm độ dài không phân biệt được truy vấn thật với mô tả bằng lời —
        "tìm về chống đông" dài 18 ký tự vẫn lọt. Một chuỗi tìm thật luôn mang
        ít nhất một dấu hiệu máy đọc được: toán tử Boolean, thẻ trường, ngoặc,
        hoặc dấu nháy cụm. Thiếu tất cả thì đó là lời kể, và lời kể thì không
        chạy lại được — mà chạy lại được chính là điều kiện của PRISMA.
        """
        v = v.strip()
        if len(v) < 10:
            raise ValueError("chuoi_truy_van quá ngắn để là một truy vấn thật")
        dau_hieu = (
            re.search(r"\b(AND|OR|NOT)\b", v)          # toán tử Boolean
            or re.search(r"\[[A-Za-z/ ]+\]", v)        # thẻ trường: [Mesh], [tiab]
            or ("(" in v and ")" in v)                 # nhóm ngoặc
            or re.search(r'"[^"]{3,}"', v)             # cụm trong nháy
        )
        if not dau_hieu:
            raise ValueError(
                f"chuoi_truy_van {v!r} không mang dấu hiệu của một truy vấn thật "
                "(thiếu cả AND/OR/NOT, thẻ trường [Mesh], ngoặc, lẫn cụm trong "
                'nháy). Phải là chuỗi NGUYÊN VĂN đã gửi cho nguồn, không phải '
                "mô tả bằng lời — lời kể thì không chạy lại được."
            )
        return v

    @field_validator("ids")
    @classmethod
    def _khong_trung_trong_cung_phieu(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            trung = sorted({x for x in v if v.count(x) > 1})
            raise ValueError(f"ID lặp trong cùng một phiếu: {trung}")
        return v

    @model_validator(mode="after")
    def _so_hoc_phai_nhat_quan(self) -> "PhieuQuet":
        """Kiểm SỐ HỌC trên chính con số Spark tự khai.

        Đây là chốt chặn rẻ nhất mà hiệu quả nhất: không cần biết Spark có trung
        thực không, chỉ cần biết các con số nó khai có cộng lại được không.
        Bộ dữ liệu cũ có cột 'Trạng Thái Kiểm Định' ghi 'Verified' ở 22/22 dòng
        mà không ai kiểm gì — một trường tự khai không có ràng buộc thì vô giá trị.
        Ràng buộc số học biến lời khai thành thứ kiểm được.
        """
        if self.so_da_sang > self.so_ket_qua_tho:
            raise ValueError(
                f"so_da_sang ({self.so_da_sang}) > so_ket_qua_tho "
                f"({self.so_ket_qua_tho}) — không thể sàng nhiều hơn số tìm được"
            )
        giu_lai = len(self.ids)
        if giu_lai + len(self.loai_tru) > self.so_da_sang:
            raise ValueError(
                f"giữ lại ({giu_lai}) + loại trừ ({len(self.loai_tru)}) = "
                f"{giu_lai + len(self.loai_tru)} > đã sàng ({self.so_da_sang})"
            )
        chong = set(self.ids) & {b.id for b in self.loai_tru}
        if chong:
            raise ValueError(
                f"ID vừa được giữ vừa bị loại: {sorted(chong)} — mâu thuẫn nội tại"
            )
        if not self.ids and not self.ghi_chu.strip():
            raise ValueError(
                "Phiếu không có ID nào mà cũng không có ghi_chu giải thích. "
                "Quét ra 0 bài là một KẾT QUẢ, phải nói rõ vì sao, không được để trống"
            )
        return self


class KetQuaDoc(BaseModel):
    """Kết quả đọc cả thư mục hàng đợi — gồm cả phần hỏng, không giấu."""

    phieu_hop_le: list[PhieuQuet] = []
    phieu_hong: list[tuple[str, str]] = []   # (tên file, lý do)
    ngay_phieu_moi_nhat: date | None = None

    @property
    def tong_id(self) -> int:
        return sum(len(p.ids) for p in self.phieu_hop_le)


def doc_hang_doi(thu_muc: Path) -> KetQuaDoc:
    """Đọc mọi phiếu .json trong thư mục hàng đợi.

    Phiếu hỏng KHÔNG làm dừng cả mẻ — nhưng cũng KHÔNG bị nuốt im lặng: nó vào
    danh sách phieu_hong để tầng gọi báo cáo. Bỏ qua thầm lặng chính là lỗi đã
    làm mất bài 2606.01770 trong bộ dữ liệu cũ mà không ai biết.
    """
    ket_qua = KetQuaDoc()
    if not thu_muc.exists():
        ket_qua.phieu_hong.append(
            (str(thu_muc), "Thư mục hàng đợi không tồn tại — kiểm lại đường dẫn "
                           "Google Drive for Desktop đã đồng bộ chưa")
        )
        return ket_qua

    for duong_dan in sorted(thu_muc.glob("*.json")):
        try:
            du_lieu = json.loads(duong_dan.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            ket_qua.phieu_hong.append((duong_dan.name, f"JSON hỏng: {exc}"))
            continue
        try:
            ket_qua.phieu_hop_le.append(PhieuQuet.model_validate(du_lieu))
        except Exception as exc:  # pydantic ValidationError
            ket_qua.phieu_hong.append((duong_dan.name, str(exc).split("\n")[0]))

    if ket_qua.phieu_hop_le:
        ket_qua.ngay_phieu_moi_nhat = max(p.ngay_quet for p in ket_qua.phieu_hop_le)
    return ket_qua


def kiem_do_tuoi(ket_qua: KetQuaDoc, so_ngay_cho_phep: int = 3,
                 hom_nay: date | None = None) -> str | None:
    """Hàng đợi im lặng quá lâu -> cảnh báo. Trả None nếu bình thường.

    TẠI SAO CẦN: chế độ hỏng nguy hiểm nhất của Spark KHÔNG phải ghi sai, mà là
    KHÔNG GHI GÌ CẢ. Bộ dữ liệu cũ có một ngày trống mà nhật ký vẫn báo thành
    công. Tầng kiểm định phải phát hiện được sự VẮNG MẶT, không chỉ xử lý cái
    có mặt — vì không có dữ liệu thì không có gì để báo lỗi.
    """
    hom_nay = hom_nay or datetime.now(timezone.utc).date()
    if ket_qua.ngay_phieu_moi_nhat is None:
        return "Hàng đợi RỖNG — chưa có phiếu quét nào hợp lệ."
    tre = (hom_nay - ket_qua.ngay_phieu_moi_nhat).days
    if tre > so_ngay_cho_phep:
        return (f"Hàng đợi CŨ: phiếu mới nhất {ket_qua.ngay_phieu_moi_nhat} "
                f"({tre} ngày trước). Spark có thể đã ngừng chạy.")
    return None

"""Kho bất biến + sổ quyết định chỉ nối thêm.

BÓC THEO BẢN CHẤT — đây là HAI loại dữ liệu có vòng đời khác hẳn nhau:

  KHO BẢN GHI    ghi MỘT lần, không bao giờ đổi. Là ảnh chụp kho tại thời điểm T.
                 Nếu nó đổi thì PRISMA sai, vì đã là một kho khác.
  SỔ QUYẾT ĐỊNH  bồi đắp dần, có thể sửa, nhiều người/máy cùng ghi.

Trộn hai thứ vào một tệp buộc phải GHI ĐÈ dữ liệu bất biến mỗi lần ra một quyết
định. Đó là chỗ sinh ra mất việc giữa chừng và hỏng tệp.

VÂN TAY KHO — mối nối giữa hai thứ, và là phần đáng nghĩ nhất của tệp này:

'Bất biến' mà không kiểm được thì chỉ là lời hứa. Nên mỗi dòng quyết định mang
theo vân tay của kho mà nó được ra trên đó. Quét lại chủ đề, kho đổi (bài mới
xuất bản, truy vấn chỉnh), vân tay đổi -> mọi quyết định cũ lập tức bị đánh dấu
là thuộc kho khác, thay vì lặng lẽ trộn vào kho mới.

Vân tay băm DANH SÁCH MÃ ĐÃ SẮP XẾP, không băm byte thô của tệp. Có chủ ý:
định dạng lại JSON KHÔNG được làm mất công sàng lọc, nhưng thêm hay bớt một bản
ghi thì PHẢI làm mất — vì lúc đó tập bài cần sàng đã khác.

CHỈ NỐI THÊM, KHÔNG SỬA CHỖ CŨ:
  - Sập giữa chừng mất tối đa MỘT dòng, không mất cả sổ.
  - Đổi ý = nối thêm dòng mới cho cùng mã; dòng sau thắng. Lịch sử VẪN CÒN.
    Nên việc đổi quyết định là thứ NHÌN THẤY ĐƯỢC, không phải thứ lặng lẽ xảy ra.
  - Dòng hỏng thì BÁO ra, không lặng lẽ bỏ qua.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Iterator

from pydantic import BaseModel, Field, field_validator, model_validator


class Quyet(str, Enum):
    GIU = "giu"
    LOAI = "loai"
    NGHI_NGO = "nghi_ngo"


class QuyetDinh(BaseModel):
    """Một dòng trong sổ. Mỗi trường ở đây đều có lý do bắt buộc riêng."""

    ma: str
    quyet_dinh: Quyet
    ly_do: str = ""
    nguoi_sang: str          # 'gun' | 'may:<tên>@<phiên bản>' — cần để so người với máy
    phien_ban_tieu_chi: str  # tiêu chí đổi giữa chừng thì quyết định trước/sau KHÔNG so được
    van_tay_kho: str
    luc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("ma", "nguoi_sang", "phien_ban_tieu_chi", "van_tay_kho")
    @classmethod
    def _khong_rong(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("trường bắt buộc không được rỗng")
        return v.strip()

    @model_validator(mode="after")
    def _loai_phai_co_ly_do(self) -> "QuyetDinh":
        """Loại không lý do thì KHÔNG dựng được sơ đồ PRISMA.

        PRISMA đòi đếm được số bài bị loại THEO TỪNG LÝ DO. Một quyết định loại
        không lý do làm hỏng đúng con số đó, và không có cách nào khôi phục sau —
        người ra quyết định lúc ấy đã quên mất vì sao rồi.
        """
        if self.quyet_dinh is Quyet.LOAI and len(self.ly_do.strip()) < 5:
            raise ValueError(
                f"{self.ma}: loại bài phải kèm lý do đọc được (tối thiểu 5 ký tự). "
                f"Nhận được {self.ly_do!r}. Loại không lý do thì không dựng được PRISMA."
            )
        return self


def van_tay_kho(ma_ban_ghi: Iterable[str]) -> str:
    """Băm danh sách mã ĐÃ SẮP XẾP — định danh tập bài, không định danh byte tệp.

    Chọn như vậy để: định dạng lại JSON không làm mất công sàng lọc, nhưng thêm
    hoặc bớt một bản ghi thì làm mất — vì lúc đó tập bài cần sàng đã khác thật.
    """
    ds = sorted(set(ma_ban_ghi))
    h = hashlib.sha256("\n".join(ds).encode("utf-8")).hexdigest()
    return f"sha256:{h[:16]}:{len(ds)}"


def van_tay_tu_tep(duong_dan: Path) -> tuple[str, list[str]]:
    """Đọc tệp kho, trả về (vân tay, danh sách mã)."""
    data = json.loads(duong_dan.read_text(encoding="utf-8"))
    if "ban_ghi" not in data:
        raise ValueError(f"{duong_dan} không phải tệp kho (thiếu khoá 'ban_ghi').")
    ma = [r.get("source_id", "") for r in data["ban_ghi"]]
    thieu = sum(1 for m in ma if not m)
    if thieu:
        raise ValueError(
            f"{duong_dan}: {thieu} bản ghi không có source_id. Bản ghi không định "
            f"danh được thì không gắn quyết định vào đâu cả."
        )
    return van_tay_kho(ma), ma


class KetQuaDocSo(BaseModel):
    """Kết quả đọc sổ. Dòng hỏng được BÁO, không bị nuốt."""

    quyet_dinh: list[QuyetDinh] = []
    dong_hong: list[tuple[int, str]] = []
    van_tay_la: dict[str, int] = {}   # vân tay khác -> số dòng mang nó

    @property
    def theo_ma(self) -> dict[str, QuyetDinh]:
        """Quyết định mới nhất cho từng mã. Dòng sau thắng dòng trước."""
        ra: dict[str, QuyetDinh] = {}
        for qd in self.quyet_dinh:
            ra[qd.ma] = qd
        return ra

    @property
    def da_doi_y(self) -> dict[str, int]:
        """Mã nào bị ra quyết định nhiều hơn một lần, và bao nhiêu lần.

        Không phải lỗi — chỉ nối thêm nghĩa là đổi ý được. Nhưng nó phải HIỆN RA,
        vì một mã bị lật đi lật lại là dấu hiệu tiêu chí đang mơ hồ ở chỗ đó.
        """
        dem: dict[str, int] = {}
        for qd in self.quyet_dinh:
            dem[qd.ma] = dem.get(qd.ma, 0) + 1
        return {m: n for m, n in dem.items() if n > 1}


class SoQuyetDinh:
    """Sổ chỉ nối thêm, gắn với đúng MỘT kho qua vân tay."""

    def __init__(self, duong_dan: Path, van_tay: str):
        self.duong_dan = Path(duong_dan)
        self.van_tay = van_tay

    def ghi(self, qd: QuyetDinh) -> None:
        self.ghi_nhieu([qd])

    def ghi_nhieu(self, ds: Iterable[QuyetDinh]) -> int:
        """Nối thêm nhiều dòng, mở tệp một lần.

        Từ chối dòng mang vân tay kho khác NGAY LÚC GHI. Bắt ở đây rẻ hơn hẳn
        bắt lúc đọc: lúc đọc thì sổ đã lẫn rồi, còn ở đây chỉ là một lần ghi hỏng.
        """
        ds = list(ds)
        for qd in ds:
            if qd.van_tay_kho != self.van_tay:
                raise ValueError(
                    f"{qd.ma}: quyết định mang vân tay kho {qd.van_tay_kho!r} "
                    f"nhưng sổ này gắn với {self.van_tay!r}.\n"
                    f"  Kho đã đổi kể từ lúc quyết định đó được ra. Trộn vào là "
                    f"sàng lọc trên một tập bài, rồi báo cáo trên tập bài khác."
                )
        if not ds:
            return 0
        self.duong_dan.parent.mkdir(parents=True, exist_ok=True)
        with self.duong_dan.open("a", encoding="utf-8") as f:
            for qd in ds:
                f.write(json.dumps(qd.model_dump(mode="json"), ensure_ascii=False) + "\n")
            f.flush()
        return len(ds)

    def doc(self) -> KetQuaDocSo:
        kq = KetQuaDocSo()
        if not self.duong_dan.exists():
            return kq
        for so_dong, dong in enumerate(
            self.duong_dan.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not dong.strip():
                continue
            try:
                qd = QuyetDinh(**json.loads(dong))
            except Exception as exc:  # noqa: BLE001
                # Dòng hỏng KHÔNG được nuốt: một dòng mất là một bài mất khỏi
                # PRISMA, và im lặng thì không ai biết để đi tìm lại.
                kq.dong_hong.append((so_dong, f"{type(exc).__name__}: {exc}"))
                continue
            if qd.van_tay_kho != self.van_tay:
                kq.van_tay_la[qd.van_tay_kho] = kq.van_tay_la.get(qd.van_tay_kho, 0) + 1
                continue
            kq.quyet_dinh.append(qd)
        return kq

    def con_lai(self, ma_trong_kho: Iterable[str]) -> list[str]:
        """Mã chưa ai quyết định. Đây là thứ cho phép sàng nhiều buổi."""
        da = set(self.doc().theo_ma)
        return [m for m in ma_trong_kho if m not in da]

    def thong_ke(self) -> dict:
        """Số liệu PRISMA. Sổ này CHÍNH LÀ dữ liệu PRISMA, không phải bản sao."""
        kq = self.doc()
        moi_nhat = kq.theo_ma.values()
        theo_quyet: dict[str, int] = {}
        theo_ly_do: dict[str, int] = {}
        theo_nguoi: dict[str, int] = {}
        for qd in moi_nhat:
            theo_quyet[qd.quyet_dinh.value] = theo_quyet.get(qd.quyet_dinh.value, 0) + 1
            theo_nguoi[qd.nguoi_sang] = theo_nguoi.get(qd.nguoi_sang, 0) + 1
            if qd.quyet_dinh is Quyet.LOAI:
                theo_ly_do[qd.ly_do] = theo_ly_do.get(qd.ly_do, 0) + 1
        return {
            "tong_quyet_dinh": len(moi_nhat),
            "tong_dong_ghi": len(kq.quyet_dinh),
            "theo_quyet_dinh": theo_quyet,
            "loai_theo_ly_do": theo_ly_do,
            "theo_nguoi_sang": theo_nguoi,
            "da_doi_y": kq.da_doi_y,
            "dong_hong": kq.dong_hong,
            "van_tay_la": kq.van_tay_la,
            "phien_ban_tieu_chi": sorted({qd.phien_ban_tieu_chi for qd in moi_nhat}),
        }


def doc_ban_ghi(duong_dan: Path) -> Iterator[dict]:
    """Duyệt từng bản ghi trong kho. Kho là BẤT BIẾN — hàm này chỉ đọc."""
    data = json.loads(duong_dan.read_text(encoding="utf-8"))
    yield from data.get("ban_ghi", [])

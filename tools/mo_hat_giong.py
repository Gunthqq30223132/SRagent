"""Sinh HẠT GIỐNG (bài mồi) mà không tiêu tốn thời gian chuyên gia.

VÌ SAO CÓ TỆP NÀY — một giả định của tôi bị bác bỏ bằng dữ liệu:

Tôi đã thiết kế phép đo độ nhạy với giả định 'nguồn duy nhất đáng tin cho bài
bắt buộc phải có là trí nhớ chuyên gia', rồi yêu cầu Gun tự nêu 3-5 bài cho mỗi
chức năng. Gun phản đối là tốn thời gian người quá mức. Kiểm lại thì giả định đó
SAI: provenance_manifest.json của AnesthOS đã chứa sẵn 24 trích dẫn do chính Gun
cam kết (Surviving Sepsis Campaign, ILCOR, DAS, NAP4, ASRA, KDIGO...).

Nói cách khác: HẠT GIỐNG KHÔNG CẦN ĐƯỢC NHỚ RA — NÓ SUY RA ĐƯỢC.

NĂM BẬC NGUỒN HẠT GIỐNG, xếp theo mức ĐỘC LẬP với truy vấn đang bị kiểm.
Đây là trục quan trọng nhất, vì hạt giống lấy từ chính kết quả của truy vấn thì
không kiểm được điểm mù của truy vấn đó — nó chỉ xác nhận cái đã tìm thấy.

  Bậc 0  Danh mục tham khảo của NGUỒN TỔNG HỢP NGOÀI (UpToDate và tương đương)
         -> ĐỘC LẬP CAO NHẤT: bài được tìm theo TÊN CHỦ ĐỀ, không qua truy vấn
            nào của ta; biên tập viên dựng danh mục mà chưa từng thấy truy vấn
            của ta. Xem `tools/nguon_tong_hop.py`.
  Bậc 1  Danh mục tham khảo của tổng quan hệ thống trong kho
         -> ĐỘC LẬP CAO nhưng KHÉP KÍN MỘT PHẦN: bài tổng quan đó được tìm ra
            BẰNG CHÍNH truy vấn đang bị kiểm. Truy vấn có điểm mù thì ta không
            gặp được bài sẽ phơi bày điểm mù đó. Cần mạng.
  Bậc 2  Trích dẫn có sẵn trong dữ liệu AnesthOS
         -> ĐỘC LẬP CAO: cam kết có trước, không do truy vấn sinh ra. KHÔNG cần mạng.
  Bậc 3  Giao của nhiều truy vấn diễn đạt khác nhau
         -> ĐỘC LẬP VỪA: khác cách hỏi, nhưng cùng một kho. Cần mạng.
  Bậc 4  Bài bậc chứng cứ cao trong chính kho
         -> ĐỘC LẬP THẤP: cùng truy vấn sinh ra. Gần như tự xác nhận.
  Bậc 5  Trí nhớ chuyên gia
         -> ĐỘC LẬP CAO nhưng TỐN THỜI GIAN NGƯỜI. Để dành cho chỗ 1-4 bí.

Công cụ báo rõ hạt giống đến từ bậc nào, vì phép đo độ nhạy chỉ đáng tin bằng
đúng mức độc lập của hạt giống nuôi nó.

CẢNH GIÁC BẮT BUỘC VỀ BẬC 2: provenance_manifest ghi `synthetic: true` cho toàn
bộ tệp dữ liệu, trong khi trích dẫn lại trông như thật. Nên trích dẫn ở đây là
LỜI KHAI, chưa phải dữ kiện — phải tra ngược về nguồn mới thành hạt giống dùng
được. Chính bước tra ngược đó đồng thời là kiểm toán lời khai xuất xứ của
AnesthOS: một thao tác, hai kết quả.
"""

from __future__ import annotations

import json
import re
from enum import IntEnum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class BacNguon(IntEnum):
    """Số NHỎ = độc lập hơn với truy vấn đang bị kiểm."""

    NGUON_TONG_HOP_NGOAI = 0
    THAM_KHAO_TONG_QUAN = 1
    TRICH_DAN_ANESTHOS = 2
    GIAO_NHIEU_TRUY_VAN = 3
    BAC_CAO_TRONG_KHO = 4
    TRI_NHO_CHUYEN_GIA = 5


MO_TA_BAC: dict[BacNguon, str] = {
    BacNguon.NGUON_TONG_HOP_NGOAI: "nguồn tổng hợp ngoài, chuyên gia biên tập (ĐỘC LẬP CAO NHẤT)",
    BacNguon.THAM_KHAO_TONG_QUAN: "danh mục tham khảo của tổng quan hệ thống (độc lập cao)",
    BacNguon.TRICH_DAN_ANESTHOS: "trích dẫn có sẵn trong AnesthOS (độc lập cao, offline)",
    BacNguon.GIAO_NHIEU_TRUY_VAN: "giao của nhiều cách hỏi (độc lập vừa)",
    BacNguon.BAC_CAO_TRONG_KHO: "bậc chứng cứ cao trong kho (ĐỘC LẬP THẤP — gần tự xác nhận)",
    BacNguon.TRI_NHO_CHUYEN_GIA: "chuyên gia nêu (độc lập cao, tốn thời gian người)",
}

# Bắt DOI và PMID trong chuỗi trích dẫn tự do.
_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
_PMID = re.compile(r"\bPMID:?\s*(\d{4,8})\b", re.IGNORECASE)


class HatGiong(BaseModel):
    """Một ứng viên hạt giống. CHƯA phải hạt giống dùng được cho tới khi xác minh."""

    mo_ta: str                       # chuỗi trích dẫn nguyên văn, để truy ngược
    bac_nguon: BacNguon
    tu_tep: str = ""
    ma: str | None = None            # 'pubmed:123' — chỉ có sau khi tra ngược được
    doi: str | None = None
    da_xac_minh: bool = False

    @field_validator("mo_ta")
    @classmethod
    def _mo_ta_phai_co_noi_dung(cls, v: str) -> str:
        if len(v.strip()) < 8:
            raise ValueError(f"mô tả trích dẫn quá ngắn để truy ngược: {v!r}")
        return v.strip()

    @property
    def dung_duoc(self) -> bool:
        """Hạt giống chỉ dùng được cho phép đo khi đã tra ngược ra mã thật.

        Ứng viên chưa xác minh mà đem đo độ nhạy thì mọi truy vấn đều 'sót' nó —
        không phải vì truy vấn hụt, mà vì bài đó có thể không tồn tại.
        """
        return self.da_xac_minh and self.ma is not None


class KetQuaMo(BaseModel):
    ung_vien: list[HatGiong] = []
    bo_qua: list[tuple[str, str]] = []   # (tệp, lý do)

    @property
    def theo_bac(self) -> dict[int, int]:
        d: dict[int, int] = {}
        for h in self.ung_vien:
            d[int(h.bac_nguon)] = d.get(int(h.bac_nguon), 0) + 1
        return d

    @property
    def dung_duoc(self) -> list[HatGiong]:
        return [h for h in self.ung_vien if h.dung_duoc]


def tach_trich_dan(chuoi: str) -> list[str]:
    """Một trường citation thường gộp NHIỀU nguồn bằng dấu chấm phẩy.

    Gộp chúng thành một hạt giống là mất hết: chuỗi ghép không tra ngược được
    về bài nào cả. Tách ra thì mỗi mảnh là một ứng viên tra được.
    """
    manh = [m.strip() for m in re.split(r"[;]", chuoi) if m.strip()]
    return [m for m in manh if len(m) >= 8]


def mo_tu_provenance(duong_dan: Path, chi_tep: set[str] | None = None) -> KetQuaMo:
    """Rút ứng viên hạt giống từ provenance_manifest.json của AnesthOS.

    KHÔNG cần mạng. Đây là bậc 2 — độc lập cao vì các trích dẫn này được cam kết
    TRƯỚC và ĐỘC LẬP với bất kỳ truy vấn nào ta sẽ chạy.
    """
    kq = KetQuaMo()
    data = json.loads(duong_dan.read_text(encoding="utf-8"))
    tep = data.get("files") or {}
    if not tep:
        raise ValueError(f"{duong_dan}: không có khoá 'files' — không phải manifest xuất xứ.")

    for ten, meta in tep.items():
        if chi_tep is not None and ten not in chi_tep:
            continue
        raw = (meta.get("citation") or "").strip()
        if not raw:
            kq.bo_qua.append((ten, "không khai trích dẫn nào"))
            continue
        for manh in tach_trich_dan(raw):
            doi = _DOI.search(manh)
            pmid = _PMID.search(manh)
            kq.ung_vien.append(HatGiong(
                mo_ta=manh,
                bac_nguon=BacNguon.TRICH_DAN_ANESTHOS,
                tu_tep=ten,
                doi=doi.group(0) if doi else None,
                ma=f"pubmed:{pmid.group(1)}" if pmid else None,
                # Có DOI/PMID KHÔNG đồng nghĩa đã xác minh: manifest ghi
                # synthetic:true, nên định danh cũng có thể là bịa. Xác minh là
                # phải tra ngược về nguồn, không phải khớp biểu thức chính quy.
                da_xac_minh=False,
            ))
    return kq


def tach_chu_de_con(duong_dan_du_lieu: Path) -> list[str]:
    """Một 'chức năng' thường KHÔNG phải một bài tổng quan — mà là N bài.

    crisis_protocols.json có 8 khoá: phản vệ, co thắt thanh quản, CICO, ngừng
    tuần hoàn, ngộ độc thuốc tê, tăng thân nhiệt ác tính, chảy máu ồ ạt, hít sặc.
    Mỗi thứ có y văn riêng, thiết kế nghiên cứu riêng, hạt giống riêng. Gộp cả 8
    vào MỘT truy vấn sẽ ra một kho không phục vụ được cái nào cho tử tế.

    Khoá của chính tệp dữ liệu ĐÃ LÀ bản phân rã sẵn — không cần ai nghĩ ra.
    """
    d = json.loads(duong_dan_du_lieu.read_text(encoding="utf-8"))
    if isinstance(d, dict):
        return [k for k in d if not k.startswith("_")]
    if isinstance(d, list):
        # Danh sách phẳng (như chronic_meds 173 hoạt chất): gom theo 'class' nếu
        # có, vì 173 truy vấn riêng là vô lý còn 1 truy vấn chung thì quá rộng.
        nhom = {r.get("class") for r in d if isinstance(r, dict) and r.get("class")}
        return sorted(n for n in nhom if n)
    return []


def bao_cao(kq: KetQuaMo) -> str:
    dong = [
        f"ỨNG VIÊN HẠT GIỐNG: {len(kq.ung_vien)}",
        f"  Đã xác minh, dùng được: {len(kq.dung_duoc)}",
        "",
    ]
    for bac, n in sorted(kq.theo_bac.items()):
        dong.append(f"  bậc {bac} · {n:>3} · {MO_TA_BAC[BacNguon(bac)]}")
    if kq.bo_qua:
        dong += ["", f"  Bỏ qua {len(kq.bo_qua)} tệp:"]
        for ten, ly_do in kq.bo_qua[:10]:
            dong.append(f"    {ten}: {ly_do}")
    if not kq.dung_duoc:
        dong += [
            "",
            "  ⚠ CHƯA ứng viên nào xác minh được, nên CHƯA đo độ nhạy được.",
            "    Trích dẫn trong manifest là LỜI KHAI: tệp dữ liệu ghi synthetic:true",
            "    trong khi trích dẫn trông như thật. Phải tra ngược về nguồn.",
            "    Bước tra ngược đó đồng thời kiểm toán luôn lời khai xuất xứ.",
        ]
    return "\n".join(dong)

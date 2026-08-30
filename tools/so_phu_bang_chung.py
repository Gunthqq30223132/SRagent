"""Sổ phủ bằng chứng V1 — phân loại và đo mức phủ bằng chứng cho AnesthOS.

Đặc tả: docs/DAC_TA_V1_SO_PHU.md.
Nhiệm vụ: liệt kê mọi khẳng định lâm sàng, xếp theo mức rủi ro, và làm rõ
sự thiếu vắng bằng chứng chống lưng.

Công thức kiểm toán bảo toàn lá: $N_1 = N_2 + N_3 = N_2 + U_1 + U_2 + U_3$.
"""

from __future__ import annotations

import argparse
import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ── 1. CÁC TẬP KHOÁ ĐẶC TẢ (§2.3) ───────────────────────────────────

# Nhóm nhãn — không cần bằng chứng (định danh + trình bày)
KHOA_NHAN: set[str] = {
    "name", "id", "aliases", "category", "label", "name_vi", "label_vi",
    "title", "code", "unit", "abbr", "short", "key", "group", "icon",
    "color", "textColor",
}

# Ưu tiên 1 — sai thì chết người
KHOA_UU_TIEN_1: set[str] = {
    "critical", "dose", "smartDose", "max", "periop", "redFlags",
    "route", "routes", "weightBasis", "concentrations", "withEpi",
    "plain", "timeToDeath",
}

# Ưu tiên 2 — sai thì hại nặng
KHOA_UU_TIEN_2: set[str] = {
    "preferred", "cautions", "contraindications", "interactions",
    "drugCautions", "sideEffects", "indication", "indications",
    "timing", "conditional", "severity", "action", "urgency",
    "triggerFlags", "bleedingRisk", "range", "yellow", "low",
    "high", "technique", "techniques", "options", "required",
    "typicalAgents", "keyDrugs", "severityScore", "tier",
}

# Tệp khai xuất xứ bị loại khỏi phạm vi khẳng định lâm sàng (§2.2)
TEP_KHAI_XUAT_XU = "provenance_manifest.json"


# ── 2. CÁC KIỂU VÀ MÔ HÌNH DỮ LIỆU (§3) ─────────────────────────────

class MucPhu(str, Enum):
    """Mức phủ bằng chứng của một khẳng định."""
    KHONG_CO = "không có gì chống lưng"
    CHI_CO_NGUON = "chỉ có nguồn cấp tệp"
    CO_CHUOI_DAY_DU = "có chuỗi bằng chứng đầy đủ"


class TrangThai(str, Enum):
    """Trạng thái đối chiếu ngược (V2)."""
    DAT = "ĐẠT"
    TRUOT = "TRƯỢT"
    KHONG_KIEM_DUOC = "KHÔNG KIỂM ĐƯỢC"


class HoSoBangChung(BaseModel):
    """Hồ sơ bằng chứng cho một khẳng định lâm sàng."""
    duong_dan: str
    khoa: str
    khang_dinh: str
    muc_rui_ro: int

    nguon_khai: str | None = None
    doi_chieu_nguoc: TrangThai = TrangThai.KHONG_KIEM_DUOC
    bo_ba: list[tuple[str, str, str]] = Field(default_factory=list)
    bac_chung_cu: int | None = None
    do_manh: str | None = None

    @property
    def muc_phu(self) -> MucPhu:
        """SUY RA từ các trường, không bao giờ gán tay (R1, R2)."""
        if (
            self.doi_chieu_nguoc == TrangThai.DAT
            and len(self.bo_ba) > 0
            and self.bac_chung_cu is not None
        ):
            return MucPhu.CO_CHUOI_DAY_DU
        if self.nguon_khai:
            return MucPhu.CHI_CO_NGUON
        return MucPhu.KHONG_CO


def xep_muc_rui_ro(khoa: str) -> int:
    """Xếp mức rủi ro theo quy tắc §2.3. Mặc định là 3."""
    if khoa in KHOA_UU_TIEN_1:
        return 1
    if khoa in KHOA_UU_TIEN_2:
        return 2
    return 3


# ── 3. DUYỆT CÂY DỮ LIỆU (§2.1, §2.2) ───────────────────────────────

def _doc_xuat_xu_manifest(thu_muc: Path) -> dict[str, str]:
    """Đọc tệp khai xuất xứ nếu có để lấy nguồn cấp tệp."""
    tep_manifest = thu_muc / TEP_KHAI_XUAT_XU
    if not tep_manifest.is_file():
        return {}
    try:
        with open(tep_manifest, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    kq: dict[str, str] = {}
    files_map = data.get("files", {}) if isinstance(data, dict) else {}
    for ten_tep, info in files_map.items():
        if isinstance(info, dict):
            nguon = info.get("citation") or info.get("source") or ""
            if nguon:
                kq[ten_tep] = str(nguon)
        elif isinstance(info, str):
            kq[ten_tep] = info
    return kq


def _duyet_la(
    node: Any,
    ten_tep: str,
    duong_dan_hien_tai: str,
    khoa_hien_tai: str,
    nguon_tep: str | None,
    danh_sach: list[HoSoBangChung],
) -> None:
    """Duyệt đệ quy cây dữ liệu JSON theo đúng quy tắc §2.1."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k.startswith("_"):
                continue
            child_path = f"{duong_dan_hien_tai}.{k}" if duong_dan_hien_tai else k
            _duyet_la(v, ten_tep, child_path, k, nguon_tep, danh_sach)
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            child_path = f"{duong_dan_hien_tai}.{idx}" if duong_dan_hien_tai else str(idx)
            _duyet_la(item, ten_tep, child_path, khoa_hien_tai, nguon_tep, danh_sach)
    else:
        # Giá trị vô hướng (scalar) = 1 lá
        if khoa_hien_tai in KHOA_NHAN:
            # Nhóm nhãn/định danh/trình bày: không tính là khẳng định lâm sàng
            return
        
        full_path = f"{ten_tep}#{duong_dan_hien_tai}"
        val_str = "" if node is None else str(node)
        rui_ro = xep_muc_rui_ro(khoa_hien_tai)

        danh_sach.append(
            HoSoBangChung(
                duong_dan=full_path,
                khoa=khoa_hien_tai,
                khang_dinh=val_str,
                muc_rui_ro=rui_ro,
                nguon_khai=nguon_tep,
            )
        )


def quet_khang_dinh(thu_muc_du_lieu: Path) -> list[HoSoBangChung]:
    """Quét toàn bộ thư mục dữ liệu AnesthOS và trả về danh sách khẳng định lâm sàng."""
    thu_muc = Path(thu_muc_du_lieu)
    if not thu_muc.is_dir():
        return []

    xuat_xu = _doc_xuat_xu_manifest(thu_muc)
    danh_sach: list[HoSoBangChung] = []

    # Tìm mọi tệp .json trong thư mục, sắp xếp tên tệp để kết quả luôn tất định
    tep_json_list = sorted(thu_muc.glob("**/*.json"))

    for p in tep_json_list:
        if p.name == TEP_KHAI_XUAT_XU or p.name.startswith("._") or p.name.endswith(".bak"):
            continue
        
        rel_name = p.name
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        nguon = xuat_xu.get(rel_name)
        _duyet_la(data, rel_name, "", "", nguon, danh_sach)

    return danh_sach


# ── 4. BÁO CÁO MỨC PHỦ (§3) ─────────────────────────────────────────

def bao_cao_phu(ds: list[HoSoBangChung]) -> str:
    """Tạo báo cáo mức phủ bằng chứng theo phân tầng rủi ro."""
    tong = len(ds)
    if tong == 0:
        return "SỔ PHỦ BẰNG CHỨNG V1\n  Không có khẳng định lâm sàng nào."

    # Thống kê theo mức phủ
    so_khong_co = sum(1 for h in ds if h.muc_phu == MucPhu.KHONG_CO)
    so_chi_nguon = sum(1 for h in ds if h.muc_phu == MucPhu.CHI_CO_NGUON)
    so_day_du = sum(1 for h in ds if h.muc_phu == MucPhu.CO_CHUOI_DAY_DU)

    # Thống kê theo mức rủi ro
    m1 = [h for h in ds if h.muc_rui_ro == 1]
    m2 = [h for h in ds if h.muc_rui_ro == 2]
    m3 = [h for h in ds if h.muc_rui_ro == 3]

    lines = [
        "=" * 68,
        "SỔ PHỦ BẰNG CHỨNG V1 — TỔNG KẾT MỨC PHỦ LÂM SÀNG",
        "=" * 68,
        f"Tổng số khẳng định lâm sàng : {tong:,}",
        f"  - Ưu tiên 1 (chết người)    : {len(m1):,} ({len(m1)/tong:.1%})",
        f"  - Ưu tiên 2 (hại nặng)      : {len(m2):,} ({len(m2)/tong:.1%})",
        f"  - Ưu tiên 3 (khác)          : {len(m3):,} ({len(m3)/tong:.1%})",
        "",
        "PHÂN BỐ THEO MỨC BẰNG CHỨNG HIỆN CÓ:",
        f"  1. Có chuỗi bằng chứng đầy đủ : {so_day_du:,} ({so_day_du/tong:.1%})",
        f"  2. Chỉ có nguồn cấp tệp        : {so_chi_nguon:,} ({so_chi_nguon/tong:.1%})",
        f"  3. Không có gì chống lưng     : {so_khong_co:,} ({so_khong_co/tong:.1%})",
        "",
        "CHI TIẾT THEO TỪNG MỨC RỦI RO:",
        f"  [Mức 1 - Chết người] : {len(m1)} khẳng định | Không có gì: {sum(1 for h in m1 if h.muc_phu == MucPhu.KHONG_CO)} | Chỉ nguồn tệp: {sum(1 for h in m1 if h.muc_phu == MucPhu.CHI_CO_NGUON)} | Đầy đủ: {sum(1 for h in m1 if h.muc_phu == MucPhu.CO_CHUOI_DAY_DU)}",
        f"  [Mức 2 - Hại nặng]   : {len(m2)} khẳng định | Không có gì: {sum(1 for h in m2 if h.muc_phu == MucPhu.KHONG_CO)} | Chỉ nguồn tệp: {sum(1 for h in m2 if h.muc_phu == MucPhu.CHI_CO_NGUON)} | Đầy đủ: {sum(1 for h in m2 if h.muc_phu == MucPhu.CO_CHUOI_DAY_DU)}",
        f"  [Mức 3 - Khác]       : {len(m3)} khẳng định | Không có gì: {sum(1 for h in m3 if h.muc_phu == MucPhu.KHONG_CO)} | Chỉ nguồn tệp: {sum(1 for h in m3 if h.muc_phu == MucPhu.CHI_CO_NGUON)} | Đầy đủ: {sum(1 for h in m3 if h.muc_phu == MucPhu.CO_CHUOI_DAY_DU)}",
        "=" * 68,
    ]
    return "\n".join(lines)


# ── 5. GIAO DIỆN DÒNG LỆNH (§4) ──────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sổ phủ bằng chứng V1 cho AnesthOS")
    parser.add_argument(
        "--du-lieu",
        type=Path,
        required=True,
        help="Đường dẫn tới thư mục dữ liệu AnesthOS (ví dụ src/domain/data/)",
    )
    args = parser.parse_args(argv)

    ds = quet_khang_dinh(args.du_lieu)
    print(bao_cao_phu(ds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Từ MỘT vấn đề thô -> điểm quyết định -> khung tuyển chọn -> truy vấn.

KHỞI ĐỘNG LẠNH: chủ đề mới toanh, không ai đưa bài mồi, không có gì sẵn.

VÌ SAO NEO VÀO QUYẾT ĐỊNH CHỨ KHÔNG NEO VÀO CHỦ ĐỀ:

'Quản lý kháng đông' là một CHỦ ĐỀ. Nhưng hệ tiêu thụ (AnesthOS) không xuất ra
chủ đề — nó xuất ra khuyến cáo tại ĐIỂM QUYẾT ĐỊNH. Neo vào chủ đề cho ra một
kho lớn không phục vụ tử tế được quyết định nào; neo vào quyết định cho ra N kho
nhỏ, mỗi kho trả lời đúng một câu hỏi trả lời được.

Hệ quả 80/20: DANH SÁCH QUYẾT ĐỊNH SUY RA ĐƯỢC TỪ LƯỢC ĐỒ ĐẦU RA. Trường nào
ứng dụng phải điền thì đó là một quyết định, và mỗi quyết định là một câu hỏi
nghiên cứu. Không cần trí nhớ chuyên gia để liệt kê ra.

Nguyên tắc này TRUNG LẬP LĨNH VỰC: 'hệ tiêu thụ cần xuất ra gì thì đó là câu hỏi
nghiên cứu'. Đổi sang dự án phi y khoa vẫn đúng nguyên văn.

MÙ KẾT CỤC ĐƯỢC BẢO ĐẢM BẰNG CẤU TRÚC, KHÔNG BẰNG LỜI DẶN:

Nguyên tắc O-blind nói: không bao giờ loại nghiên cứu dựa trên thứ nó TÌM THẤY,
chỉ dựa trên thứ nó KHẢO SÁT. Một lời dặn trong tài liệu thì sẽ có ngày ai đó
quên. Nên ở đây `ket_cuc` được GHI LẠI nhưng hàm dựng truy vấn KHÔNG BAO GIỜ đọc
tới nó. Vi phạm O-blind trở thành chuyện không viết ra được, chứ không phải
chuyện phải nhớ đừng làm.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class DangCauHoi(str, Enum):
    """Năm dạng câu hỏi. Dạng quyết định thiết kế nghiên cứu nào là tối ưu."""

    DIEU_TRI = "therapy"
    TAC_HAI = "harm"
    CHAN_DOAN = "diagnosis"
    TIEN_LUONG = "prognosis"
    CHAN_DOAN_PHAN_BIET = "differential"


# Dạng nào BẮT BUỘC phải có nhóm đối chiếu. Bảng này chặn lỗi đã nêu ở bản đồ
# chức năng: bắt mọi dạng phải có đối chiếu sẽ loại sạch nghiên cứu mà tiên
# lượng và chẩn đoán phân biệt cần — và loại một cách im lặng.
DOI_CHIEU_BAT_BUOC: dict[DangCauHoi, bool] = {
    DangCauHoi.DIEU_TRI: True,
    DangCauHoi.TAC_HAI: True,          # nhóm không phơi nhiễm
    DangCauHoi.CHAN_DOAN: False,       # tiêu chuẩn vàng, không phải đối chiếu
    DangCauHoi.TIEN_LUONG: False,
    DangCauHoi.CHAN_DOAN_PHAN_BIET: False,
}

# Thiết kế nghiên cứu tối ưu theo dạng — dùng để XẾP HẠNG, tuyệt đối không dùng
# để lọc lúc tìm (xem quet_that.py: loại ở cửa tìm thì không để lại vết).
THIET_KE_TOI_UU: dict[DangCauHoi, list[str]] = {
    DangCauHoi.DIEU_TRI: ["Randomized Controlled Trial", "Meta-Analysis",
                          "Systematic Review", "Practice Guideline"],
    DangCauHoi.TAC_HAI: ["Cohort Studies", "Case-Control Studies",
                         "Observational Study", "Case Reports"],
    DangCauHoi.CHAN_DOAN: ["Cross-Sectional Studies", "Validation Study"],
    DangCauHoi.TIEN_LUONG: ["Cohort Studies", "Prospective Studies"],
    DangCauHoi.CHAN_DOAN_PHAN_BIET: ["Cross-Sectional Studies"],
}


class DiemQuyetDinh(BaseModel):
    """Một câu hỏi mà hệ tiêu thụ BẮT BUỘC phải trả lời được.

    Đây là đơn vị công việc thật, không phải 'chủ đề'. Suy ra từ lược đồ đầu ra:
    mỗi trường ứng dụng phải điền là một điểm quyết định.
    """

    ma: str
    cau_hoi: str                    # câu hỏi bác sĩ đứng trước, viết bằng lời thường
    dau_ra_can_co: str              # AnesthOS phải xuất ra CÁI GÌ ở đây
    dang: DangCauHoi

    @field_validator("cau_hoi", "dau_ra_can_co")
    @classmethod
    def _phai_cu_the(cls, v: str) -> str:
        if len(v.strip()) < 12:
            raise ValueError(f"mô tả quá mơ hồ để dựng truy vấn: {v!r}")
        return v.strip()


class KhungTuyenChon(BaseModel):
    """Khung tuyển chọn TRUNG LẬP LĨNH VỰC. PICO là một cách điền vào khung này.

    Tên trường cố ý không dùng P/I/C/O: bảng 5 dạng câu hỏi cho thấy chính trong
    y khoa PICO đã tự biến dạng (C rỗng ở 3/5 dạng, I thành phơi nhiễm, O thành
    tiêu chuẩn vàng). Cái sống sót qua cả 5 biến thể mới là khung thật, và nó
    không có gì y khoa.
    """

    diem_quyet_dinh: str
    dang: DangCauHoi

    pham_vi: list[str] = Field(min_length=1)      # lớp đối tượng nào trong kho
    mat_khao_sat: list[str] = Field(min_length=1)  # thứ đang được xét
    doi_chieu: list[str] = []                      # TUỲ dạng câu hỏi
    ket_cuc: list[str] = []                        # GHI LẠI — không bao giờ để lọc
    phien_ban: str = "nhap-1"

    @model_validator(mode="after")
    def _doi_chieu_dung_ky_vong_cua_dang(self) -> "KhungTuyenChon":
        if DOI_CHIEU_BAT_BUOC[self.dang] and not self.doi_chieu:
            raise ValueError(
                f"{self.diem_quyet_dinh}: dạng {self.dang.value} cần nhóm đối chiếu "
                f"(điều trị cần nhóm so sánh; tác hại cần nhóm không phơi nhiễm)."
            )
        return self

    @model_validator(mode="after")
    def _ket_cuc_phai_duoc_ghi(self) -> "KhungTuyenChon":
        """Kết cục KHÔNG dùng để lọc, nhưng vẫn BẮT BUỘC phải khai.

        Hai việc khác nhau: khai kết cục là để biết bài nào có ích khi tổng hợp
        và để dựng bảng GRADE. Không khai thì đến bước tổng hợp mới phát hiện là
        chưa ai định nghĩa 'có ích' nghĩa là gì.
        """
        if not self.ket_cuc:
            raise ValueError(
                f"{self.diem_quyet_dinh}: phải khai kết cục quan tâm. Nó KHÔNG "
                f"dùng để loại bài, nhưng thiếu nó thì không dựng được bảng tổng hợp."
            )
        if len(self.ket_cuc) > 7:
            raise ValueError(
                f"{self.diem_quyet_dinh}: {len(self.ket_cuc)} kết cục, tối đa 7. "
                f"Quá 7 thì bảng tóm tắt phát hiện mất tác dụng — không ai đọc nổi."
            )
        return self

    def thanh_truy_van(self) -> str:
        """Dựng truy vấn CHỈ từ PHẠM VI và MẶT KHẢO SÁT.

        BA THỨ CỐ Ý KHÔNG CÓ MẶT Ở ĐÂY, cùng một lý do:

          ket_cuc      — mù kết cục: không loại theo thứ nghiên cứu TÌM THẤY
          THIET_KE     — thiết kế là tiêu chí xếp hạng lúc sàng
          doi_chieu    — xem dưới

        VÌ SAO ĐỐI CHIẾU BỊ GỠ RA (đo được, không phải phán đoán): lần chạy thật
        3 câu hỏi tiền mê cho thấy câu DUY NHẤT không có mệnh đề đối chiếu đạt
        100% (43/43 bài tổng quan lọt vào kho), còn hai câu có đối chiếu rụng
        xuống 18% và 6%.

        Nguyên nhân: mệnh đề đối chiếu là các CỤM NGUYÊN VĂN. Một thử nghiệm so
        nhịn ăn dài với nhịn ăn ngắn gần như không bao giờ viết đúng chữ
        'prolonged fasting' trong tóm tắt. Bộ lọc đó không lọc theo KHÁI NIỆM —
        nó lọc theo CÁCH DIỄN ĐẠT.

        Và đó đúng ba lý do đã dùng để gỡ PUB_TYPE ra khỏi truy vấn: phụ thuộc
        cách người khác diễn đạt, loại ở cửa tìm KHÔNG ĐỂ LẠI VẾT, và đã có chỗ
        khác xử tốt hơn. Một nghiên cứu CÓ nhóm đối chứng hay không là thứ biết
        được bằng cách ĐỌC nó, không phải bằng việc tóm tắt chứa cụm nào.

        `doi_chieu` VẪN BẮT BUỘC KHAI cho dạng điều trị và tác hại — nó là một
        phần định nghĩa câu hỏi, và là tiêu chí sàng. Chỉ khác: nó không còn là
        bộ lọc lúc tìm.
        """
        return f"({_nhom(self.pham_vi)}) AND ({_nhom(self.mat_khao_sat)})"

    def truy_van_mo_dau(self) -> str:
        """Truy vấn RỘNG, nhắm vào tổng quan và hướng dẫn, để GẶT HẠT GIỐNG.

        Khởi động lạnh không có bài mồi nào. Nhưng y văn tự mang bản đồ của nó:
        tổng quan hệ thống và hướng dẫn thực hành CÓ TỒN TẠI và tìm được, còn
        danh mục tham khảo của chúng là tập bài mà chuyên gia trong ngành đã
        chọn sẵn — độc lập với ta.

        LƯU Ý QUAN TRỌNG sau khi gỡ mệnh đề đối chiếu khỏi truy vấn chính: câu
        này nay là truy vấn chính CỘNG THÊM bộ lọc loại bài, tức là TẬP CON chặt
        của truy vấn chính. Nên phép so 'tổng quan có lọt vào kho không' luôn ra
        100% — xem `phep_do_chong_lan_co_hieu_luc()`.
        """
        return (
            f"{self.thanh_truy_van()} "
            f'AND (PUB_TYPE:"Systematic Review" OR PUB_TYPE:"Meta-Analysis" '
            f'OR PUB_TYPE:"Practice Guideline" OR PUB_TYPE:"Guideline")'
        )

    def cum_trung_giua_hai_menh_de(self) -> set[str]:
        """Cụm nào xuất hiện ở CẢ phạm vi lẫn mặt khảo sát.

        Lỗi này lộ ra ở lần chạy thật: câu nhịn ăn cho kho 46.197 bài, gấp 27
        lần câu đường thở. Vì `pham_vi` chứa KW:"Fasting" và `mat_khao_sat`
        CŨNG chứa KW:"Fasting" — hai mệnh đề trùng khái niệm nên phép AND giữa
        chúng gần như không thu hẹp gì.

        Đây là lỗi IM LẶNG: truy vấn vẫn hợp lệ, vẫn trả kết quả, chỉ là kết quả
        rộng gấp chục lần dự tính. Hai mệnh đề phải là HAI TRỤC KHÁC NHAU —
        'ai/cái gì' và 'đang xét khía cạnh nào' — thì AND mới có nghĩa.
        """
        def chuan(ds):
            return {t.strip().strip('"').split(":", 1)[-1].strip('"').lower() for t in ds}
        return chuan(self.pham_vi) & chuan(self.mat_khao_sat)

    def phep_do_chong_lan_co_hieu_luc(self) -> bool:
        """Phép so mở-đầu-với-chính có nói lên điều gì không?

        KHÔNG, khi truy vấn mở đầu chỉ là truy vấn chính cộng thêm ràng buộc:
        lúc đó nó là tập con chặt, độ phủ luôn 100%, và báo '✓' là báo một
        thành tích không tồn tại. Đúng kiểu cột 'Verified' tự khai mà cả hệ
        thống này dựng lên để chặn.

        Phép so chỉ có hiệu lực khi hai truy vấn KHÁC NHAU ở chỗ truy vấn chính
        có ràng buộc mà mở đầu không có. Sau khi gỡ đối chiếu, điều đó không còn
        đúng nữa — nên phải nói thẳng là vô hiệu, thay vì im lặng báo đạt.
        """
        return not self.truy_van_mo_dau().startswith(self.thanh_truy_van())

    def truy_van_thieu(self, bo: str) -> str:
        """Truy vấn BỎ HẲN một mệnh đề. CHỈ MÔ TẢ mức thu hẹp, KHÔNG đo độ nhạy.

        ĐÍNH CHÍNH — bản đầu của hàm này đi kèm một kết luận SAI, và lần chạy
        thật đã lộ ra. Bỏ `pham_vi` khỏi câu kháng đông cho 20.740 bài tổng quan
        nhưng chỉ 24 nằm trong kho (0%), và tôi in ra 'mệnh đề này đang cắt mất
        bài đúng chủ đề'. Sai: bỏ phạm vi nghĩa là tìm MỌI bài tổng quan về chu
        phẫu, phần lớn không liên quan kháng đông. Tỷ lệ thấp ở đây là mệnh đề
        phạm vi ĐANG LÀM ĐÚNG VIỆC thu hẹp, không phải nó loại nhầm.

        Gốc rễ: bỏ một mệnh đề làm ĐỔI LUÔN CHỦ ĐỀ, nên bài tìm được không còn
        bảo đảm liên quan. Không suy ra được tính liên quan từ việc thuộc tập
        nào. Phép này KHÔNG đo được độ nhạy, và không được gắn dấu đạt/trượt.

        Đo độ nhạy thật cần một tập bài ĐÃ BIẾT là liên quan, lấy độc lập —
        danh mục tham khảo của chính các bài tổng quan đã gặt. Đó là việc còn lại.
        """
        con = {"pham_vi": self.mat_khao_sat, "mat_khao_sat": self.pham_vi}
        if bo not in con:
            raise ValueError(f"chỉ bỏ được 'pham_vi' hoặc 'mat_khao_sat', không phải {bo!r}")
        return (
            f"({_nhom(con[bo])}) "
            f'AND (PUB_TYPE:"Systematic Review" OR PUB_TYPE:"Meta-Analysis" '
            f'OR PUB_TYPE:"Practice Guideline" OR PUB_TYPE:"Guideline")'
        )


def _nhom(ds: list[str]) -> str:
    """Nối các cụm bằng OR, bọc nháy đúng MỘT lần.

    Lỗi này lộ ra khi chạy trên bộ câu hỏi tiền mê thật: cụm trong tệp hồ sơ đã
    mang sẵn nháy (`"fasting duration"`), bọc thêm lần nữa thành `""fasting
    duration""` — Europe PMC không hiểu, và truy vấn hỏng theo kiểu IM LẶNG vì
    nó vẫn là chuỗi hợp lệ, chỉ trả về kết quả sai.

    Cụm mang thẻ trường (`KW:`, `PUB_TYPE:`) giữ nguyên, vì thẻ trường nằm ngoài
    phần được bọc nháy.
    """
    ra: list[str] = []
    for t in ds:
        t = t.strip()
        if ":" in t:
            ra.append(t)
        else:
            ra.append(f'"{t.strip(chr(34))}"')
    return " OR ".join(ra)


def tu_luoc_do_dau_ra(luoc_do: dict[str, Any], tien_to: str = "") -> list[str]:
    """Duyệt lược đồ đầu ra, trả về đường dẫn tới từng trường lá.

    Mỗi trường lá là một thứ hệ tiêu thụ phải điền, tức là một điểm quyết định
    ứng viên. Đây là bước biến 'liệt kê câu hỏi nghiên cứu' từ việc nhớ ra thành
    việc đọc mã.
    """
    ra: list[str] = []
    for khoa, gia_tri in luoc_do.items():
        if khoa.startswith("_"):
            continue
        duong = f"{tien_to}.{khoa}" if tien_to else khoa
        if isinstance(gia_tri, dict) and gia_tri:
            ra.extend(tu_luoc_do_dau_ra(gia_tri, duong))
        else:
            ra.append(duong)
    return ra


def goi_y_dang(cau_hoi: str) -> DangCauHoi:
    """Đoán dạng câu hỏi từ lời văn. GỢI Ý, không phải phán quyết.

    Đoán sai dạng là sai đắt: nó kéo theo sai cả kỳ vọng về nhóm đối chiếu lẫn
    thiết kế nghiên cứu tối ưu. Nên hàm này chỉ đặt điểm khởi đầu, và người/máy
    ở tầng trên vẫn phải xác nhận — sai ở đây lộ ra ngay tại phép đo độ nhạy.
    """
    t = cau_hoi.lower()
    if any(k in t for k in ("nguy cơ", "biến chứng", "tác hại", "an toàn", "ngộ độc")):
        return DangCauHoi.TAC_HAI
    if any(k in t for k in ("xét nghiệm", "chẩn đoán", "phát hiện", "tầm soát")):
        return DangCauHoi.CHAN_DOAN
    if any(k in t for k in ("tiên lượng", "dự đoán", "khả năng xảy ra")):
        return DangCauHoi.TIEN_LUONG
    return DangCauHoi.DIEU_TRI

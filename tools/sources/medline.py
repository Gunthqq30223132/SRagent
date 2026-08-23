"""Đọc định dạng MEDLINE — đường vòng khi eutils bị chặn nhưng web PubMed thì không.

VÌ SAO CÓ TỆP NÀY — một dữ kiện đo được, không phải phỏng đoán:

Lần chạy thử đầu tiên cho ra một mâu thuẫn đáng chú ý. Spark TÌM được trên
PubMed (1.767 kết quả, 10 PMID, cả 10 đều là bài có thật), nhưng khi gọi
`eutils.ncbi.nlm.nih.gov/efetch` để tải bản gốc thì bị chặn (302 -> misuse.ncbi).
Máy của Gun cũng bị chặn y hệt ở đúng endpoint đó.

Mâu thuẫn này chỉ có một lời giải: hai host khác nhau, hai chính sách chặn khác
nhau. `eutils.*` (cổng API) đang chặn gắt; `pubmed.ncbi.nlm.nih.gov` (giao diện
web) thì Spark vẫn vào được — chính nó vừa dùng để tìm ra 10 bài kia.

Giao diện web có sẵn nút xuất bản ghi ở định dạng MEDLINE:

    https://pubmed.ncbi.nlm.nih.gov/<pmid>/?format=pubmed

Trả về văn bản thuần, có cấu trúc, đủ mọi trường ta cần (PMID/TI/AB/FAU/DP/PT).
Nên ta viết bộ đọc cho định dạng đó. KHÔNG đổi gì về mặt tin cậy: đây vẫn là
'pubmed-qua-spark' hạng 3 như đường efetch, vì câu hỏi tin-hay-không là câu hỏi
về NGƯỜI CHUYỂN THƯ, không phải về định dạng lá thư.

CẢNH GIÁC ĐẶC THÙ CỦA ĐỊNH DẠNG NÀY: MEDLINE nhạy với khoảng trắng. Dòng nối
tiếp của một trường được nhận ra bằng SÁU DẤU CÁCH đầu dòng. Nếu ai đó dán văn
bản qua Google Doc, qua trình soạn thảo tự canh lề, hay "dọn cho gọn", phần thụt
lề biến mất — và bản ghi vẫn phân tích được nhưng TÓM TẮT BỊ CỤT. Đó là kiểu
hỏng im lặng tệ nhất, nên `parse_medline` bắt riêng nó thay vì đọc cho xong.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sr_agent.errors import LayoutParseError
from sr_agent.models.schemas import DocStatus, Document
from tools.sources.pubmed import _MONTHS, evidence_level

# Cùng nguồn, cùng hạng với đường efetch-qua-Spark. Đăng ký ở spark_efetch.py;
# import để chắc chắn sổ đăng ký đã có mục này dù tệp nào được nạp trước.
from tools.sources.spark_efetch import SparkEfetchReader  # noqa: F401

NGUON = "pubmed-qua-spark"
HANG_UY_TIN = 3

# Nhãn trường MEDLINE: 4 ký tự căn trái, rồi '- '. Ví dụ 'PMID- ', 'DP  - '.
_NHAN = re.compile(r"^([A-Z][A-Z0-9]{0,3}) *- (.*)$")
_NOI_TIEP = re.compile(r"^ {2,}(\S.*)$")


def _gop_ngay(dp: str) -> datetime | None:
    """DP của MEDLINE: '2021 Jun 9', '2023 May', '2021', '2024 Jan-Feb'."""
    m = re.search(r"(\d{4})", dp)
    if not m:
        return None
    year = int(m.group(1))
    thang = re.search(r"\b([A-Za-z]{3})[a-z]*\b", dp)
    month = _MONTHS.get(thang.group(1).lower(), 1) if thang else 1
    ngay = re.search(r"\b(\d{1,2})\b(?!\d)", dp[m.end():])
    day = int(ngay.group(1)) if ngay and 1 <= int(ngay.group(1)) <= 31 else 1
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return datetime(year, 1, 1, tzinfo=timezone.utc)


def _tach_ban_ghi(text: str) -> list[list[str]]:
    """Cắt văn bản thành từng bản ghi. Ranh giới là dòng trống giữa hai khối."""
    ban_ghi: list[list[str]] = []
    hien_tai: list[str] = []
    for dong in text.splitlines():
        if not dong.strip():
            if hien_tai:
                ban_ghi.append(hien_tai)
                hien_tai = []
            continue
        hien_tai.append(dong)
    if hien_tai:
        ban_ghi.append(hien_tai)
    return ban_ghi


def _doc_truong(dong_list: list[str], stt: int) -> dict[str, list[str]]:
    """Gom các dòng của một bản ghi thành bản đồ nhãn -> danh sách giá trị.

    Bắt lỗi mất thụt lề ngay tại đây: một dòng không mang nhãn mà cũng không
    thụt lề là dấu hiệu văn bản đã bị trình soạn thảo canh lề lại.
    """
    truong: dict[str, list[str]] = {}
    nhan_cuoi: str | None = None
    for dong in dong_list:
        m = _NHAN.match(dong)
        if m:
            nhan_cuoi = m.group(1)
            truong.setdefault(nhan_cuoi, []).append(m.group(2).strip())
            continue
        n = _NOI_TIEP.match(dong)
        if n and nhan_cuoi:
            truong[nhan_cuoi][-1] += " " + n.group(1).strip()
            continue
        raise LayoutParseError(
            f"Bản ghi #{stt}: dòng không mang nhãn MEDLINE và cũng không thụt lề:\n"
            f"    {dong[:100]!r}\n"
            f"  Gần như chắc chắn văn bản đã bị canh lề lại (dán qua Google Doc, "
            f"trình soạn thảo tự bỏ khoảng trắng đầu dòng). Định dạng MEDLINE nhạy "
            f"với khoảng trắng — mất thụt lề là mất phần nối tiếp của tóm tắt.\n"
            f"  Cách sửa: tải lại bằng nút Save > PubMed trên trang PubMed, nộp "
            f"đúng tệp .txt tải về, không sao chép dán."
        )
    return truong


def parse_medline(text: str) -> list[Document]:
    """Phân tích văn bản MEDLINE thành Document. Hỏng thì kêu to, không đọc bừa."""
    if not text.strip():
        raise LayoutParseError("Tệp MEDLINE rỗng — không có gì để đọc.")
    if "PMID-" not in text:
        raise LayoutParseError(
            "Không tìm thấy nhãn 'PMID-' nào — đây không phải định dạng MEDLINE.\n"
            f"  120 ký tự đầu nhận được: {text[:120]!r}\n"
            "  Nhắc: URL phải kết thúc bằng '?format=pubmed'. Thiếu đuôi đó thì "
            "PubMed trả về HTML trang web, không phải bản ghi."
        )

    docs: list[Document] = []
    for stt, dong_list in enumerate(_tach_ban_ghi(text), start=1):
        truong = _doc_truong(dong_list, stt)
        pmids = truong.get("PMID", [])
        if not pmids:
            raise LayoutParseError(
                f"Bản ghi #{stt} không có PMID. Bản ghi thiếu định danh thì không "
                f"đối chiếu được với phiếu, nên không nhận."
            )
        pmid = pmids[0].strip()
        if not pmid.isdigit():
            raise LayoutParseError(f"Bản ghi #{stt}: PMID {pmid!r} không phải số.")

        # FAU ('Kovacs, Michael J') đầy đủ hơn AU ('Kovacs MJ') — ưu tiên FAU.
        authors = truong.get("FAU") or truong.get("AU") or []
        pub_types = truong.get("PT", [])
        dp = (truong.get("DP") or truong.get("DEP") or [""])[0]

        docs.append(Document(
            uid="",
            source=NGUON,
            source_id=f"{NGUON}:{pmid}",
            authority_tier=HANG_UY_TIN,
            title=(truong.get("TI") or [""])[0].strip(),
            abstract=(truong.get("AB") or [None])[0],
            authors=[a.strip() for a in authors if a.strip()],
            published_date=_gop_ngay(dp),
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            status=DocStatus.FETCHED,
            evidence_level=evidence_level(pub_types),
        ))
    return docs


def canh_bao_tom_tat_cut(docs: list[Document], nguong: int = 200) -> list[str]:
    """Tóm tắt ngắn bất thường là dấu hiệu bản ghi bị cắt giữa chừng.

    Tách riêng khỏi parse_medline vì đây là NGHI NGỜ chứ không phải lỗi chắc
    chắn: có bài tóm tắt ngắn thật. Cảnh báo để người xem, không tự ý loại.
    """
    canh_bao: list[str] = []
    for d in docs:
        if d.abstract is None:
            canh_bao.append(f"{d.source_id}: KHÔNG có tóm tắt")
        elif len(d.abstract) < nguong:
            canh_bao.append(
                f"{d.source_id}: tóm tắt chỉ {len(d.abstract)} ký tự "
                f"(dưới {nguong}) — kiểm xem có bị cắt không"
            )
    return canh_bao

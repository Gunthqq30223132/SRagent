"""Nguồn Europe PMC (EMBL-EBI) — bản sao MEDLINE truy cập được, tải hàng loạt được.

VÌ SAO NGUỒN NÀY GỠ ĐƯỢC HAI NÚT THẮT CÙNG LÚC:

Nút 1 — BỊ CHẶN. `eutils.ncbi.nlm.nih.gov` chặn cả máy của Gun lẫn Spark
(302 -> misuse.ncbi). Europe PMC là dịch vụ do EMBL-EBI vận hành, API mở, không
cần khoá, và đã kiểm chứng THẬT từ máy Gun ngày 2026-08-23: trả về đầy đủ bản
ghi BRIDGE kèm pmid, pmcid, doi. Không còn phải nhờ ai chuyển thư.

Nút 2 — ĐỘ PHỦ 0,57%. Đây mới là chỗ quan trọng, và nó là hệ quả tình cờ của
thiết kế API chứ không phải mục tiêu: với `resultType=core`, Europe MC trả
TOÀN VĂN BẢN GHI (có cả tóm tắt) NGAY TRONG KẾT QUẢ TÌM KIẾM. Không cần bước
fetch riêng cho từng bài.

  PubMed  : 1 lần esearch  + 9 lần efetch theo lô  = 10 request, 2 giai đoạn
  EuroPMC : 2 lần search (pageSize=1000)           = 2 request, 1 giai đoạn

Sàng 1.767 bài không còn là chuyện phải mở 1.767 trang web. Nó là hai request.
Nút thắt độ phủ chưa bao giờ nằm ở khả năng phán đoán — nó nằm ở đường truyền.

TRUNG THỰC VỀ HẠNG UY TÍN: Europe PMC gộp nhiều kho khác nhau vào một chỗ, và
trường `source` của mỗi bản ghi nói rõ nó từ đâu ra. Bài MEDLINE đã bình duyệt
và bản tiền ấn phẩm chưa ai duyệt KHÔNG được cùng hạng. Ta đọc trường đó và cho
hạng theo nó, thay vì gán phẳng một hạng cho cả nguồn.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from sr_agent.config import UNKNOWN_SOURCE_TIER, register_source
from sr_agent.errors import LayoutParseError
from sr_agent.ingest.base import get_with_retry
from sr_agent.models.schemas import DocStatus, Document
from tools.sources.pubmed import evidence_level

REST = "https://www.ebi.ac.uk/europepmc/webservices/rest"
SEARCH = f"{REST}/search"

EPMC_ID_PATTERN = re.compile(r"^europepmc:[A-Z]{3}:[A-Za-z0-9._-]{1,32}$")

register_source("europepmc", id_pattern=EPMC_ID_PATTERN, authority_tier=1)

# Kho con của Europe PMC -> hạng uy tín. Bình duyệt và chưa bình duyệt phải khác
# hạng, nếu không thì cả tầng chấm điểm phía trên mất ý nghĩa.
HANG_THEO_KHO: dict[str, int] = {
    "MED": 1,   # MEDLINE/PubMed — đã bình duyệt, NLM lập chỉ mục thủ công
    "PMC": 1,   # PubMed Central toàn văn
    "PPR": 2,   # tiền ấn phẩm — CHƯA bình duyệt
    "AGR": 3, "CBA": 3, "CTX": 3, "ETH": 3, "HIR": 3, "NBK": 3, "PAT": 3,
}

# Europe PMC không bắt buộc khai danh tính, nhưng khai vẫn là phép lịch sự tối
# thiểu và giúp họ liên hệ nếu ta gây tải bất thường.
USER_AGENT = "sr-agent/0.1 (+https://github.com/Gunthqq30223132/SRagent)"

TRAN_AN_TOAN = 5000  # chốt chặn: quét quá mức này là truy vấn sai, không phải kho to


def hang_uy_tin(kho: str) -> int:
    return HANG_THEO_KHO.get((kho or "").upper(), UNKNOWN_SOURCE_TIER)


def _ngay(rec: dict[str, Any]) -> datetime | None:
    for khoa in ("firstPublicationDate", "electronicPublicationDate"):
        raw = rec.get(khoa)
        if raw:
            try:
                y, m, d = (int(x) for x in str(raw).split("-")[:3])
                return datetime(y, m, d, tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass
    nam = str(rec.get("pubYear") or "").strip()
    if nam.isdigit():
        return datetime(int(nam), 1, 1, tzinfo=timezone.utc)
    return None


def _tac_gia(rec: dict[str, Any]) -> list[str]:
    ds = (rec.get("authorList") or {}).get("author") or []
    ten = [a.get("fullName", "").strip() for a in ds if a.get("fullName")]
    if ten:
        return ten
    # authorString là chuỗi gộp 'Douketis JD, Spyropoulos AC.' — dự phòng.
    gop = (rec.get("authorString") or "").rstrip(".")
    return [t.strip() for t in gop.split(",") if t.strip()]


def _loai_bai(rec: dict[str, Any]) -> list[str]:
    return [t for t in (rec.get("pubTypeList") or {}).get("pubType") or [] if t]


def ban_ghi_thanh_document(rec: dict[str, Any]) -> Document:
    """Một bản ghi JSON của Europe PMC -> Document chuẩn của hệ thống."""
    kho = (rec.get("source") or "").upper()
    ma = str(rec.get("id") or "").strip()
    if not kho or not ma:
        raise LayoutParseError(
            f"Bản ghi Europe PMC thiếu 'source' hoặc 'id' — không định danh được: "
            f"{ {k: rec.get(k) for k in ('source', 'id', 'title')} }"
        )

    # Giữ vết mọi định danh khác để tầng chống trùng D34 nhận ra bản ghi này và
    # bản tải thẳng từ PubMed là MỘT bài, thay vì đếm thành hai.
    khac: list[str] = []
    if rec.get("pmid"):
        khac.append(f"pubmed:{rec['pmid']}")
    if rec.get("pmcid"):
        khac.append(f"pmc:{rec['pmcid']}")
    if rec.get("doi"):
        khac.append(f"doi:{rec['doi']}")

    return Document(
        uid="",
        source="europepmc",
        source_id=f"europepmc:{kho}:{ma}",
        authority_tier=hang_uy_tin(kho),
        alternate_uids=khac,
        title=(rec.get("title") or "").strip(),
        abstract=rec.get("abstractText") or None,
        authors=_tac_gia(rec),
        published_date=_ngay(rec),
        url=f"https://europepmc.org/article/{kho}/{ma}",
        status=DocStatus.FETCHED,
        evidence_level=evidence_level(_loai_bai(rec)),
    )


class EuropePMCFetcher:
    """Fetcher Europe PMC theo FetcherProtocol (search + fetch)."""

    source = "europepmc"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(
            timeout=30.0, headers={"User-Agent": USER_AGENT}
        )
        self.loai_bai: dict[str, list[str]] = {}

    def _goi(self, query: str, page_size: int, cursor: str) -> dict[str, Any]:
        resp = get_with_retry(self.client, SEARCH, params={
            "query": query,
            "format": "json",
            "resultType": "core",
            "pageSize": str(page_size),
            "cursorMark": cursor,
        })
        try:
            data = resp.json()
        except ValueError as exc:
            raise LayoutParseError(
                f"Europe PMC trả về nội dung không phải JSON.\n"
                f"  Mã HTTP: {resp.status_code}\n"
                f"  200 ký tự đầu: {resp.text[:200]!r}\n"
                f"  Lỗi phân tích: {exc}"
            ) from exc
        if "resultList" not in data:
            raise LayoutParseError(
                f"Phản hồi Europe PMC thiếu 'resultList' — không đúng dạng mong đợi.\n"
                f"  Các khoá nhận được: {sorted(data)[:12]}"
            )
        return data

    def quet_toan_bo(
        self, query: str, tran: int = TRAN_AN_TOAN, page_size: int = 1000,
    ) -> tuple[list[Document], int]:
        """Quét TOÀN BỘ kho khớp truy vấn, không phải 10 bài đầu.

        Trả về (bản ghi, tổng số kho báo có). Hai số này phải bằng nhau thì lần
        quét mới phủ 100% — và đó chính là con số Tầng 2 đo. Đây là hàm khiến
        'độ phủ 0,57%' thôi là giới hạn kỹ thuật.
        """
        docs: list[Document] = []
        cursor, tong = "*", None
        while True:
            data = self._goi(query, min(page_size, 1000), cursor)
            # CHỈ lấy hitCount ở TRANG ĐẦU. Đây là mẫu số của phép đo độ phủ —
            # con số quan trọng nhất Tầng 2 báo cáo. Để trang sau ghi đè lên nó
            # nghĩa là một trang lỗi hay một trang cuối rỗng có thể lặng lẽ kéo
            # mẫu số về 0, và độ phủ sẽ hiện ra đẹp đẽ trong khi thật ra vô nghĩa.
            if tong is None:
                tong = int(data.get("hitCount", 0))
            ket_qua = (data.get("resultList") or {}).get("result") or []
            for rec in ket_qua:
                doc = ban_ghi_thanh_document(rec)
                self.loai_bai[doc.uid] = _loai_bai(rec)
                docs.append(doc)
            cursor_moi = data.get("nextCursorMark")
            # Cursor không đổi = trang cuối. Không kiểm điều này thì vòng lặp
            # chạy mãi khi API đổi hành vi.
            if not ket_qua or not cursor_moi or cursor_moi == cursor:
                break
            cursor = cursor_moi
            if len(docs) >= tran:
                break
        return docs, (tong or 0)

    def search(self, query: str, max_results: int = 20) -> list[str]:
        docs, _ = self.quet_toan_bo(query, tran=max_results,
                                    page_size=min(max_results, 1000))
        return [d.source_id for d in docs[:max_results]]

    def fetch(self, source_ids: Iterable[str]) -> list[Document]:
        """Lấy bản ghi theo danh sách mã. Nhận cả 'pubmed:123' lẫn mã Europe PMC."""
        dieu_kien: list[str] = []
        for raw in source_ids:
            ma = str(raw).strip().rsplit(":", 1)[-1]
            if ma:
                dieu_kien.append(f"EXT_ID:{ma}")
        if not dieu_kien:
            return []
        docs, _ = self.quet_toan_bo(" OR ".join(dieu_kien), tran=len(dieu_kien) * 2)
        return docs

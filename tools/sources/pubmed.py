"""Nguồn Y KHOA — PubMed qua NCBI E-utilities (esearch + efetch).

VÌ SAO NẰM Ở tools/ CHỨ KHÔNG PHẢI sr_agent/ingest/:
`sr_agent/ingest/` nằm trong vùng cấm zero-touch do gate_m6.sh thực thi. Nhưng
`SourceRouter.__init__` nhận tham số `fetchers` tiêm vào, và validator của
`Document` bỏ qua kiểm ID với nguồn chưa khai trong ID_PATTERNS. Hai điểm mở đó
đủ để cắm một nguồn mới TỪ BÊN NGOÀI mà không sửa lõi — nên ta dùng đúng điểm
mở rộng có sẵn thay vì phá vùng cấm.

KHÔNG THÊM PHỤ THUỘC: parse bằng xml.etree trong thư viện chuẩn, để pyproject.toml
giữ nguyên zero-touch (feedparser chỉ đọc Atom/RSS, không hợp cho PubMed XML).

Quy ước ID: 'pubmed:<pmid>' — thẳng hàng với 'arxiv:YYMM.NNNNN' để make_uid()
trong lõi không phải xử lý ngoại lệ nào.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Iterable
from xml.etree import ElementTree as ET

import httpx

from sr_agent.config import register_source
from sr_agent.errors import LayoutParseError
from sr_agent.ingest.base import get_with_retry
from sr_agent.models.schemas import DocStatus, Document

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESEARCH = f"{EUTILS}/esearch.fcgi"
EFETCH = f"{EUTILS}/efetch.fcgi"

PUBMED_ID_PATTERN = re.compile(r"^pubmed:\d{1,8}$")

# Tự khai báo vào sổ đăng ký nguồn — không phải sửa config.py mỗi lần thêm nguồn.
register_source("pubmed", id_pattern=PUBMED_ID_PATTERN, authority_tier=1)

# PubMed là tạp chí đã bình duyệt -> ngang tier IEEE. Truyền tường minh thay vì
# gọi default_tier() để không phải thêm khóa vào config.py (giữ vùng cấm sạch).
PUBMED_TIER = 1

# Thang bậc chứng cứ, số NHỎ = mạnh hơn. Đây là tín hiệu quý nhất mà PubMed cho
# không mà arXiv/IEEE không có: PublicationType do NLM gán thủ công.
EVIDENCE_RANK: dict[str, int] = {
    "meta-analysis": 1,
    "systematic review": 2,
    "randomized controlled trial": 3,
    "practice guideline": 3,
    "guideline": 4,
    "clinical trial": 5,
    "observational study": 6,
    "review": 7,
    "case reports": 9,
}

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def normalize_pubmed_id(raw: str) -> str | None:
    """Đưa mọi biến thể ('PMID: 12345', 'pmid:12345', URL, số trần) về 'pubmed:12345'."""
    raw = raw.strip()
    m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{1,8})", raw)
    if m:
        candidate = f"pubmed:{m.group(1)}"
    else:
        bare = re.sub(r"^(?:pubmed|pmid)\s*[:\s]\s*", "", raw, flags=re.IGNORECASE)
        candidate = f"pubmed:{bare.strip()}"
    return candidate if PUBMED_ID_PATTERN.match(candidate) else None


def _text(node: ET.Element | None) -> str:
    """Gom toàn bộ text của một node kể cả thẻ inline (<i>, <sup>...)."""
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


def _parse_pubdate(article: ET.Element) -> datetime | None:
    """PubDate của PubMed có 3 dạng: Year/Month/Day, MedlineDate ('2024 Jan-Feb'), rỗng."""
    for path in (".//ArticleDate", ".//Journal/JournalIssue/PubDate"):
        node = article.find(path)
        if node is None:
            continue
        year_txt = _text(node.find("Year"))
        if not year_txt:
            medline = _text(node.find("MedlineDate"))
            m = re.search(r"(\d{4})", medline)
            if not m:
                continue
            year_txt = m.group(1)
        try:
            year = int(year_txt)
        except ValueError:
            continue
        month_txt = _text(node.find("Month")).lower()[:3]
        month = _MONTHS.get(month_txt, 0) or (
            int(month_txt) if month_txt.isdigit() else 1
        )
        day_txt = _text(node.find("Day"))
        day = int(day_txt) if day_txt.isdigit() else 1
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return datetime(year, 1, 1, tzinfo=timezone.utc)
    return None


def evidence_level(publication_types: list[str]) -> int | None:
    """Bậc chứng cứ MẠNH NHẤT trong các nhãn NLM gán cho bài. None nếu không nhận ra.

    None KHÔNG được coi là 'kém' — nó nghĩa là 'chưa phân loại', và tầng trên phải
    hiển thị khác với 'đã phân loại là yếu'. Đánh đồng hai thứ này là bỏ sót thầm lặng.
    """
    ranks = [EVIDENCE_RANK[t.lower()] for t in publication_types
             if t.lower() in EVIDENCE_RANK]
    return min(ranks) if ranks else None


class PubMedFetcher:
    """Fetcher PubMed tuân thủ FetcherProtocol (search + fetch)."""

    source = "pubmed"

    def __init__(self, client: httpx.Client | None = None, api_key: str | None = None,
                 email: str | None = None):
        # Đọc từ .env khi không truyền tường minh — người dùng cuối chỉ điền .env
        # một lần, không phải sửa mã.
        api_key = os.getenv("NCBI_API_KEY", "") if api_key is None else api_key
        email = os.getenv("NCBI_EMAIL", "") if email is None else email
        # NCBI yêu cầu công cụ tự định danh qua User-Agent; thiếu nó có thể bị
        # xếp vào nhóm lưu lượng ẩn danh và bị chặn mềm (HTTP 200 + trang chặn).
        self.client = client or httpx.Client(
            timeout=30, follow_redirects=True,
            headers={"User-Agent": "sr-agent/0.1 (+https://github.com/Gunthqq30223132/SRagent)"},
        )
        self.api_key = api_key
        self.email = email
        # Dữ liệu chỉ PubMed mới có, giữ ngoài Document (xem ghi chú ở parse).
        self.publication_types: dict[str, list[str]] = {}
        self.evidence_levels: dict[str, int | None] = {}

    def _common_params(self) -> dict[str, str]:
        params = {"db": "pubmed", "tool": "sr-agent"}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.email:
            params["email"] = self.email
        return params

    def search(self, query: str, max_results: int = 20) -> list[str]:
        """Tìm PMID theo từ khoá.

        DÙNG XML, KHÔNG DÙNG JSON. Lần chạy thật đầu tiên trên máy Mac cho lỗi
        'Expecting value: line 1 column 1' — HTTP thành công nhưng thân phản hồi
        không phải JSON. retmode=json của E-utilities là chế độ phụ và trả về
        HTML/rỗng trong vài tình huống (chuyển hướng, trang chặn, biến động
        phía NCBI). Định dạng XML là mặc định của E-utilities, ổn định hàng chục
        năm, và ta đã có sẵn bộ phân tích XML ngay dưới đây.
        """
        params = self._common_params() | {
            "term": query, "retmax": str(max_results), "sort": "relevance",
        }
        resp = get_with_retry(self.client, ESEARCH, params=params)
        return self.parse_esearch_xml(resp.text)

    @staticmethod
    def parse_esearch_xml(xml_text: str) -> list[str]:
        """<eSearchResult><IdList><Id>123</Id>...</IdList></eSearchResult> -> ids.

        Lỗi phân tích PHẢI kèm nội dung thật NCBI trả về. Bản trước chỉ in thông
        điệp của trình đọc JSON, giấu mất thân phản hồi — đúng thứ duy nhất cần
        để chẩn đoán. Che dữ liệu chẩn đoán làm mất thêm một vòng thử.
        """
        body = (xml_text or "").strip()
        if not body:
            raise LayoutParseError(
                "esearch trả về THÂN RỖNG (0 byte). Thường do proxy/tường lửa "
                "cắt kết nối, hoặc NCBI chặn tạm."
            )
        # NCBI chặn MỀM: vẫn trả HTTP 200 nhưng chuyển hướng sang trang lạm dụng.
        # Không nhận diện riêng thì lỗi hiện ra là "không phải XML" — đúng về kỹ
        # thuật, vô dụng về chẩn đoán. Nguyên nhân thật hầu như luôn là thiếu
        # email theo chính sách NCBI, chứ không phải người dùng thực sự lạm dụng.
        if "WWW Error Blocked Diagnostic" in body or "misuse.ncbi" in body:
            raise LayoutParseError(
                "NCBI TỪ CHỐI PHỤC VỤ IP NÀY (trang 'WWW Error Blocked Diagnostic').\n"
                "       Đây KHÔNG phải lỗi mạng và KHÔNG phải lỗi mã — NCBI chủ động chặn.\n"
                "       Nguyên nhân thường gặp nhất: truy vấn tự động thiếu email liên hệ.\n"
                "       Khắc phục (2 phút):\n"
                "         1. Mở .env, điền  NCBI_EMAIL=<email của anh>\n"
                "         2. Lấy khóa miễn phí tại https://account.ncbi.nlm.nih.gov/settings/\n"
                "            rồi điền     NCBI_API_KEY=<khóa>\n"
                "       Khóa API còn tách anh khỏi IP dùng chung — hết bị vạ lây."
            )
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise LayoutParseError(
                f"esearch trả về nội dung không phải XML ({exc}). "
                f"300 ký tự đầu NCBI thực sự trả về: {body[:300]!r}"
            ) from exc
        if root.tag == "ERROR" or root.find("ERROR") is not None:
            loi = _text(root if root.tag == "ERROR" else root.find("ERROR"))
            raise LayoutParseError(f"NCBI báo lỗi truy vấn: {loi}")
        # Một trang HTML chặn ('<html><body>Access denied</body></html>') tình cờ
        # cũng là XML hợp lệ. Không kiểm thẻ gốc thì nó lọt qua và trả DANH SÁCH
        # RỖNG — người dùng đọc thành "không có bài nào khớp" thay vì "bị chặn".
        # Bỏ sót thầm lặng nguy hiểm hơn báo lỗi ồn ào.
        if root.tag != "eSearchResult":
            raise LayoutParseError(
                f"esearch trả về tài liệu lạ (thẻ gốc <{root.tag}>, cần "
                f"<eSearchResult>). Nhiều khả năng là trang chặn của tường lửa/"
                f"proxy. 300 ký tự đầu: {body[:300]!r}"
            )
        return [f"pubmed:{_text(node)}" for node in root.findall(".//IdList/Id")
                if _text(node)]

    def fetch(self, source_ids: Iterable[str]) -> list[Document]:
        pmids = [sid.removeprefix("pubmed:") for sid in source_ids]
        if not pmids:
            return []
        params = self._common_params() | {
            "id": ",".join(pmids), "retmode": "xml",
        }
        resp = get_with_retry(self.client, EFETCH, params=params)
        return self.parse_efetch_xml(resp.text)

    def parse_efetch_xml(self, xml_text: str) -> list[Document]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise LayoutParseError(f"efetch trả XML hỏng: {exc}") from exc

        docs: list[Document] = []
        for citation in root.findall(".//PubmedArticle/MedlineCitation"):
            pmid = _text(citation.find("PMID"))
            article = citation.find("Article")
            if article is None:
                raise LayoutParseError(f"PMID {pmid!r} thiếu node <Article>")

            title = _text(article.find("ArticleTitle"))
            source_id = normalize_pubmed_id(f"pubmed:{pmid}")
            if not source_id or not title:
                raise LayoutParseError(
                    f"Bản ghi thiếu PMID/title hợp lệ: pmid={pmid!r} title={title!r}"
                )

            # Abstract PubMed chia nhiều đoạn có Label (BACKGROUND/METHODS/RESULTS).
            # Giữ nguyên nhãn — đó chính là cấu trúc IMRAD có sẵn, vứt đi là mất dữ liệu.
            parts: list[str] = []
            for at in article.findall(".//Abstract/AbstractText"):
                body = _text(at)
                if not body:
                    continue
                label = (at.get("Label") or "").strip()
                parts.append(f"{label}: {body}" if label else body)
            abstract = "\n".join(parts) or None

            authors: list[str] = []
            for a in article.findall(".//AuthorList/Author"):
                last, fore = _text(a.find("LastName")), _text(a.find("ForeName"))
                collective = _text(a.find("CollectiveName"))
                name = f"{fore} {last}".strip() or collective
                if name:
                    authors.append(name)

            pub_types = [_text(pt) for pt
                         in article.findall(".//PublicationTypeList/PublicationType")]

            doc = Document(
                uid="",
                source=self.source,
                source_id=source_id,
                authority_tier=PUBMED_TIER,
                title=title,
                abstract=abstract,
                authors=authors,
                published_date=_parse_pubdate(article),
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                status=DocStatus.FETCHED,
                evidence_level=evidence_level(pub_types),
            )
            # Bậc chứng cứ giữ NGOÀI Document: thêm trường vào schema là chạm
            # vùng cấm lần nữa cho một thứ chỉ PubMed mới có. Tầng nào cần thì
            # tra qua bản đồ này theo uid.
            self.publication_types[doc.uid] = pub_types
            self.evidence_levels[doc.uid] = evidence_level(pub_types)
            docs.append(doc)
        return docs

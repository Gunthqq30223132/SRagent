"""Nguồn Loại C — Europe PMC REST API (y văn lâm sàng).

Europe PMC là superset của PubMed/MEDLINE + PMC + preprint (PPR), trả JSON
thuần nên parse bằng stdlib — KHÔNG dependency runtime mới (Bất biến #1). Không
cần API key (khác NCBI E-utilities), nên không thêm secret vào .env.

ID chuẩn hóa: 'europepmc:<SRC>:<num>' với SRC ∈ {MED, PMC, PPR}. Prefix tường
minh là BẮT BUỘC — một PMID trần (vd '12345678') trùng quy tắc 8 số của IEEE,
nên adapter từ chối ID không mang dấu hiệu nguồn để router giữ tính tất định.

Chỉ metadata + abstract chảy qua đây; full-text OA (nếu cần về sau) vẫn phải đi
qua Outbound Interceptor khi ra cloud. Unit test dùng fixtures offline qua
parse_search_json() nên không chạm mạng.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from sr_agent.config import ID_PATTERNS
from sr_agent.errors import LayoutParseError
from sr_agent.ingest.base import get_with_retry
from sr_agent.models.schemas import DocStatus, Document, default_tier

EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

_VALID_SRC = ("MED", "PMC", "PPR")

# 'MED/12345', 'europepmc:MED:12345', 'PMC1234567', 'PPR456789'
_CANON_RE = re.compile(r"^europepmc:(MED|PMC|PPR):(\d+)$")
_SLASH_RE = re.compile(r"^(MED|PMC|PPR)/(\d+)$", re.IGNORECASE)
_PREFIX_RE = re.compile(r"^(PMC|PPR)(\d+)$", re.IGNORECASE)


def normalize_europepmc_id(raw: str) -> str | None:
    """Đưa các biến thể có DẤU HIỆU NGUỒN về 'europepmc:<SRC>:<num>'.

    Số trần (không prefix) trả None — nhập nhằng với IEEE, không đoán mò.
    """
    raw = raw.strip()
    for rx in (_CANON_RE, _SLASH_RE):
        m = rx.match(raw)
        if m:
            candidate = f"europepmc:{m.group(1).upper()}:{m.group(2)}"
            return candidate if ID_PATTERNS["europepmc"].match(candidate) else None
    m = _PREFIX_RE.match(raw)
    if m:
        candidate = f"europepmc:{m.group(1).upper()}:{m.group(2)}"
        return candidate if ID_PATTERNS["europepmc"].match(candidate) else None
    return None


def _split_id(source_id: str) -> tuple[str, str]:
    m = _CANON_RE.match(source_id)
    if not m:
        raise LayoutParseError(f"source_id Europe PMC sai khuôn: {source_id!r}")
    return m.group(1), m.group(2)


def _parse_authors(rec: dict[str, Any]) -> list[str]:
    """authorString 'Nguyen A, Tran B.' hoặc authorList.author[].fullName."""
    author_list = (rec.get("authorList") or {}).get("author")
    if isinstance(author_list, list) and author_list:
        names = [str(a.get("fullName", "")).strip() for a in author_list]
        return [n for n in names if n]
    raw = (rec.get("authorString") or "").strip().rstrip(".")
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_date(rec: dict[str, Any]) -> datetime | None:
    fpd = (rec.get("firstPublicationDate") or "").strip()
    if fpd:
        try:
            return datetime.strptime(fpd, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    year = rec.get("pubYear")
    if year:
        try:
            return datetime(int(year), 1, 1, tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None
    return None


class EuropePMCFetcher:
    source = "europepmc"

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=30, follow_redirects=True)

    def _query(self, query: str, page_size: int) -> dict[str, Any]:
        resp = get_with_retry(
            self.client,
            EPMC_SEARCH,
            params={
                "query": query,
                "format": "json",
                "resultType": "core",
                "pageSize": page_size,
            },
        )
        try:
            return resp.json()
        except ValueError as exc:
            raise LayoutParseError(f"Europe PMC trả về non-JSON: {exc}") from exc

    def search(self, query: str, max_results: int = 20) -> list[str]:
        data = self._query(query, page_size=max_results)
        return [d.source_id for d in self.parse_search_json(data)]

    def fetch(self, source_ids: Iterable[str]) -> list[Document]:
        clauses = []
        for sid in source_ids:
            src, num = _split_id(sid)
            clauses.append(f"(EXT_ID:{num} AND SRC:{src})")
        if not clauses:
            return []
        data = self._query(" OR ".join(clauses), page_size=len(clauses))
        return self.parse_search_json(data)

    def parse_search_json(self, data: dict[str, Any]) -> list[Document]:
        if not isinstance(data, dict) or "resultList" not in data:
            raise LayoutParseError("Europe PMC response thiếu key 'resultList'")
        results = (data.get("resultList") or {}).get("result")
        if not isinstance(results, list):
            raise LayoutParseError("Europe PMC 'resultList.result' không phải list")

        docs: list[Document] = []
        for rec in results:
            src = str(rec.get("source", "")).strip().upper()
            rec_id = str(rec.get("id", "")).strip()
            # Khóa cứng: chỉ nhận 3 nguồn đã đăng ký, ID số.
            if src not in _VALID_SRC or not rec_id.isdigit():
                continue
            source_id = f"europepmc:{src}:{rec_id}"
            if not ID_PATTERNS["europepmc"].match(source_id):
                continue

            title = " ".join((rec.get("title") or "").split()).rstrip(".")
            if not title:
                raise LayoutParseError(f"Record {source_id!r} thiếu title")

            # Preprint (PPR) là bằng chứng yếu hơn — hạ tier bất kể mặc định nguồn.
            tier = 2 if src == "PPR" else default_tier(self.source)

            docs.append(Document(
                uid="",
                source=self.source,
                source_id=source_id,
                authority_tier=tier,
                title=title,
                abstract=" ".join((rec.get("abstractText") or "").split()) or None,
                authors=_parse_authors(rec),
                published_date=_parse_date(rec),
                url=f"https://europepmc.org/article/{src}/{rec_id}",
                status=DocStatus.FETCHED,
            ))
        return docs

"""Nguồn Loại A — IEEE Xplore Metadata API (CS Transactions).

Document ID (article_number) là số nguyên 8 chữ số — khớp quy tắc ID tĩnh.
Cần IEEE_API_KEY (miễn phí, https://developer.ieee.org). Thiếu key thì fetcher
raise UnsupportedFormat ngay khi gọi thật; unit test dùng fixtures offline
qua parse_search_json() nên không cần key.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from sr_agent.config import ID_PATTERNS, IEEE_API_KEY
from sr_agent.errors import LayoutParseError, UnsupportedFormat
from sr_agent.ingest.base import get_with_retry
from sr_agent.models.schemas import DocStatus, Document, default_tier

IEEE_API = "https://ieeexploreapi.ieee.org/api/v1/search/articles"


class IEEEXploreFetcher:
    source = "ieee"

    def __init__(self, client: httpx.Client | None = None, api_key: str | None = None):
        self.client = client or httpx.Client(timeout=30)
        self.api_key = api_key if api_key is not None else IEEE_API_KEY

    def _query(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise UnsupportedFormat(
                "Thiếu IEEE_API_KEY trong .env — đăng ký miễn phí tại developer.ieee.org"
            )
        resp = get_with_retry(
            self.client, IEEE_API, params={"apikey": self.api_key, **params}
        )
        try:
            return resp.json()
        except ValueError as exc:
            raise LayoutParseError(f"IEEE API trả về non-JSON: {exc}") from exc

    def search(self, query: str, max_results: int = 20) -> list[str]:
        data = self._query({"querytext": query, "max_records": max_results})
        docs = self.parse_search_json(data)
        return [d.source_id for d in docs]

    def fetch(self, source_ids: Iterable[str]) -> list[Document]:
        docs: list[Document] = []
        # Metadata API tra theo article_number từng ID một
        for sid in source_ids:
            data = self._query({"article_number": sid, "max_records": 1})
            docs.extend(self.parse_search_json(data))
        return docs

    def parse_search_json(self, data: dict[str, Any]) -> list[Document]:
        if not isinstance(data, dict) or "articles" not in data:
            raise LayoutParseError("IEEE response thiếu key 'articles'")

        docs: list[Document] = []
        for art in data["articles"]:
            article_number = str(art.get("article_number", "")).strip()
            title = (art.get("title") or "").strip()
            if not title:
                raise LayoutParseError(f"Article {article_number!r} thiếu title")
            # Khóa cứng: chỉ nhận document ID đúng 8 chữ số
            if not ID_PATTERNS["ieee"].match(article_number):
                continue

            published = None
            year = art.get("publication_year")
            if year:
                published = datetime(int(year), 1, 1, tzinfo=timezone.utc)

            authors = [
                a.get("full_name", "").strip()
                for a in (art.get("authors") or {}).get("authors", [])
                if a.get("full_name")
            ]

            docs.append(Document(
                uid="",
                source=self.source,
                source_id=article_number,
                authority_tier=default_tier(self.source),
                title=title,
                abstract=(art.get("abstract") or "").strip() or None,
                authors=authors,
                published_date=published,
                url=art.get("html_url") or art.get("pdf_url"),
                status=DocStatus.FETCHED,
            ))
        return docs

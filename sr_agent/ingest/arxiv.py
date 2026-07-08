"""Nguồn Loại B — arXiv Atom API (export.arxiv.org).

ID chuẩn hóa về 'arxiv:YYMM.NNNNN' (bỏ version suffix vN) theo quy tắc tĩnh.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable

import feedparser
import httpx

from sr_agent.config import ID_PATTERNS
from sr_agent.errors import LayoutParseError
from sr_agent.ingest.base import get_with_retry
from sr_agent.models.schemas import DocStatus, Document, default_tier

ARXIV_API = "https://export.arxiv.org/api/query"

# id trong Atom: http://arxiv.org/abs/2401.12345v2 -> 2401.12345
_ATOM_ID_RE = re.compile(r"abs/(\d{4}\.\d{4,5})(v\d+)?$")


def normalize_arxiv_id(raw: str) -> str | None:
    """Đưa mọi biến thể (URL, '2401.12345v2', 'arXiv:...') về 'arxiv:YYMM.NNNNN'."""
    raw = raw.strip()
    m = _ATOM_ID_RE.search(raw)
    if m:
        candidate = f"arxiv:{m.group(1)}"
    else:
        bare = re.sub(r"^arxiv:", "", raw, flags=re.IGNORECASE)
        bare = re.sub(r"v\d+$", "", bare)
        candidate = f"arxiv:{bare}"
    return candidate if ID_PATTERNS["arxiv"].match(candidate) else None


class ArxivFetcher:
    source = "arxiv"

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=30, follow_redirects=True)

    def search(self, query: str, max_results: int = 20) -> list[str]:
        resp = get_with_retry(
            self.client,
            ARXIV_API,
            params={"search_query": f"all:{query}", "start": 0,
                    "max_results": max_results},
        )
        docs = self.parse_atom(resp.text)
        return [d.source_id for d in docs]

    def fetch(self, source_ids: Iterable[str]) -> list[Document]:
        bare_ids = [sid.removeprefix("arxiv:") for sid in source_ids]
        if not bare_ids:
            return []
        resp = get_with_retry(
            self.client,
            ARXIV_API,
            params={"id_list": ",".join(bare_ids), "max_results": len(bare_ids)},
        )
        return self.parse_atom(resp.text)

    def parse_atom(self, atom_text: str) -> list[Document]:
        feed = feedparser.parse(atom_text)
        if feed.bozo and not feed.entries:
            raise LayoutParseError(f"Atom feed rác: {feed.bozo_exception}")

        docs: list[Document] = []
        for entry in feed.entries:
            arxiv_id = normalize_arxiv_id(entry.get("id", ""))
            title = " ".join((entry.get("title") or "").split())
            if not arxiv_id or not title:
                raise LayoutParseError(
                    f"Entry thiếu id/title hợp lệ: {entry.get('id')!r}"
                )
            published = None
            if entry.get("published_parsed"):
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            docs.append(Document(
                uid="",
                source=self.source,
                source_id=arxiv_id,
                authority_tier=default_tier(self.source),
                title=title,
                abstract=" ".join((entry.get("summary") or "").split()) or None,
                authors=[a.get("name", "") for a in entry.get("authors", []) if a.get("name")],
                published_date=published,
                url=entry.get("link"),
                status=DocStatus.FETCHED,
            ))
        return docs

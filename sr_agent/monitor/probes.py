"""Probe hạ tầng — dùng chung cho doctor (con người) và heal (máy).

Một nguồn sự thật duy nhất về "sống chưa" để doctor và heal không bao giờ
kết luận ngược nhau về cùng một hạ tầng.
"""

from __future__ import annotations

import httpx

from sr_agent.parser.ollama_client import OllamaClient

# Endpoint nhẹ nhất của từng nguồn để kiểm tra ĐƯỜNG MẠNG (không phải auth):
# bất kỳ HTTP status nào trả về (kể cả 403 thiếu key) = mạng thông.
PROBE_URLS: dict[str, str] = {
    "arxiv": "https://export.arxiv.org/api/query?search_query=all:test&max_results=1",
    "ieee": "https://ieeexploreapi.ieee.org/api/v1/search/articles",
}


def probe_source(source: str, timeout: float = 3.0) -> bool:
    """True nếu đường mạng tới nguồn thông (phân biệt lỗi mạng với lỗi cấu hình)."""
    url = PROBE_URLS.get(source)
    if url is None:
        return False
    try:
        httpx.get(url, timeout=timeout, follow_redirects=True)
        return True
    except httpx.TransportError:
        return False


def probe_ollama(client: OllamaClient | None = None) -> bool:
    return (client or OllamaClient()).is_available()

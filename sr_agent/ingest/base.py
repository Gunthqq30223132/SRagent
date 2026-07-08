"""Hợp đồng chung cho mọi fetcher + tiện ích HTTP có retry/backoff.

Fetcher trả về `Document` ở trạng thái FETCHED (metadata + abstract).
Việc dedup/score/parse là của các tầng sau — fetcher chỉ lo lấy dữ liệu về
và ném đúng loại exception (Transient vs Permanent) để pipeline cô lập lỗi.
"""

from __future__ import annotations

from typing import Iterable, Protocol

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from sr_agent.config import MAX_RETRIES
from sr_agent.errors import NetworkError, RateLimited
from sr_agent.models.schemas import Document


class FetcherProtocol(Protocol):
    source: str

    def search(self, query: str, max_results: int = 20) -> list[str]:
        """Trả về danh sách source_id khớp quy tắc ID tĩnh của nguồn."""
        ...

    def fetch(self, source_ids: Iterable[str]) -> list[Document]:
        """Lấy metadata cho từng ID; lỗi layout từng bản ghi -> LayoutParseError."""
        ...


def raise_for_transient(response: httpx.Response) -> None:
    """Đổi HTTP status thành exception đúng loại để tenacity/pipeline xử lý."""
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        raise RateLimited(
            f"429 từ {response.request.url}",
            retry_after=float(retry_after) if retry_after else None,
        )
    if response.status_code >= 500:
        raise NetworkError(f"{response.status_code} từ {response.request.url}")
    response.raise_for_status()


# Backoff 2s/4s/8s/16s + jitter; chỉ retry lỗi Transient — PermanentError xuyên qua.
http_retry = retry(
    retry=retry_if_exception_type((RateLimited, NetworkError, httpx.TransportError)),
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential_jitter(initial=2, max=16),
    reraise=True,
)


@http_retry
def get_with_retry(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    try:
        response = client.get(url, **kwargs)
    except httpx.TransportError as exc:
        raise NetworkError(str(exc)) from exc
    raise_for_transient(response)
    return response

"""Exception hierarchy của SR-Agent.

Nguyên tắc cô lập lỗi: pipeline bọc try/except quanh TỪNG bản ghi.
- TransientError  -> retry với backoff; hết lượt retry thì vào DLQ (retry_eligible=1)
- PermanentError  -> không retry, vào DLQ ngay + quarantine raw payload
"""

from __future__ import annotations


class SRAgentError(Exception):
    """Gốc của mọi lỗi nghiệp vụ trong pipeline."""


class TransientError(SRAgentError):
    """Lỗi tạm thời — đáng retry (mạng, rate limit)."""


class RateLimited(TransientError):
    """HTTP 429 từ API nguồn."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class NetworkError(TransientError):
    """Timeout / connection reset / 5xx."""


class PermanentError(SRAgentError):
    """Lỗi tất định — retry vô ích, cần người xem raw payload."""


class LayoutParseError(PermanentError):
    """File tải về sai định dạng layout (XML/Atom rác, thiếu field bắt buộc)."""


class SchemaValidationError(PermanentError):
    """Dữ liệu không qua được Pydantic validation."""


class UnsupportedFormat(PermanentError):
    """ID hoặc content-type không khớp quy tắc tĩnh nào."""


class ContextOverflowError(PermanentError):
    """Văn bản vượt quá giới hạn ngữ cảnh LLM."""

    def __init__(self, message: str, token_estimate: int):
        super().__init__(message)
        self.token_estimate = token_estimate


class VacuousPassError(PermanentError):
    """Lỗi khi không có mỏ neo số (anchors_checked == 0) trong kiểm tra firewall."""



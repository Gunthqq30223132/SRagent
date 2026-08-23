"""Router mở rộng cho miền y khoa — thêm PubMed mà KHÔNG sửa lõi.

`SourceRouter.classify()` khóa cứng 2 regex trong config.ID_PATTERNS (vùng cấm).
Thay vì sửa nó, ta kế thừa: thử quy tắc PubMed trước, không khớp thì giao lại
cho lớp cha xử lý y như cũ. Lõi giữ nguyên byte-for-byte, hành vi CS không đổi.
"""

from __future__ import annotations

from sr_agent.errors import UnsupportedFormat
from sr_agent.ingest.base import FetcherProtocol
from sr_agent.ingest.router import SourceRouter

from tools.sources.pubmed import PubMedFetcher, normalize_pubmed_id


class MedicalSourceRouter(SourceRouter):
    """SourceRouter + PubMed. Dùng cho chủ đề y khoa; CS vẫn dùng bản gốc."""

    def __init__(self, fetchers: dict[str, FetcherProtocol] | None = None,
                 pubmed_api_key: str = ""):
        super().__init__(fetchers)
        self.fetchers.setdefault("pubmed", PubMedFetcher(api_key=pubmed_api_key))

    def classify(self, raw_id: str) -> tuple[str, str]:
        """PubMed trước, rồi mới tới quy tắc gốc.

        Thứ tự này an toàn vì quy tắc PubMed đòi tiền tố tường minh
        ('pubmed:' / 'pmid:' / URL) — một ID IEEE 8 số trần KHÔNG thể bị nhận
        nhầm thành PMID.
        """
        raw_id = raw_id.strip()
        if raw_id.lower().startswith(("pubmed:", "pmid:")) or "pubmed.ncbi" in raw_id:
            normalized = normalize_pubmed_id(raw_id)
            if normalized:
                return "pubmed", normalized
            raise UnsupportedFormat(
                f"ID {raw_id!r} trông như PubMed nhưng không khớp 'pubmed:<pmid>'"
            )
        return super().classify(raw_id)

"""Multi-source Router — registry pattern tối giản cho các nguồn khóa cứng.

Phân loại một ID thô bằng các regex tĩnh trong config.ID_PATTERNS; ID không
khớp nguồn nào -> UnsupportedFormat (vào DLQ, không đoán mò).
"""

from __future__ import annotations

from sr_agent.config import ID_PATTERNS
from sr_agent.errors import UnsupportedFormat
from sr_agent.ingest.arxiv import ArxivFetcher, normalize_arxiv_id
from sr_agent.ingest.base import FetcherProtocol
from sr_agent.ingest.europepmc import EuropePMCFetcher, normalize_europepmc_id
from sr_agent.ingest.ieee import IEEEXploreFetcher


class SourceRouter:
    def __init__(self, fetchers: dict[str, FetcherProtocol] | None = None):
        self.fetchers: dict[str, FetcherProtocol] = fetchers or {
            "ieee": IEEEXploreFetcher(),
            "arxiv": ArxivFetcher(),
            "europepmc": EuropePMCFetcher(),
        }

    def classify(self, raw_id: str) -> tuple[str, str]:
        """(source, source_id chuẩn hóa) cho một ID thô. Tất định, không fallback.

        Europe PMC được thử TRƯỚC ieee: ID EPMC luôn mang prefix nguồn tường minh
        ('europepmc:'/'MED/'/'PMC…'), nên không nuốt nhầm PMID số trần của ieee.
        """
        raw_id = raw_id.strip()
        epmc = normalize_europepmc_id(raw_id)
        if epmc:
            return "europepmc", epmc
        if ID_PATTERNS["ieee"].match(raw_id):
            return "ieee", raw_id
        normalized = normalize_arxiv_id(raw_id)
        if normalized:
            return "arxiv", normalized
        raise UnsupportedFormat(
            f"ID {raw_id!r} không khớp quy tắc tĩnh nào "
            f"(ieee 8 số / arxiv:YYMM.NNNNN / europepmc:<SRC>:<num>)"
        )

    def fetcher_for(self, source: str) -> FetcherProtocol:
        if source not in self.fetchers:
            raise UnsupportedFormat(f"Nguồn {source!r} chưa được khóa cứng trong M0-M2")
        return self.fetchers[source]

"""Snowballing có kiểm soát qua Semantic Scholar Graph API (M8 Result A, D33 §3).

Kỹ thuật SR chuẩn: lần theo trích dẫn NGƯỢC (references) và XUÔI (citations) từ tập
seed đã include. Mọi trần là TẤT ĐỊNH — chạm bất kỳ trần nào ⇒ dừng kèm stopped_reason,
không tồn tại vòng thu thập vô hạn. Kết quả là RefRecord thô: vẫn phải qua dedup +
rubric gate + screening như mọi bản ghi khác (snowball KHÔNG phải cửa sau vào staging).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import httpx
from pydantic import BaseModel, Field

from tools.evidence.schemas import RefRecord
from tools.guard.outbound import assert_sanitized

S2_BASE = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "externalIds,title,abstract,year,venue,authors"


class SnowballConfig(BaseModel):
    max_depth: int = 1                 # số vòng BFS tối đa
    max_refs_per_paper: int = 50       # trần mỗi node
    max_total: int = 200               # trần tổng record mới
    max_api_calls: int = 100           # trần lời gọi API
    min_new_unique_rate: float = 0.1   # luật bão hòa: vòng có tỉ lệ mới < ngưỡng ⇒ dừng
    directions: list[Literal["backward", "forward"]] = Field(
        default_factory=lambda: ["backward", "forward"]
    )


class SnowballResult(BaseModel):
    found: list[RefRecord]
    stopped_reason: str                # "exhausted" | "max_total" | "max_api_calls" | "saturated"
    api_calls: int
    rounds_completed: int


def _to_record(item: dict) -> RefRecord | None:
    paper = item.get("citedPaper") or item.get("citingPaper") or item
    title = (paper.get("title") or "").strip()
    if not title:
        return None
    ext = paper.get("externalIds") or {}
    ids: dict[str, str] = {}
    if ext.get("DOI"):
        ids["doi"] = str(ext["DOI"])
    if ext.get("PubMed"):
        ids["pmid"] = str(ext["PubMed"])
    if ext.get("ArXiv"):
        ids["arxiv"] = f"arxiv:{ext['ArXiv']}"
    if paper.get("paperId"):
        ids["s2"] = paper["paperId"]
    return RefRecord(
        source_db="s2",
        external_ids=ids,
        title=title,
        authors=[a.get("name", "") for a in (paper.get("authors") or []) if a.get("name")],
        year=paper.get("year"),
        venue=paper.get("venue") or None,
        abstract=paper.get("abstract"),
        provenance=f"s2:{paper.get('paperId', '?')}",
    )


def snowball(
    seed_ids: list[str],
    config: SnowballConfig | None = None,
    client: httpx.Client | None = None,
) -> SnowballResult:
    """BFS chặn trần từ seed (DOI:..., PMID:..., hoặc S2 paperId — theo cú pháp S2 API).

    Lỗi HTTP một node ⇒ bỏ node đó, đi tiếp (cô lập lỗi từng bản ghi — nguyên tắc M1);
    KHÔNG retry vô hạn, KHÔNG raise giữa batch.
    """
    cfg = config or SnowballConfig()
    http = client or httpx.Client(timeout=30.0)
    endpoint_of = {"backward": "references", "forward": "citations"}

    seen: set[str] = set()
    found: list[RefRecord] = []
    api_calls = 0
    frontier = list(dict.fromkeys(seed_ids))
    reason = "exhausted"
    rounds = 0

    for depth in range(cfg.max_depth):
        next_frontier: list[str] = []
        new_this_round = 0
        fetched_this_round = 0
        for node in frontier:
            for direction in cfg.directions:
                if api_calls >= cfg.max_api_calls:
                    return SnowballResult(found=found, stopped_reason="max_api_calls",
                                          api_calls=api_calls, rounds_completed=rounds)
                url = (
                    f"{S2_BASE}/paper/{node}/{endpoint_of[direction]}"
                    f"?fields={_FIELDS}&limit={cfg.max_refs_per_paper}"
                )
                assert_sanitized(url)                     # chốt outbound trước khi rời máy
                api_calls += 1
                try:
                    resp = http.get(url)
                    resp.raise_for_status()
                except httpx.HTTPError:
                    continue                              # cô lập lỗi node, đi tiếp
                for item in (resp.json().get("data") or [])[: cfg.max_refs_per_paper]:
                    rec = _to_record(item)
                    if rec is None:
                        continue
                    fetched_this_round += 1
                    uid = rec.canonical_uid()
                    if uid in seen:
                        continue
                    seen.add(uid)
                    found.append(rec)
                    new_this_round += 1
                    if rec.external_ids.get("s2"):
                        next_frontier.append(rec.external_ids["s2"])
                    if len(found) >= cfg.max_total:
                        return SnowballResult(found=found, stopped_reason="max_total",
                                              api_calls=api_calls, rounds_completed=rounds)
        rounds += 1
        # Luật bão hòa tất định: vòng này gần như không ra gì mới ⇒ dừng sớm.
        if fetched_this_round and new_this_round / fetched_this_round < cfg.min_new_unique_rate:
            reason = "saturated"
            break
        if not next_frontier:
            break
        frontier = next_frontier

    return SnowballResult(found=found, stopped_reason=reason,
                          api_calls=api_calls, rounds_completed=rounds)

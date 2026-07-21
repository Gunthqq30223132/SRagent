"""Gỡ trùng đa nguồn thư mục (M8 Result A) — 100% local, không LLM, không cloud.

Ba tầng kế thừa triết lý D34 (sr_agent/dedup/d34.py — KHÔNG sửa, chỉ mượn triết lý):
  1. Exact external-ID: hai record chia sẻ bất kỳ (key, value) id nào ⇒ trùng chắc chắn
     (union-find — bắc cầu qua nhiều nguồn: PubMed có pmid+doi, Embase chỉ doi...).
  2. Fuzzy title: rapidfuzz ratio (dep sẵn có), cutoff 93 đồng bộ FUZZY_TITLE_THRESHOLD.
  3. Authority tier: giữ bản ghi từ nguồn uy tín hơn (tier nhỏ hơn), merge external_ids.

Kèm harness đo F1 (benchmark_f1) — tiêu chí "F1 >= 99.5% trên 10k bản ghi" phải được
ĐO trên máy thật và dán số, không tự khai (D33 §2).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from rapidfuzz import fuzz, process

from tools.evidence.schemas import DedupReport, RefRecord

FUZZY_TITLE_THRESHOLD = 93.0

# Tier nguồn (nhỏ = uy tín cao) — khai báo được, không hard-code trong logic.
DEFAULT_SOURCE_TIERS: dict[str, int] = {
    "pubmed": 1, "embase": 1, "ieee": 1,
    "europepmc": 2, "arxiv": 2,
    "s2": 3, "unknown": 9,
}


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _pick_winner(group: list[int], records: list[RefRecord], tiers: dict[str, int]) -> int:
    """Chọn đại diện nhóm trùng: tier nhỏ nhất; hòa thì index nhỏ nhất (tất định)."""
    return min(group, key=lambda i: (tiers.get(records[i].source_db, 9), i))


def dedup_records(
    records: list[RefRecord],
    *,
    threshold: float = FUZZY_TITLE_THRESHOLD,
    source_tiers: dict[str, int] | None = None,
) -> DedupReport:
    tiers = source_tiers or DEFAULT_SOURCE_TIERS
    n = len(records)
    uf = _UnionFind(n)

    # --- Tầng 1: exact external-ID (bắc cầu qua union-find) ---
    id_owner: dict[tuple[str, str], int] = {}
    for i, rec in enumerate(records):
        for key, val in rec.external_ids.items():
            v = val.strip().casefold()
            if not v:
                continue
            token = (key, v)
            if token in id_owner:
                uf.union(id_owner[token], i)
            else:
                id_owner[token] = i

    # --- Tầng 2: fuzzy title — chỉ so giữa các ĐẠI DIỆN nhóm hiện tại (blocking rẻ) ---
    roots = sorted({uf.find(i) for i in range(n)})
    root_titles = {r: records[r].title_normalized() for r in roots}
    seen_titles: dict[str, int] = {}
    for r in roots:
        t = root_titles[r]
        if not t:
            continue
        if seen_titles:
            match = process.extractOne(
                t, seen_titles.keys(), scorer=fuzz.ratio, score_cutoff=threshold,
            )
            if match is not None:
                uf.union(seen_titles[match[0]], r)
                continue
        seen_titles[t] = r

    # --- Tầng 3: chọn winner theo tier + merge external_ids của cả nhóm ---
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    unique: list[RefRecord] = []
    dup_log: list[tuple[str, str, str]] = []
    for _, members in sorted(groups.items()):
        w = _pick_winner(members, records, tiers)
        winner = records[w].model_copy(deep=True)
        for i in members:
            if i == w:
                continue
            loser = records[i]
            for k, v in loser.external_ids.items():
                winner.external_ids.setdefault(k, v)      # merge id, không ghi đè
            layer = (
                "exact_id"
                if set(map(lambda kv: (kv[0], kv[1].casefold()), loser.external_ids.items()))
                & set(map(lambda kv: (kv[0], kv[1].casefold()), records[w].external_ids.items()))
                else "fuzzy_title"
            )
            dup_log.append((loser.canonical_uid(), winner.canonical_uid(), layer))
        unique.append(winner)

    return DedupReport(
        unique=unique, duplicates=dup_log, n_input=n, n_unique=len(unique),
    )


# --- Benchmark harness (D33 §2: số phải đo, không tự khai) ---------------------------

def benchmark_f1(
    records: list[RefRecord],
    gold_duplicate_pairs: set[frozenset[int]],
    **dedup_kwargs,
) -> dict[str, float]:
    """Đo precision/recall/F1 của phát hiện CẶP trùng so với nhãn vàng (index-based).

    gold_duplicate_pairs: {frozenset({i, j}), ...} — mọi cặp index thuộc cùng một bài thật.
    Trả về dict tất định để dán vào báo cáo bench (M8.2 chạy trên máy thật với 10k+).
    """
    report = dedup_records(records, **dedup_kwargs)
    # Tái dựng cặp dự đoán từ nhóm: cần chạy lại union-find → suy từ dup_log qua uid
    uid_to_idx: dict[str, list[int]] = {}
    for i, r in enumerate(records):
        uid_to_idx.setdefault(r.canonical_uid(), []).append(i)

    predicted: set[frozenset[int]] = set()
    # nhóm theo winner uid
    group_map: dict[str, set[str]] = {}
    for loser, winner, _ in report.duplicates:
        group_map.setdefault(winner, {winner}).add(loser)
    for members in group_map.values():
        idxs = sorted(i for uid in members for i in uid_to_idx.get(uid, []))
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                predicted.add(frozenset({idxs[a], idxs[b]}))

    tp = len(predicted & gold_duplicate_pairs)
    fp = len(predicted - gold_duplicate_pairs)
    fn = len(gold_duplicate_pairs - predicted)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 6), "recall": round(recall, 6),
        "f1": round(f1, 6), "tp": tp, "fp": fp, "fn": fn,
        "n_input": report.n_input, "n_unique": report.n_unique,
    }

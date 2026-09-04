"""D34 — bộ lọc loại trùng tất định 3 tầng, chạy TRƯỚC mọi xử lý LLM.

Tầng 1: Exact match ID       — so uid chuẩn hóa với index staging, O(1).
Tầng 2: Fuzzy title match    — rapidfuzz.fuzz.ratio (Levenshtein-based) trên
                               title_normalized, score_cutoff = FUZZY_TITLE_THRESHOLD.
Tầng 3: Cross-source priority— trùng chéo nguồn thì giữ bản authority_tier nhỏ
                               (IEEE 1 > arXiv 2), merge metadata thay vì vứt.

Toàn bộ là hard rules Python thuần — cùng input luôn cho cùng output.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rapidfuzz import fuzz, process

from sr_agent.config import FUZZY_TITLE_THRESHOLD
from sr_agent.models.schemas import Document


class DedupAction(str, Enum):
    NEW = "new"                        # không trùng — cho đi tiếp
    DUPLICATE_ID = "duplicate_id"      # tầng 1: uid đã tồn tại — bỏ qua
    DUPLICATE_FUZZY = "duplicate_fuzzy"  # tầng 2+3: trùng mờ, bản cũ uy tín hơn — bỏ qua
    SUPERSEDES = "supersedes"          # tầng 3: bản mới uy tín hơn — thay thế bản cũ


@dataclass(frozen=True)
class DedupDecision:
    action: DedupAction
    matched_uid: str | None = None
    score: float = 0.0


def decide(
    candidate: Document,
    existing_uids: set[str],
    titles_index: dict[str, str],
    tier_lookup: dict[str, int],
    threshold: float = FUZZY_TITLE_THRESHOLD,
) -> DedupDecision:
    """Quyết định số phận một bản ghi mới so với staging hiện có.

    Args:
        candidate:     bản ghi vừa fetch (đã chuẩn hóa uid/title_normalized).
        existing_uids: toàn bộ uid đang có trong staging (tầng 1).
        titles_index:  {title_normalized: uid} của bản ghi còn sống (tầng 2).
        tier_lookup:   {uid: authority_tier} để phân xử tầng 3.
    """
    # --- Tầng 1: Exact match ID ---
    if candidate.uid in existing_uids:
        return DedupDecision(DedupAction.DUPLICATE_ID, candidate.uid, 100.0)

    # Tầng 1 (tiếp): định danh KHÁC của cùng một bài. Europe PMC bơm sẵn
    # `pubmed:…`/`doi:…` vào alternate_uids đúng để chỗ này nhận ra bản tải từ
    # Europe PMC và bản tải thẳng từ PubMed là MỘT bài. Không so ở đây thì cả hai
    # rơi xuống tầng 2 (so tiêu đề mờ): tiêu đề giống thì bản thứ hai bị VỨT, tiêu
    # đề lệch quá ngưỡng thì lọt cả hai và được đếm thành HAI nguồn độc lập —
    # hai chiều sai ngược nhau, không chiều nào có tín hiệu.
    # Duyệt theo thứ tự list (không phải set) để cùng input luôn cho cùng output.
    for uid_khac in candidate.alternate_uids:
        if uid_khac in existing_uids:
            return DedupDecision(DedupAction.DUPLICATE_ID, uid_khac, 100.0)

    # --- Tầng 2: Fuzzy title (Levenshtein ratio) ---
    if not titles_index:
        return DedupDecision(DedupAction.NEW)
    match = process.extractOne(
        candidate.title_normalized,
        titles_index.keys(),
        scorer=fuzz.ratio,
        score_cutoff=threshold,
    )
    if match is None:
        return DedupDecision(DedupAction.NEW)
    matched_title, score, _ = match
    matched_uid = titles_index[matched_title]

    # --- Tầng 3: Cross-Source Prioritization (tier nhỏ = uy tín cao) ---
    existing_tier = tier_lookup.get(matched_uid, 99)
    if candidate.authority_tier < existing_tier:
        return DedupDecision(DedupAction.SUPERSEDES, matched_uid, score)
    return DedupDecision(DedupAction.DUPLICATE_FUZZY, matched_uid, score)


def merge_superseded(winner: Document, loser: Document) -> Document:
    """Bản uy tín cao thắng nhưng không vứt vết: giữ alternate_uids + bù metadata."""
    if loser.uid not in winner.alternate_uids:
        winner.alternate_uids = [*winner.alternate_uids, *loser.alternate_uids, loser.uid]
    if not winner.abstract and loser.abstract:
        winner.abstract = loser.abstract
    if not winner.authors and loser.authors:
        winner.authors = loser.authors
    if not winner.full_text and loser.full_text:
        winner.full_text = loser.full_text
    return winner

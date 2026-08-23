"""Cấu hình khóa cứng của SR-Agent (chặng M0-M2).

Mọi hằng số vận hành nằm ở đây; các module khác KHÔNG tự định nghĩa
threshold/regex riêng để bảo đảm tính tất định toàn pipeline.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Sổ đăng ký nguồn (MỞ, không còn khóa cứng 2 nguồn) ----------------------
# LỊCH SỬ: bản M0-M2 khóa cứng đúng 2 nguồn CS (IEEE + arXiv) để giữ staging
# đồng nhất tuyệt đối trong lúc dựng pipeline. Ràng buộc đó đã hoàn thành vai
# trò và bị GỠ ngày 2026-08-23 theo quyết định của chủ dự án.
#
# TẦM NHÌN ĐẰNG SAU: SR-Agent là bộ máy sinh chứng cứ, KHÔNG phải công cụ y
# khoa. Cùng một lõi, đổi nguồn tham khảo là có một hệ tri thức hệ thống cho
# bất kỳ lĩnh vực nào. Vì vậy nguồn phải là DỮ LIỆU ĐĂNG KÝ ĐƯỢC, không phải
# hằng số biên dịch.
#
# HỢP ĐỒNG MỚI:
# - Mọi chuỗi source đều được chấp nhận (không còn danh sách trắng đóng).
# - Nguồn ĐÃ đăng ký: được kiểm quy tắc ID nghiêm ngặt + dùng tier khai báo.
# - Nguồn CHƯA đăng ký: vẫn chạy được, nhưng bỏ qua kiểm ID và nhận
#   UNKNOWN_SOURCE_TIER (hạng thấp nhất). Chưa thẩm định thì không được hưởng
#   uy tín — mặc định thận trọng, không phải mặc định tin tưởng.

ID_PATTERNS: dict[str, re.Pattern[str]] = {
    "ieee": re.compile(r"^\d{8}$"),
    "arxiv": re.compile(r"^arxiv:\d{4}\.\d{4,5}$"),
}

# Authority tier: số nhỏ = uy tín cao. Dùng cho tầng 3 của D34.
AUTHORITY_TIERS: dict[str, int] = {
    "ieee": 1,   # peer-reviewed transactions/journals
    "arxiv": 2,  # preprint
}

# Tier gán cho nguồn chưa đăng ký. Cố tình đặt thấp: một nguồn chưa ai thẩm
# định không được phép thắng một tạp chí bình duyệt ở bước chống trùng.
UNKNOWN_SOURCE_TIER = 5


def register_source(
    name: str,
    *,
    id_pattern: str | re.Pattern[str] | None = None,
    authority_tier: int = UNKNOWN_SOURCE_TIER,
    overwrite: bool = False,
) -> None:
    """Đăng ký một nguồn tài liệu mới lúc chạy.

    Gọi ở module định nghĩa fetcher (xem tools/sources/pubmed.py) để nguồn tự
    khai báo quy tắc của mình — không phải sửa tệp cấu hình mỗi lần thêm nguồn.

    overwrite=False (mặc định) để hai nguồn không âm thầm giẫm lên quy tắc ID
    của nhau: đăng ký trùng tên với quy tắc khác là lỗi lập trình, phải nổ ra
    lúc nạp module chứ không phải lúc dữ liệu đã vào kho.
    """
    if not name or not name.strip():
        raise ValueError("Tên nguồn không được rỗng")
    name = name.strip().lower()
    if not overwrite and name in AUTHORITY_TIERS:
        if AUTHORITY_TIERS[name] != authority_tier:
            raise ValueError(
                f"Nguồn {name!r} đã đăng ký với tier {AUTHORITY_TIERS[name]}, "
                f"nay lại đăng ký tier {authority_tier}. Dùng overwrite=True nếu cố ý."
            )
        return
    AUTHORITY_TIERS[name] = int(authority_tier)
    if id_pattern is not None:
        ID_PATTERNS[name] = (
            id_pattern if isinstance(id_pattern, re.Pattern)
            else re.compile(id_pattern)
        )


def registered_sources() -> list[str]:
    """Danh sách nguồn đã đăng ký, để CLI/UI hiển thị mà không phải đoán."""
    return sorted(AUTHORITY_TIERS)

# --- Hàng đợi duyệt thủ công ------------------------------------------------
WIP_LIMIT = 5          # tài liệu/ngày hiển thị ở QC UI, xếp theo rubric giảm dần
TTL_HOURS = 72         # bản ghi staging chưa Approve/Reject quá 72h -> auto-purge

# --- Dedup D34 ---------------------------------------------------------------
FUZZY_TITLE_THRESHOLD = 93.0   # rapidfuzz ratio (0-100), Levenshtein-based

# --- Rubric ------------------------------------------------------------------
RUBRIC_PASS_THRESHOLD = 60.0   # dưới ngưỡng: loại trước khi tốn LLM parse

# --- Retry / rate limit -------------------------------------------------------
MAX_RETRIES = 4                 # backoff 2s, 4s, 8s, 16s (exponential + jitter)
CIRCUIT_BREAKER_FAILURES = 3    # N lỗi transient liên tiếp -> skip nguồn trong batch

IEEE_API_KEY = os.getenv("IEEE_API_KEY", "")

# --- Hạ tầng local ------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("SR_AGENT_DB", ROOT_DIR / "staging" / "sr_agent.db"))
QUARANTINE_DIR = DB_PATH.parent / "quarantine"

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# Trần model 7B-8B cho Macbook Air M4 16GB. Mặc định qwen2.5 vì bám JSON schema
# tốt nhất phân khúc; gemma3:4b là profile nhẹ/nhanh (xem .env.example).
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_PARENT_PAGE_ID = os.getenv("NOTION_PARENT_PAGE_ID", "")

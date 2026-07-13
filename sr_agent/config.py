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

# --- Định danh nguồn & quy tắc ID tĩnh -------------------------------------
# Nguồn A: IEEE Xplore (CS Transactions) — document ID 8 chữ số.
# Nguồn B: arXiv — 'arxiv:YYMM.NNNNN'.
# Nguồn C: Europe PMC — y văn peer-review + preprint; ID chuẩn hóa
# 'europepmc:<SRC>:<num>' với SRC ∈ {MED (MEDLINE/PubMed), PMC, PPR (preprint)}.
# Prefix tường minh bắt buộc để KHÔNG nhập nhằng với ieee (8 số trần). Hoãn mọi
# nguồn trung gian khác để giữ staging đồng nhất tuyệt đối.
ID_PATTERNS: dict[str, re.Pattern[str]] = {
    "ieee": re.compile(r"^\d{8}$"),
    "arxiv": re.compile(r"^arxiv:\d{4}\.\d{4,5}$"),
    "europepmc": re.compile(r"^europepmc:(MED|PMC|PPR):\d+$"),
}

# Authority tier: số nhỏ = uy tín cao. Dùng cho tầng 3 của D34.
# Europe PMC trộn MEDLINE/PMC (peer-review, tier 1) và preprint PPR (tier 2);
# adapter override xuống 2 cho PPR ngay lúc parse — mặc định ở đây là 1.
AUTHORITY_TIERS: dict[str, int] = {
    "ieee": 1,        # peer-reviewed transactions/journals
    "arxiv": 2,       # preprint
    "europepmc": 1,   # MEDLINE/PMC peer-review (PPR preprint bị hạ xuống 2 khi parse)
}

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

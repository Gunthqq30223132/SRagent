"""Numeric Firewall V24 — tường lửa tất định cho đầu ra LLM (local lẫn cloud).

TẠI SAO: tầng tổng hợp Layer C (Gemini/NotebookLM/Ollama) tạo văn bản trôi chảy nhưng
có thể bịa hằng số kỹ thuật — độ phức tạp thuật toán, cổng mạng, thông số phần cứng,
tỷ lệ phần trăm. Với tri thức khoa học, sai MỘT ký tự số là sai hoàn toàn (O(n log n)
≠ O(n²); 99.9% ≠ 99.8%). Firewall này chặn đầu ra LLM, bóc mọi "mỏ neo số"
(NumericAnchor) và đối chiếu NGUYÊN VĂN với kho nguồn tất định (Layer A).

HỢP ĐỒNG CỨNG (V24):
- So khớp substring byte-exact trên phần chữ số sau chuẩn hóa NHẸ (chỉ whitespace,
  dấu nháy, dấu gạch). KHÔNG casefold chữ số, KHÔNG fuzzy match, CẤM cosine
  similarity — tương đồng ngữ nghĩa không phải là bằng chứng cho hằng số.
- Fail-closed: một anchor không khớp ⇒ toàn bộ đầu ra bị từ chối (passed=False).
- strict=True (mặc định): anchor không tìm thấy trong bất kỳ nguồn nào cũng là
  vi phạm. strict=False: hạ xuống warning (dùng cho văn bản tổng quan không trích số
  từ nguồn cụ thể) — nhưng mismatch thì không bao giờ được tha.

Module TỰ CHỨA (không import từ tools/screen_run.py để không phụ thuộc thứ tự merge
nhánh M6). TODO sau khi PR #2 merge: hợp nhất _normalize với verify_quote/normalize_text.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pydantic import BaseModel

AnchorKind = Literal[
    "complexity", "ip", "port", "percentage", "unit", "version", "number_series"
]

# Thứ tự có chủ đích: pattern đặc thù trước (ip trước port/version để span dài thắng).
_ANCHOR_PATTERNS: list[tuple[AnchorKind, re.Pattern[str]]] = [
    ("complexity", re.compile(r"[OoΘΩ]\([^()]{1,40}\)")),
    ("ip", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?\b")),
    ("version", re.compile(r"\bv\d+\.\d+(?:\.\d+)?\b|\b\d+\.\d+\.\d+\b")),
    ("percentage", re.compile(r"\b\d+(?:\.\d+)?\s?%")),
    (
        "unit",
        re.compile(
            r"\b\d+(?:[.,]\d+)?\s?(?:ms|ns|µs|us|GHz|MHz|kHz|Hz|GB|MB|KB|TB|GiB|MiB|"
            r"Gbps|Mbps|Kbps|FLOPS|TFLOPS|W|kW|B|tokens?|params?)\b"
        ),
    ),
    ("port", re.compile(r"(?:port|cổng)\s+(\d{2,5})\b", re.IGNORECASE)),
]


class NumericAnchor(BaseModel):
    kind: AnchorKind
    raw: str                 # chuỗi bề mặt nguyên văn trong đầu ra LLM
    span: tuple[int, int]    # vị trí trong đầu ra (phục vụ hiển thị/审 audit)


class Violation(BaseModel):
    anchor: NumericAnchor
    reason: str


class FirewallVerdict(BaseModel):
    passed: bool
    anchors_checked: int
    violations: list[Violation] = []
    warnings: list[Violation] = []   # chỉ dùng ở strict=False cho anchor vắng nguồn


def _normalize(text: str) -> str:
    """Chuẩn hóa NHẸ — đủ để vượt khác biệt trình bày, không đủ để che sai số.

    Chỉ: gộp whitespace, thống nhất nháy cong/thẳng và gạch dài/ngắn.
    Tuyệt đối không đụng vào chữ số, không casefold ký tự trong biểu thức số.
    """
    for ch in "'‘’":
        text = text.replace(ch, "'")
    for ch in '"“”':
        text = text.replace(ch, '"')
    for ch in "–—":
        text = text.replace(ch, "-")
    return re.sub(r"\s+", " ", text).strip()


def extract_anchors(text: str) -> list[NumericAnchor]:
    """Bóc mọi mỏ neo số; span chồng lấn thì giữ match dài hơn (IP thắng port...)."""
    found: list[NumericAnchor] = []
    taken: list[tuple[int, int]] = []
    for kind, pat in _ANCHOR_PATTERNS:
        for m in pat.finditer(text):
            span = m.span()
            if any(span[0] < t
                   and span[1] > f for f, t in taken):  # chồng lấn match đã nhận
                continue
            raw = m.group(1) if (kind == "port" and m.groups()) else m.group(0)
            found.append(NumericAnchor(kind=kind, raw=raw, span=span))
            taken.append(span)
    found.sort(key=lambda a: a.span)
    return found


def check_output(
    llm_output: str,
    source_texts: list[str],
    *,
    strict: bool = True,
) -> FirewallVerdict:
    """Đối chiếu từng anchor trong đầu ra LLM với kho nguồn Layer A.

    Anchor "khớp" ⇔ dạng chuẩn hóa của nó là substring nguyên văn của ít nhất
    một nguồn đã chuẩn hóa. Không có khái niệm "gần đúng".
    """
    anchors = extract_anchors(llm_output)
    norm_sources = [_normalize(s) for s in source_texts if s]

    violations: list[Violation] = []
    warnings: list[Violation] = []
    for anchor in anchors:
        needle = _normalize(anchor.raw)
        if any(needle in src for src in norm_sources):
            continue
        v = Violation(
            anchor=anchor,
            reason=(
                f"'{anchor.raw}' ({anchor.kind}) không xuất hiện nguyên văn "
                f"trong bất kỳ nguồn nào — từ chối theo nguyên tắc fail-closed"
            ),
        )
        if strict:
            violations.append(v)
        else:
            warnings.append(v)

    return FirewallVerdict(
        passed=not violations,
        anchors_checked=len(anchors),
        violations=violations,
        warnings=warnings,
    )

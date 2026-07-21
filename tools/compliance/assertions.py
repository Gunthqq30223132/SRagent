"""Agent-V — bóc prose LLM thành assertion tuples (D32 §2.4).

Code TẤT ĐỊNH (regex + parser), KHÔNG phải LLM chấm LLM — tự chấm là lỗ hổng
self-attestation đã bịt từ M6/G3. Nền tảng: `extract_anchors` của Numeric Firewall V24
được IMPORT NGUYÊN TRẠNG (`tools/guard/firewall.py` không bị sửa một dòng — tiêu chí
nghiệm thu riêng của D32.3); mọi mở rộng D32 (package spec, key=value, citation token)
nằm trọn trong module này.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.compliance.schemas import AssertionTuple
from tools.guard.firewall import extract_anchors

# Citation token: [<doc_id>#<chunk>] (node KB, ví dụ [rfc9110#042-3fa9c1d2])
# hoặc [layer_a:<formula_id>] (số liệu Layer A, ví dụ [layer_a:quorum.v1]).
CITATION_RE = re.compile(r"\[(layer_a:[\w.\-]+|[\w.\-]+#[\w\-]+)\]")

# package spec: nginx==1.19.0 / libssl>=3.0 / tool@2.4 — op dài trước op ngắn.
_PKG_SPEC_RE = re.compile(
    r"\b([A-Za-z][\w\-]*(?:\.[\w\-]+)*)\s*(==|>=|<=|!=|@)\s*(\d[\w.\-]*)"
)

# cặp cấu hình key=value (một dấu '=' — không nuốt '==' của package spec).
_KEY_VALUE_RE = re.compile(r"\b([A-Za-z_][\w.]*)\s?=(?!=)\s?([\w.:/\-]+)")


def split_sentences(prose: str) -> list[str]:
    """Tách câu tất định: sau . ! ? có whitespace, hoặc xuống dòng.

    '(?<=[.!?])\\s+' không cắt '3.1' trong version (không có khoảng trắng sau dấu chấm).
    """
    parts = re.split(r"(?<=[.!?])\s+|\n+", prose)
    return [p.strip() for p in parts if p.strip()]


def extract_citations(text: str) -> list[str]:
    """Mọi citation token trong text, theo thứ tự xuất hiện."""
    return [m.group(1) for m in CITATION_RE.finditer(text)]


def _strip_citations(text: str) -> str:
    """Bỏ token citation trước khi bóc assertion — citation là metadata, không phải khẳng định."""
    return CITATION_RE.sub(" ", text)


def extract_assertions(prose: str) -> list[AssertionTuple]:
    """prose → list[AssertionTuple]; constraint_source = citation ĐẦU TIÊN trong cùng câu.

    Câu không có citation ⇒ constraint_source="" — NE4 (reconcile.py) sẽ xử phạt nếu
    câu đó là chỉ thị actionable. Agent-V chỉ bóc, không phán xử.
    """
    tuples: list[AssertionTuple] = []
    for sentence in split_sentences(prose):
        citations = extract_citations(sentence)
        source = citations[0] if citations else ""
        body = _strip_citations(sentence)

        # 1) package spec (ưu tiên trước key=value; đánh dấu span đã nhận)
        taken: list[tuple[int, int]] = []
        for m in _PKG_SPEC_RE.finditer(body):
            pkg, op, ver = m.group(1), m.group(2), m.group(3)
            tuples.append(AssertionTuple(
                entity=pkg, attribute="version_spec", value=f"{op}{ver}",
                constraint_source=source,
            ))
            taken.append(m.span())

        # 2) key=value (bỏ match chồng lấn package spec)
        for m in _KEY_VALUE_RE.finditer(body):
            s = m.span()
            if any(s[0] < t and s[1] > f for f, t in taken):
                continue
            tuples.append(AssertionTuple(
                entity=m.group(1), attribute="config", value=m.group(2),
                constraint_source=source,
            ))

        # 3) mỏ neo số — tái dùng firewall V24 nguyên trạng
        for anchor in extract_anchors(body):
            tuples.append(AssertionTuple(
                entity=anchor.kind, attribute="numeric", value=anchor.raw,
                constraint_source=source,
            ))

    return tuples

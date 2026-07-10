"""Agent-R — firewall compliance: chuỗi checker NE1–NE5 + vòng rewrite có trần (D32 §2.5, §4).

Toàn bộ checker TẤT ĐỊNH và THUẦN: không I/O, không LLM, không clock. Gọi LLM viết lại
và ghi event CO_* xuống store là việc của caller (Agent-E runtime, D32.4) — nhờ vậy
module test offline 100% không cần mock.

Nguyên tắc fail-closed kế thừa V24: vi phạm ⇒ CO_REJECTED / CO_ESCALATED; KHÔNG BAO GIỜ
tự sửa số cho khớp (verdict void ≠ verdict fixed). CẤM cosine/fuzzy trong mọi đường
verify của module này (gate_d32.sh kiểm bằng grep).

Chính sách vòng viết lại (§4):
- NE1/NE4/NE5: lỗi diễn đạt của LLM → được viết lại, trần MAX_REWRITES.
- NE2: sau 1 lần nhắc mà vẫn sót hard block → escalate thẳng.
- NE3: lỗi DỮ LIỆU KB (thiếu conflict_flag) → không có vòng viết lại, escalate ngay.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.compliance.assertions import extract_citations, split_sentences
from tools.compliance.schemas import LayerAResult, ReconciliationVerdict, Violation
from tools.guard.firewall import _normalize, check_output  # import nguyên trạng — không sửa guard

MAX_REWRITES = 2

# Động từ chỉ thị (EN word-boundary + VI substring) — câu chứa chúng là "actionable".
_DIRECTIVE_EN = re.compile(
    r"\b(deploy|rollback|upgrade|downgrade|pin|unpin|set|scale|restart|migrate|"
    r"install|uninstall|enable|disable|apply|provision)\b",
    re.IGNORECASE,
)
_DIRECTIVE_VI = (
    "triển khai", "nâng cấp", "hạ cấp", "cài đặt", "gỡ bỏ", "khởi động lại",
    "bật ", "tắt ", "áp dụng", "mở rộng", "thu hẹp",
)

_ACTION_HEADER_RE = re.compile(r"^#{1,6}\s*.*\b(action|hành động)\b", re.IGNORECASE)
_HEADER_RE = re.compile(r"^#{1,6}\s")


def _field(node: Any, name: str, default: Any = None) -> Any:
    """Đọc thuộc tính từ kb.Node hoặc dict — Agent-R không ép kiểu đầu vào."""
    if isinstance(node, dict):
        return node.get(name, default)
    return getattr(node, name, default)


def layer_a_source_text(layer_a: LayerAResult) -> str:
    """Render LayerAResult thành văn bản nguồn cho NE1 — mọi con số Layer A tính ra
    xuất hiện nguyên văn ở đây để firewall đối chiếu byte-exact."""
    lines: list[str] = []
    for m in layer_a.computed:
        lines.append(f"{m.name} = {m.value} {m.unit}" if m.unit else f"{m.name} = {m.value}")
    for b in layer_a.hard_blocks:
        lines.append(f"HARD BLOCK {b.block_id}: {b.subject} — {b.reason} [{b.source_node}]")
    for h in layer_a.hold_flags:
        lines.append(f"{h.verdict}: {h.subject} [{h.source_node}]")
    return "\n".join(lines)


# --- NE1: số/parameter không khớp Layer A ------------------------------------

def check_ne1_numeric(
    prose: str, layer_a: LayerAResult, node_contents: list[str]
) -> list[Violation]:
    sources = [layer_a_source_text(layer_a), *node_contents]
    fw = check_output(prose, sources, strict=True)
    return [
        Violation(never_event="NE1", subject=v.anchor.raw, detail=v.reason)
        for v in fw.violations
    ]


# --- NE2: sót hard block (chiều NGƯỢC firewall — completeness) ---------------

def check_ne2_completeness(prose: str, layer_a: LayerAResult) -> list[Violation]:
    norm_prose = _normalize(prose)
    return [
        Violation(
            never_event="NE2",
            subject=b.subject,
            detail=f"hard block {b.block_id} (nguồn {b.source_node}) không xuất hiện trong prose",
        )
        for b in layer_a.hard_blocks
        if _normalize(b.subject) not in norm_prose
    ]


# --- NE3: L2 đè L1-security thiếu conflict_flag (lỗi dữ liệu, chặn TRƯỚC LLM) --

def check_ne3_conflict_flags(retrieval_nodes: list[Any]) -> list[Violation]:
    """Quy tắc tất định: retrieval set có node L1_canonical domain=security VÀ node
    L2_local_runbook cùng domain security ⇒ node L2 đó PHẢI mang conflict_flag khai báo."""
    l1_security = any(
        _field(n, "layer") == "L1_canonical" and _field(n, "domain") == "security"
        for n in retrieval_nodes
    )
    if not l1_security:
        return []
    return [
        Violation(
            never_event="NE3",
            subject=str(_field(n, "node_id")),
            detail="node L2 domain=security đè chuẩn L1 nhưng không khai báo conflict_flag",
        )
        for n in retrieval_nodes
        if _field(n, "layer") == "L2_local_runbook"
        and _field(n, "domain") == "security"
        and not _field(n, "conflict_flag")
    ]


# --- NE4: chỉ thị actionable thiếu citation inline ---------------------------

def _is_directive(sentence: str) -> bool:
    low = sentence.lower()
    return bool(_DIRECTIVE_EN.search(sentence)) or any(v in low for v in _DIRECTIVE_VI)


def check_ne4_citations(prose: str, *, strict: bool = False) -> list[Violation]:
    """Mặc định: câu chứa động từ chỉ thị phải mang citation token.
    strict: MỌI câu trong section Action/Hành động phải có citation (chống chỉ thị
    viết vòng lọt parser động từ — red-team R2 của spec)."""
    violations: list[Violation] = []
    in_action = False
    for line in prose.splitlines():
        if _HEADER_RE.match(line):
            in_action = bool(_ACTION_HEADER_RE.match(line))
            continue
        for sentence in split_sentences(line):
            has_citation = bool(extract_citations(sentence))
            must_cite = _is_directive(sentence) or (strict and in_action)
            if must_cite and not has_citation:
                violations.append(Violation(
                    never_event="NE4",
                    subject=sentence[:120],
                    detail="câu chỉ thị actionable không có citation [node_id]/[layer_a:*]",
                ))
    return violations


# --- NE5: citation mồ côi / ngoài retrieval set -------------------------------

def check_ne5_resolve(
    prose: str,
    kb_node_ids: set[str],
    retrieval_node_ids: set[str],
    formula_ids: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    for token in extract_citations(prose):
        if token.startswith("layer_a:"):
            if token.removeprefix("layer_a:") not in formula_ids:
                violations.append(Violation(
                    never_event="NE5", subject=token,
                    detail="formula_id không tồn tại trong LayerAResult của run",
                ))
        elif token not in kb_node_ids:
            violations.append(Violation(
                never_event="NE5", subject=token,
                detail="node_id không tồn tại trong KB — citation bịa",
            ))
        elif token not in retrieval_node_ids:
            violations.append(Violation(
                never_event="NE5", subject=token,
                detail="node có thật nhưng KHÔNG thuộc retrieval set của run này",
            ))
    return violations


# --- Agent-R: verdict + vòng rewrite có trần ---------------------------------

def reconcile(
    prose: str,
    layer_a: LayerAResult,
    retrieval_nodes: list[Any],
    kb_node_ids: set[str],
    formula_ids: set[str],
    *,
    rewrite_count: int = 0,
    strict_citations: bool = False,
) -> ReconciliationVerdict:
    """Chạy đủ NE1→NE5, ra verdict theo chính sách vòng viết lại của §4."""
    retrieval_ids = {str(_field(n, "node_id")) for n in retrieval_nodes}
    node_contents = [str(_field(n, "content", "") or "") for n in retrieval_nodes]

    ne3 = check_ne3_conflict_flags(retrieval_nodes)
    violations = (
        check_ne1_numeric(prose, layer_a, node_contents)
        + check_ne2_completeness(prose, layer_a)
        + ne3
        + check_ne4_citations(prose, strict=strict_citations)
        + check_ne5_resolve(prose, kb_node_ids, retrieval_ids, formula_ids)
    )
    triggered = sorted({v.never_event for v in violations})

    if not violations:
        state = "CO_VERIFIED"
    elif ne3:
        state = "CO_ESCALATED"          # lỗi dữ liệu KB — không có vòng viết lại
    elif any(v.never_event == "NE2" for v in violations) and rewrite_count >= 1:
        state = "CO_ESCALATED"          # nhắc 1 lần vẫn sót hard block
    elif rewrite_count >= MAX_REWRITES:
        state = "CO_ESCALATED"          # hết trần
    else:
        state = "CO_REJECTED"           # trả về cho Agent-E viết lại prose

    return ReconciliationVerdict(
        passed=not violations,
        violations=violations,
        never_events_triggered=triggered,
        rewrite_count=rewrite_count,
        final_state=state,
    )


def run_reconcile_loop(
    generate_prose: Callable[[list[Violation]], str],
    layer_a: LayerAResult,
    retrieval_nodes: list[Any],
    kb_node_ids: set[str],
    formula_ids: set[str],
    *,
    strict_citations: bool = False,
) -> tuple[ReconciliationVerdict, str]:
    """Vòng reject-and-rewrite có trần. `generate_prose(violations)` do caller tiêm vào
    (LLM thật ở runtime, hàm giả trong test) — lần đầu nhận [], các lần sau nhận danh
    sách violation của lần trước. LayerAResult BẤT BIẾN trong suốt vòng lặp."""
    violations: list[Violation] = []
    verdict: ReconciliationVerdict
    prose = ""
    for attempt in range(MAX_REWRITES + 1):
        prose = generate_prose(violations)
        verdict = reconcile(
            prose, layer_a, retrieval_nodes, kb_node_ids, formula_ids,
            rewrite_count=attempt, strict_citations=strict_citations,
        )
        if verdict.final_state != "CO_REJECTED":
            return verdict, prose
        violations = verdict.violations
    return verdict, prose  # không tới được: attempt cuối luôn VERIFIED/ESCALATED

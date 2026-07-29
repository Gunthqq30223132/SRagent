"""BS4 §0 — tầng THUẦN của Consensus Generator.

Không LLM, không I/O ngoài tham số. Đây là nơi mọi con số lâm sàng được sinh ra;
`consensus_run` chỉ điều phối và nối văn. Test đánh chủ yếu vào file này.

Nguyên tắc bất di dịch (BS4-consensus):
- CẤM mọi phép số học giữa các claim (mean/pool/so độ lớn) — đó là meta-analysis,
  vĩnh viễn ngoài phạm vi và vĩnh viễn ngoài đường LLM.
- Hệ KHÔNG có khái niệm "đồng thuận số học". Cùng hướng ⇒ chỉ liệt kê song song.
- VOID/không quy đổi được trọng số vẫn VÀO ledger với weight 0.0 và hiện trong phụ
  lục Excluded — không bao giờ lặng lẽ biến mất.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from pydantic import BaseModel

from tools.guard.firewall import check_output, extract_anchors

UNMAPPED = "__unmapped__"
OVERALL_ROW = "__overall__"
UNBANDED = "__unbanded__"

# Hợp đồng trọng số BS4-consensus §31. Fail-closed: key lạ ⇒ raise (luật Anchor).
ROB_WEIGHTS: dict[str, float] = {
    "Low": 1.0,
    "Some concerns": 0.5,
    "High": 0.25,
    "VOID": 0.0,
}

# BS4 §5.2 — từ làm mềm số. LLM không được phép "khoảng 50 mg" khi nguồn ghi "50 mg".
APPROX_LEXICON = [
    "approximately",
    "about",
    "around",
    "roughly",
    "~",
    "khoảng",
    "xấp xỉ",
    "gần",
]

CLAIM_REF_RE = re.compile(r"\[clm-[A-Za-z0-9_\-]+\]")
NUMBER_RE = re.compile(r"\d")

# NE1 cần MỌI token số, kể cả số trần. `extract_anchors` của tools/guard chỉ nhận
# diện mỏ neo miền CS (IP, version, %, GB/ms/tokens…) nên với y văn nó trả RỖNG —
# "50 mg" không sinh anchor nào, và một NE1 chỉ dựa vào nó sẽ cho số bịa lọt sạch.
# `tools/guard/` là zero-touch (bất biến CLAUDE.md #4), nên lớp quét số trần nằm ở
# đây, chồng lên check_output chứ không thay thế nó.
BARE_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")


class Claim(BaseModel):
    claim_id: str
    run_id: str
    outcome_id: str
    uid: str
    field: str
    value: str
    quote: str
    rob_overall: str
    weight: float
    direction: str | None = None
    conflict_group: str | None = None


# --- Trọng số -------------------------------------------------------------------------


def rob_weight(overall: str, weights: dict[str, float] | None = None) -> float:
    """Quy đổi phán định RoB → trọng số. Key lạ ⇒ raise (không bao giờ mặc định 1.0)."""
    table = ROB_WEIGHTS if weights is None else weights
    if overall not in table:
        raise ValueError(
            f"rob_overall không nhận diện được: {overall!r}. "
            f"Hợp lệ: {sorted(table)}. Bảo thủ bất đối xứng cấm đoán mò trọng số."
        )
    return table[overall]


def band_rob_overall(overall: str, minors_bands: dict[str, int] | None = None) -> str:
    """Đưa overall về một trong 4 nhãn trọng số được.

    RoB2 đã trả đúng nhãn. MINORS trả TỔNG ĐIỂM dạng chuỗi số ("18") — quy đổi điểm
    sang nhãn là một phán định LÂM SÀNG, phải do protocol khai (`minors_bands`,
    nhãn → điểm sàn). Protocol không khai ⇒ trả UNBANDED, và claim đó nhận weight 0
    + hiện trong phụ lục Excluded kèm lý do. Tuyệt đối không tự đặt ngưỡng.
    """
    if overall in ROB_WEIGHTS:
        return overall
    try:
        score = int(overall)
    except (TypeError, ValueError):
        return UNBANDED
    if not minors_bands:
        return UNBANDED
    for label in sorted(minors_bands, key=lambda k: minors_bands[k], reverse=True):
        if score >= minors_bands[label]:
            return label if label in ROB_WEIGHTS else UNBANDED
    return "High"


# --- Ánh xạ outcome + hướng (tất định, LLM không tham gia) ----------------------------


def map_outcome(field: str, outcomes: Iterable[Any]) -> str:
    """field ∈ match_fields của outcome nào thì thuộc outcome đó (§3.4).

    Ràng buộc "một field thuộc ≤1 outcome" đã được validate lúc NẠP protocol,
    nên ở đây match đầu tiên là match duy nhất.
    """
    for o in outcomes:
        if field in getattr(o, "match_fields", []):
            return o.id
    return UNMAPPED


def assign_direction(quote: str, direction_terms: dict[str, list[str]] | None) -> str | None:
    """Gán hướng bằng substring exact sau casefold — KHÔNG cosine/fuzzy (bất biến #2).

    Match ≥2 nhóm khác nhau ⇒ None: nhập nhằng thì không phán, không đoán.
    Thiếu `direction_terms` ⇒ None: hai giá trị chỉ được trưng bày cạnh nhau.
    """
    if not direction_terms or not quote:
        return None
    q = quote.casefold()
    matched = {
        group
        for group, stems in direction_terms.items()
        if any(stem.casefold() in q for stem in stems)
    }
    if len(matched) == 1:
        return matched.pop()
    return None


# --- Dựng ledger ----------------------------------------------------------------------


def build_ledger(
    extractions: list[dict[str, Any]],
    rob_map: dict[str, str],
    protocol: Any,
    run_id: str,
) -> list[Claim]:
    """Dựng sổ cái claim từ extraction đã kiểm chứng.

    `extractions`: các dòng {uid, field, value, quote, verified}. CHỈ verified == 1
    vào ledger — verified == 2 ("không kiểm chứng được") không có anchor nên không
    được làm số liệu; verified == 0 đã bị hủy từ tầng extract.
    `rob_map`: uid → rob_overall thô (đã ưu tiên agent='human' > rob_a ở tầng gọi).
    """
    outcomes = list(getattr(protocol, "outcomes", []) or [])
    minors_bands = getattr(protocol, "minors_bands", None)
    terms_by_outcome = {
        o.id: getattr(o, "direction_terms", {}) or {} for o in outcomes
    }

    claims: list[Claim] = []
    seq = 0
    for row in extractions:
        if int(row.get("verified", 0)) != 1:
            continue
        uid = row["uid"]
        raw_overall = rob_map.get(uid)
        if raw_overall is None:
            # Không có phán định RoB ⇒ không đủ tư cách làm số liệu, nhưng vẫn phải
            # nhìn thấy được: vào ledger weight 0 với nhãn VOID.
            banded = "VOID"
        else:
            banded = band_rob_overall(raw_overall, minors_bands)

        weight = 0.0 if banded == UNBANDED else rob_weight(banded)
        outcome_id = map_outcome(row["field"], outcomes)
        direction = (
            assign_direction(row["quote"], terms_by_outcome.get(outcome_id))
            if outcome_id != UNMAPPED
            else None
        )

        seq += 1
        claims.append(
            Claim(
                claim_id=f"clm-{run_id}-{seq:03d}",
                run_id=run_id,
                outcome_id=outcome_id,
                uid=uid,
                field=row["field"],
                value=row["value"],
                quote=row["quote"],
                rob_overall=raw_overall if raw_overall is not None else "VOID",
                weight=weight,
                direction=direction,
            )
        )
    return claims


def detect_conflicts(claims: list[Claim]) -> list[Claim]:
    """Đánh dấu nhóm xung đột trong từng outcome (§4).

    Xung đột ⇔ tồn tại cặp claim từ HAI uid khác nhau, cùng outcome, weight > 0,
    có direction khác nhau và cả hai đều không NULL. Cùng hướng hoặc có NULL ⇒
    KHÔNG phán "consistent" — hệ không có khái niệm đồng thuận số học.
    """
    by_outcome: dict[str, list[Claim]] = {}
    for c in claims:
        if c.outcome_id == UNMAPPED or c.weight <= 0:
            continue
        by_outcome.setdefault(c.outcome_id, []).append(c)

    for outcome_id, group in by_outcome.items():
        opposed = False
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a.uid == b.uid:
                    continue
                if a.direction and b.direction and a.direction != b.direction:
                    opposed = True
                    break
            if opposed:
                break
        if opposed:
            for c in group:
                c.conflict_group = f"cfl-{outcome_id}"
    return claims


# --- Anchor set + kiểm narrative ------------------------------------------------------


def build_anchor_set(claims: list[Claim], unit_lexicon: list[str] | None = None) -> set[str]:
    """Tập mỏ neo hợp lệ: chỉ claim có trọng số và đã map outcome mới được cấp số."""
    units = unit_lexicon or []
    anchors: set[str] = set()
    for c in claims:
        if c.weight <= 0 or c.outcome_id == UNMAPPED:
            continue
        anchors.add(c.value)
        for a in extract_anchors(c.value):
            anchors.add(a.raw)
        for num in re.findall(r"\d+(?:[.,]\d+)?", c.value):
            anchors.add(num)
            for unit in units:
                anchors.add(f"{num} {unit}")
    return anchors


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _strip_refs(text: str) -> str:
    """Bỏ token [clm-...] trước khi soi số — chữ số trong claim_id KHÔNG phải số liệu."""
    return CLAIM_REF_RE.sub(" ", text)


def check_narrative(
    narrative: str, claims: list[Claim], anchor_set: set[str]
) -> list[str]:
    """4 lớp tường lửa BS4 §5. Trả về danh sách vi phạm — rỗng = đạt.

    Fail bất kỳ lớp nào ⇒ tầng gọi reject TOÀN BỘ narrative (không vá cục bộ).
    """
    problems: list[str] = []
    body = _strip_refs(narrative)

    # NE1 (xuôi): mọi mỏ neo số trong văn phải nằm trong anchor set.
    # Lớp 1 — mỏ neo có cấu trúc (miền CS) qua firewall dùng chung.
    verdict = check_output(body, sorted(anchor_set))
    if not verdict.passed:
        bad = ", ".join(v.anchor.raw for v in verdict.violations)
        problems.append(f"NE1: số không có nguồn trong ledger: {bad}")
    # Lớp 2 — số trần (miền y khoa). So khớp THÀNH VIÊN CHÍNH XÁC, không substring:
    # nếu ledger có "100" mà LLM viết "10", substring sẽ cho lọt còn membership thì không.
    unknown = sorted({
        tok for tok in BARE_NUMBER_RE.findall(body) if tok not in anchor_set
    })
    if unknown:
        problems.append(
            f"NE1: số không có nguồn trong ledger: {', '.join(unknown)}"
        )

    # Lint ước lượng: từ làm mềm đứng cùng câu với một con số.
    for sent in _sentences(body):
        if not NUMBER_RE.search(sent):
            continue
        low = sent.casefold()
        for word in APPROX_LEXICON:
            hit = (
                word in low
                if not word.isalpha()
                else re.search(rf"\b{re.escape(word)}\b", low) is not None
            )
            if hit:
                problems.append(
                    f"LINT: từ ước lượng {word!r} đứng cùng câu với số — "
                    "cấm làm mềm giá trị đã kiểm chứng."
                )
                break

    # NE2 (ngược): mỗi nhóm xung đột phải được trình bày cùng nhau ít nhất một câu.
    groups: dict[str, set[str]] = {}
    for c in claims:
        if c.conflict_group:
            groups.setdefault(c.conflict_group, set()).add(c.claim_id)
    for group_id, ids in groups.items():
        if not any(
            len(ids & {ref.strip("[]") for ref in CLAIM_REF_RE.findall(sent)}) >= 2
            for sent in _sentences(narrative)
        ):
            problems.append(
                f"NE2: nhóm xung đột {group_id} không được trình bày cùng nhau "
                "trong bất kỳ câu nào — không được làm mượt văn bằng cách bỏ mâu thuẫn."
            )

    # NE4: câu có số phải có trích dẫn claim.
    for sent in _sentences(narrative):
        if NUMBER_RE.search(_strip_refs(sent)) and not CLAIM_REF_RE.search(sent):
            problems.append(f"NE4: câu mang số nhưng thiếu [clm-...]: {sent[:80]!r}")

    # NE5: mọi trích dẫn phải resolve về claim có thật.
    known = {c.claim_id for c in claims}
    for ref in CLAIM_REF_RE.findall(narrative):
        if ref.strip("[]") not in known:
            problems.append(f"NE5: trích dẫn mồ côi {ref} không có trong ledger.")

    return problems


# --- Bảng render (đường thoát không-LLM) ----------------------------------------------


FALLBACK_SENTENCE = (
    "Bảng dưới trình bày nguyên văn giá trị đã kiểm chứng theo outcome; "
    "các nhóm CONFLICTING không được gộp."
)


def render_table(claims: list[Claim]) -> str:
    """Markdown tất định. Dựng TRƯỚC khi gọi LLM và dùng làm fallback khi LLM hỏng."""
    if not claims:
        return "_Ledger rỗng — không có claim nào đủ điều kiện._"

    by_outcome: dict[str, list[Claim]] = {}
    for c in claims:
        by_outcome.setdefault(c.outcome_id, []).append(c)

    lines: list[str] = []
    for outcome_id in sorted(by_outcome):
        group = by_outcome[outcome_id]
        conflicted = [c for c in group if c.conflict_group]
        normal = [c for c in group if not c.conflict_group]

        lines.append(f"### {outcome_id}")
        if normal:
            lines.append(_table_block(normal))
        if conflicted:
            lines.append("")
            lines.append("**CONFLICTING — not pooled**")
            lines.append(_table_block(conflicted))
        lines.append("")
    return "\n".join(lines).strip()


def _table_block(claims: list[Claim]) -> str:
    head = (
        "| study | RoB | weight | direction | value | claim |\n"
        "|---|---|---|---|---|---|"
    )
    rows = [
        f"| {c.uid} | {c.rob_overall} | {c.weight} | {c.direction or '—'} "
        f"| {c.value} | [{c.claim_id}] |"
        for c in sorted(claims, key=lambda x: x.claim_id)
    ]
    return "\n".join([head, *rows])


def render_excluded(claims: list[Claim]) -> str:
    """Phụ lục minh bạch: mọi claim weight 0 kèm lý do — không ai biến mất im lặng."""
    excluded = [c for c in claims if c.weight <= 0]
    if not excluded:
        return "_Không có claim nào bị loại khỏi phần số._"
    lines = ["| study | field | RoB thô | lý do |", "|---|---|---|---|"]
    for c in sorted(excluded, key=lambda x: x.claim_id):
        reason = (
            "RoB VOID — phán định không kiểm chứng được"
            if c.rob_overall == "VOID"
            else f"điểm MINORS {c.rob_overall} chưa quy đổi được "
            "(protocol chưa khai `minors_bands`)"
        )
        lines.append(f"| {c.uid} | {c.field} | {c.rob_overall} | {reason} |")
    return "\n".join(lines)

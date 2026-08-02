"""Numeric Firewall V24 Hardened — tường lửa tất định cho đầu ra LLM (local lẫn cloud).

TẠI SAO: tầng tổng hợp Layer C (Gemini/NotebookLM/Ollama) tạo văn bản trôi chảy nhưng
có thể bịa hằng số kỹ thuật — độ phức tạp thuật toán, cổng mạng, thông số phần cứng,
tỷ lệ phần trăm, liều lượng lâm sàng. Với tri thức khoa học, sai MỘT ký tự số là sai hoàn toàn.

HỢP ĐỒNG CỨNG (V24 Hardened):
- So khớp strict boundary substring trên phần chữ số sau chuẩn hóa NHẸ.
- Fail-closed: một anchor không khớp ⇒ toàn bộ đầu ra bị từ chối (passed=False).
- G1 Whitelist (Strip-and-Verify): Bóc slot templates {{slot_id}} và verified anchors.
  Nếu còn chữ số nguyên văn (unslotted raw digits) trong prose, vi phạm.
- Vacuous PASS Protection: anchors_checked == 0 raises VacuousPassError (unless allow_vacuous=True).
- Expanded Clinical Units & Polarity/Applicability Verification.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pydantic import BaseModel

from sr_agent.errors import VacuousPassError
from sr_agent.models.schemas import ClinicalPayloadItem, Polarity

AnchorKind = Literal[
    "complexity", "ip", "port", "percentage", "unit", "version", "number_series"
]

_CLINICAL_UNITS = sorted(
    [
        # Triple compound rate / concentration units
        r"mg/kg/h", r"mL/kg/h", r"ml/kg/h", r"mcg/kg/h", r"µg/kg/h", r"ug/kg/h",
        r"mg/kg/min", r"mcg/kg/min", r"µg/kg/min", r"ug/kg/min", r"mL/kg/min", r"ml/kg/min",
        # Mass per body weight
        r"mcg/kg", r"µg/kg", r"ug/kg", r"mg/kg", r"g/kg", r"ng/kg",
        # Mass / moles / eq / units per concentration (dL, mL, L)
        r"mcg/dL", r"µg/dL", r"ug/dL", r"mg/dL", r"g/dL", r"ng/dL", r"pg/dL", r"mmol/dL", r"umol/dL", r"µmol/dL", r"mEq/dL",
        r"mcg/mL", r"µg/mL", r"ug/mL", r"mg/mL", r"g/mL", r"ng/mL", r"pg/mL", r"IU/mL", r"mIU/mL", r"mEq/mL", r"mmol/mL", r"umol/mL", r"µmol/mL",
        r"mg/L", r"g/L", r"mcg/L", r"µg/L", r"ug/L", r"ng/L", r"pg/L", r"mmol/L", r"umol/L", r"µmol/L", r"mol/L", r"mEq/L", r"IU/L", r"mIU/L",
        # Area-based dosage
        r"mg/m²", r"mg/m2", r"g/m²", r"g/m2", r"mcg/m²", r"mcg/m2", r"µg/m²", r"µg/m2", r"ug/m²", r"ug/m2",
        # Flow rates
        r"mL/kg", r"mL/h", r"ml/h", r"mL/min", r"ml/min", r"l/min", r"L/min", r"L/h", r"l/h", r"drops/min", r"gtt/min",
        # Physiological parameters
        r"beats/min", r"breaths/min",
        # Pressure / clinical indicators
        r"mmHg", r"cmH2O", r"kPa",
        r"spO2", r"SpO2", r"%vol", r"MAC",
        # Activity / Equivalents
        r"mIU", r"IU", r"mU", r"mEq", r"units?", r"U",
        # Volumes
        r"mL", r"ml", r"dL", r"dl", r"µL", r"uL", r"L", r"l",
        # Mass
        r"mcg", r"µg", r"ug", r"mg", r"ng", r"pg", r"kg", r"g",
        # Physical / rate
        r"bpm", r"cm", r"mm", r"m²", r"m2",
        # Time
        r"mins?", r"hrs?", r"hr", r"secs?", r"sec", r"days?", r"weeks?", r"months?", r"years?", r"h",
        # Technical / computer units
        r"ms", r"ns", r"µs", r"us", r"GHz", r"MHz", r"kHz", r"Hz", r"GB", r"MB", r"KB", r"TB",
        r"GiB", r"MiB", r"Gbps", r"Mbps", r"Kbps", r"FLOPS", r"TFLOPS", r"W", r"kW", r"B",
        r"tokens?", r"params?",
    ],
    key=len,
    reverse=True,
)

_UNIT_REGEX = r"\b\d+(?:[.,]\d+)?\s?(?:" + "|".join(_CLINICAL_UNITS) + r")(?!\w)"

_ANCHOR_PATTERNS: list[tuple[AnchorKind, re.Pattern[str]]] = [
    ("complexity", re.compile(r"[OoΘΩ]\([^()]{1,40}\)")),
    ("ip", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?\b")),
    ("version", re.compile(r"\bv\d+\.\d+(?:\.\d+)?\b|\b\d+\.\d+\.\d+\b")),
    ("percentage", re.compile(r"\b\d+(?:\.\d+)?\s?%")),
    ("unit", re.compile(_UNIT_REGEX, re.IGNORECASE)),
    ("port", re.compile(r"(?:port|cổng)\s+(\d{2,5})\b", re.IGNORECASE)),
    ("number_series", re.compile(r"\b\d+(?:[.,]\d+)*\b")),
]

_SLOT_PATTERN = re.compile(r"\{\{[a-zA-Z0-9_\-.]+\}\}")

_NEGATION_KEYWORDS = {
    "không", "khong", "cấm", "cam", "chống chỉ định", "chong chi dinh",
    "không được", "khong duoc", "tối đa", "toi da", "không quá", "khong qua",
    "không vượt quá", "khong vuot qua", "liều tối đa", "lieu toi da",
    "do not exceed", "contraindicated", "max", "maximum", "never", "avoid",
}


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


def is_strict_substring(needle: str, source: str) -> bool:
    """Strict boundary substring matching aware of word/digit boundaries.

    Prevents '5 mg' matching '25 mg', '80' matching '8080'.
    """
    norm_needle = _normalize(needle)
    norm_source = _normalize(source)
    escaped = re.escape(norm_needle)

    prefix = r"(?<![\d.])" if re.match(r"^[\d\w.]", norm_needle) else r""
    suffix = (
        r"(?![\d.])"
        if re.search(r"[\d.]$", norm_needle)
        else (r"(?![\w/])" if re.search(r"\w$", norm_needle) else r"")
    )

    pattern = re.compile(prefix + escaped + suffix)
    return bool(pattern.search(norm_source))


def extract_anchors(text: str) -> list[NumericAnchor]:
    """Bóc mọi mỏ neo số; span chồng lấn thì giữ match dài hơn (IP thắng port...)."""
    found: list[NumericAnchor] = []
    # Ignore spans corresponding to slot templates {{slot_id}}
    taken: list[tuple[int, int]] = [m.span() for m in _SLOT_PATTERN.finditer(text)]
    for kind, pat in _ANCHOR_PATTERNS:
        for m in pat.finditer(text):
            span = m.span()
            if any(span[0] < t and span[1] > f for f, t in taken):  # chồng lấn match đã nhận
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
    allow_vacuous: bool = False,
) -> FirewallVerdict:
    """Đối chiếu từng anchor trong đầu ra LLM với kho nguồn Layer A.

    Fail-closed:
    - G1 Whitelist: Strips valid slot templates {{slot_id}} and verified numeric anchors.
      If any raw unslotted digits remain in prose, adds Violation and enforces passed = False.
    - Vacuous PASS Protection: When anchors_checked == 0 and not allow_vacuous, raises VacuousPassError.
    - Strict Boundary Substring Matching: Regex matching with boundary awareness.
    - Polarity Verification: Checks context negations against source rules.
    """
    anchors = extract_anchors(llm_output)
    if len(anchors) == 0 and not allow_vacuous:
        raise VacuousPassError("No numeric anchors checked in output (vacuous pass protection active)")

    norm_sources = [_normalize(s) for s in source_texts if s]
    violations: list[Violation] = []
    warnings: list[Violation] = []
    verified_anchors: list[NumericAnchor] = []

    for anchor in anchors:
        needle = _normalize(anchor.raw)
        matching_sources = [src for src in norm_sources if is_strict_substring(needle, src)]
        if matching_sources:
            pos_out = llm_output.find(anchor.raw)
            out_snippet = (
                llm_output[max(0, pos_out - 60):min(len(llm_output), pos_out + len(anchor.raw) + 60)].lower()
            )
            out_has_neg = any(kw in out_snippet for kw in _NEGATION_KEYWORDS)

            src_has_neg = False
            for src in matching_sources:
                p_src = src.find(needle)
                if p_src != -1:
                    src_snippet = (
                        src[max(0, p_src - 60):min(len(src), p_src + len(needle) + 60)].lower()
                    )
                    if any(kw in src_snippet for kw in _NEGATION_KEYWORDS):
                        src_has_neg = True
                        break

            if out_has_neg != src_has_neg:
                v = Violation(
                    anchor=anchor,
                    reason=(
                        f"Polarity inversion detected for '{anchor.raw}': "
                        f"output negation={out_has_neg} vs source negation={src_has_neg}"
                    ),
                )
                if strict:
                    violations.append(v)
                else:
                    warnings.append(v)
            else:
                verified_anchors.append(anchor)
        else:
            v = Violation(
                anchor=anchor,
                reason=(
                    f"'{anchor.raw}' ({anchor.kind}) không xuất hiện nguyên văn "
                    f"trong bất kỳ nguồn nào (strict boundary match) — từ chối theo nguyên tắc fail-closed"
                ),
            )
            if strict:
                violations.append(v)
            else:
                warnings.append(v)

    # G1 Whitelist (Strip-and-Verify) checking
    stripped_text = _SLOT_PATTERN.sub("", llm_output)
    anchors_to_strip = verified_anchors if strict else anchors
    for v_anchor in anchors_to_strip:
        stripped_text = stripped_text.replace(v_anchor.raw, "")

    raw_digits_match = re.search(r"\d+", stripped_text)
    if raw_digits_match and strict:
        digit_snippet = raw_digits_match.group(0)
        unslotted_anchor = NumericAnchor(
            kind="number_series",
            raw=digit_snippet,
            span=raw_digits_match.span(),
        )
        v = Violation(
            anchor=unslotted_anchor,
            reason=f"Raw unslotted digits '{digit_snippet}' found in LLM prose after slot/anchor stripping",
        )
        violations.append(v)



    return FirewallVerdict(
        passed=not violations,
        anchors_checked=len(anchors),
        violations=violations,
        warnings=warnings,
    )


def verify_clinical_payload(
    item: ClinicalPayloadItem,
    source_texts: list[str],
) -> FirewallVerdict:
    """Kiểm tra một ClinicalPayloadItem độc lập đối với các nguồn Layer A."""
    val_str = str(item.value).strip()
    unit_str = item.unit.strip() if item.unit else ""
    needle = f"{val_str} {unit_str}".strip()
    anchor = NumericAnchor(kind="unit" if unit_str else "number_series", raw=needle, span=(0, len(needle)))

    norm_sources = [_normalize(s) for s in source_texts if s]
    matching_sources = [s for s in norm_sources if is_strict_substring(needle, s)]

    if not matching_sources:
        v = Violation(
            anchor=anchor,
            reason=f"Clinical payload item '{needle}' không xuất hiện nguyên văn trong bất kỳ nguồn nào.",
        )
        return FirewallVerdict(passed=False, anchors_checked=1, violations=[v])

    violations: list[Violation] = []
    if item.polarity in (Polarity.NEGATIVE, Polarity.MAX_LIMIT):
        has_negation = False
        for s in matching_sources:
            pos = s.find(_normalize(needle))
            if pos != -1:
                snippet = s[max(0, pos - 60):min(len(s), pos + len(needle) + 60)].lower()
                if any(kw in snippet for kw in _NEGATION_KEYWORDS):
                    has_negation = True
                    break
        if not has_negation:
            violations.append(
                Violation(
                    anchor=anchor,
                    reason=(
                        f"Polarity mismatch: Payload item mang polarity {item.polarity} "
                        f"nhưng nguồn không chứa từ khóa giới hạn/phủ định."
                    ),
                )
            )
    elif item.polarity == Polarity.POSITIVE:
        for s in matching_sources:
            pos = s.find(_normalize(needle))
            if pos != -1:
                snippet = s[max(0, pos - 60):min(len(s), pos + len(needle) + 60)].lower()
                if any(kw in snippet for kw in _NEGATION_KEYWORDS):
                    violations.append(
                        Violation(
                            anchor=anchor,
                            reason=(
                                f"Polarity mismatch: Payload item khẳng định POSITIVE "
                                f"nhưng nguồn mang tính phủ định/giới hạn."
                            ),
                        )
                    )
                    break

    if item.applicability_condition:
        cond_norm = _normalize(item.applicability_condition).lower()
        cond_matched = False
        for s in matching_sources:
            pos = s.find(_normalize(needle))
            if pos != -1:
                snippet = s[max(0, pos - 80):min(len(s), pos + len(needle) + 80)].lower()
                if cond_norm in snippet:
                    cond_matched = True
                    break
        if not cond_matched:
            violations.append(
                Violation(
                    anchor=anchor,
                    reason=(
                        f"Applicability mismatch: Điều kiện áp dụng '{item.applicability_condition}' "
                        f"không có trong ngữ cảnh nguồn."
                    ),
                )
            )

    return FirewallVerdict(
        passed=not violations,
        anchors_checked=1,
        violations=violations,
    )

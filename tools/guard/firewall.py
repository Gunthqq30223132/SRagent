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
    "complexity", "ip", "port", "percentage", "unit", "version", "number_series",
    # --- Mỏ neo miền LÂM SÀNG (chỉ bật khi domain="clinical") ---
    "dose", "duration", "lab_value", "effect_size",
]

Domain = Literal["cs", "clinical"]

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

# --- Mỏ neo LÂM SÀNG ---------------------------------------------------------
# TẠI SAO TÁCH RIÊNG: bộ pattern gốc V24 sinh ra cho hằng số khoa học máy tính
# (ms, GHz, GB, tokens). Với văn bản lâm sàng nó bóc được 0 mỏ neo — nghĩa là
# "Enoxaparin 40 mg, ngưng 12 giờ, INR 1.5" đi qua firewall SẠCH vì không có gì
# để đối chiếu. Đó là lỗ hổng: không tìm thấy số KHÔNG có nghĩa là không có số.
#
# Chỉ bật khi domain="clinical" để KHÔNG đổi hành vi của mọi caller CS hiện có
# (hợp đồng cũ giữ nguyên byte-for-byte; đây là mở rộng cộng thêm, không phải sửa).
#
# Đơn vị PHÂN BIỆT HOA THƯỜNG có chủ đích: 'mg' ≠ 'MG', và 'g' thường không được
# phép khớp chữ 'G' trong 'GB' — nhầm đơn vị là nhầm 1000 lần.
_UNIT_DOSE = (
    r"(?:mcg|µg|ug|mg|g|kg|IU|UI|mmol|mEq|mL|ml|L|đv)"
)
_UNIT_TIME = (
    r"(?:giờ|h|hrs?|hours?|ngày|days?|phút|min|minutes?|tuần|weeks?|tháng|months?)"
)
_NUM = r"\d+(?:[.,]\d+)?"

_CLINICAL_PATTERNS: list[tuple[AnchorKind, re.Pattern[str]]] = [
    # Chỉ số xét nghiệm có TÊN đi kèm: 'INR 1.5', 'CrCl < 30', 'anti-Xa 0.5'.
    # Bắt cả toán tử so sánh vì '< 1.2' khác '1.2' về mặt lâm sàng.
    (
        "lab_value",
        re.compile(
            r"\b(?:INR|aPTT|PT|TT|anti[- ]?Xa|CrCl|eGFR|Hb|Hct|PLT|TC|GFR)\s*"
            r"(?:[<>≤≥]\s*=?\s*|=\s*)?" + _NUM + r"\b"
        ),
    ),
    # Ngưỡng sinh lý có đơn vị: '30 mL/phút', '120 mmHg', '1.2 mg/dL'.
    (
        "lab_value",
        re.compile(
            _NUM + r"\s?(?:mmHg|mL\s?/\s?(?:phút|min)|mg\s?/\s?dL|g\s?/\s?dL|"
            r"µmol\s?/\s?L|mmol\s?/\s?L|U\s?/\s?L)\b"
        ),
    ),
    # Liều thuốc, kèm mẫu số tuỳ chọn: '40 mg', '1 mg/kg', '0,5 mg/kg/giờ'.
    (
        "dose",
        re.compile(
            _NUM + r"\s?" + _UNIT_DOSE
            + r"(?:\s?/\s?(?:kg|m2|m²|" + _UNIT_TIME + r"))*\b"
        ),
    ),
    # Mốc thời gian, bắt cả KHOẢNG: '5-7 ngày' phải là MỘT mỏ neo, không phải
    # hai số rời — nếu tách, '5' và '7' có thể mượn nguồn từ hai chỗ khác nhau.
    (
        "duration",
        re.compile(_NUM + r"(?:\s?[-–]\s?" + _NUM + r")?\s?" + _UNIT_TIME + r"\b"),
    ),
    # Cỡ hiệu ứng & khoảng tin cậy — bắt buộc cho meta-analysis.
    (
        "effect_size",
        re.compile(
            r"\b(?:OR|RR|HR|MD|SMD|aOR|aHR|I2|I²)\s*[=:]?\s*" + _NUM + r"\b"
        ),
    ),
    (
        "effect_size",
        re.compile(
            r"\b\d{2}\s?%\s?(?:CI|KTC)\s*[:=]?\s*" + _NUM
            + r"\s?[-–đến]+\s?" + _NUM + r"\b"
        ),
    ),
    # BẮT CUỐI CÙNG — mọi con số còn sót, kể cả trần trụi không đơn vị.
    #
    # TẠI SAO PHẢI CÓ: liệt kê đủ mọi cách viết lâm sàng là việc không bao giờ
    # xong ("INR mục tiêu < 1.2", "INR đích 1,2", "target INR of 1.2"...). Mỗi
    # cách viết bỏ sót là một con số đi qua cổng mà không ai đối chiếu.
    # Đảo lại bài toán: KHÔNG liệt kê cái được bắt, mà bắt TẤT CẢ rồi để các
    # pattern có tên ở trên giành span trước (chúng chạy trước nên thắng).
    # Hệ quả có chủ ý: '2018' trong 'hướng dẫn ASRA 2018' cũng phải có mặt
    # trong nguồn. Đó là hành vi ĐÚNG — trích dẫn sai năm cũng là trích dẫn sai.
    ("number_series", re.compile(r"(?<![\w.,])" + _NUM + r"(?![\w])")),
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


def _matches_verbatim(needle: str, source: str) -> bool:
    """So khớp nguyên văn nhưng TỪ CHỐI khi needle nằm lọt bên trong một số lớn hơn.

    TẠI SAO: `needle in source` thuần substring cho PASS SAI — '5 mg' được "chứng thực"
    bởi nguồn '25 mg' (thiếu 5 lần), '9.9%' bởi '99.9%' (sai 10 lần). Con số nhỏ hơn
    không bao giờ được phép mượn chữ số của con số lớn hơn để hợp lệ hóa.

    Ranh giới chỉ chặn ĐÚNG trường hợp chữ số liền kề (hoặc dấu thập phân/phân cách
    nghìn nối tiếp bằng chữ số) — không chặn dấu phẩy liệt kê: trong 'port 8080, 8081'
    thì '8080' vẫn khớp, vì sau dấu ',' là khoảng trắng chứ không phải chữ số.
    """
    pattern = (
        r"(?<![\d])(?<![\d][.,])"      # trước: không phải chữ số, không phải <số><.,>
        + re.escape(needle)
        + r"(?![\d])(?![.,]\d)"        # sau: không phải chữ số, không phải <.,><số>
    )
    return re.search(pattern, source) is not None


# Từ khóa nhận biết "câu này đang nói chuyện lâm sàng" — dùng cho chính sách
# zero-anchor ở domain="clinical". Danh sách CÓ CHỦ Ý ngắn và mở rộng dần khi
# thêm miền bệnh: thà bỏ sót cảnh báo còn hơn báo động giả tràn lan làm người
# duyệt mất niềm tin vào cổng (alarm fatigue).
_CLINICAL_TERMS = re.compile(
    r"(?i)\b(?:heparin|enoxaparin|lovenox|warfarin|coumadin|rivaroxaban|xarelto|"
    r"apixaban|eliquis|dabigatran|pradaxa|edoxaban|clopidogrel|plavix|prasugrel|"
    r"ticagrelor|aspirin|fondaparinux|LMWH|DOAC|NOAC|VKA|"
    r"tê tủy sống|ngoài màng cứng|neuraxial|epidural|spinal|catheter|"
    r"liều|dose|ngưng thuốc|bắc cầu|bridging|chống đông|anticoagula)\w*"
)


def _looks_clinical(text: str) -> bool:
    """Câu có nhắc thuốc/thủ thuật lâm sàng không? (cho chính sách zero-anchor)"""
    return _CLINICAL_TERMS.search(text) is not None


def extract_anchors(text: str, domain: Domain = "cs") -> list[NumericAnchor]:
    """Bóc mọi mỏ neo số; span chồng lấn thì giữ match dài hơn (IP thắng port...).

    domain="clinical" bật thêm bộ pattern lâm sàng. Pattern lâm sàng đứng TRƯỚC
    pattern CS để span dài thắng: '30 mL/phút' phải thành một mỏ neo lab_value,
    không bị pattern 'unit' của CS xé thành mảnh.
    """
    patterns = (
        _CLINICAL_PATTERNS + _ANCHOR_PATTERNS if domain == "clinical"
        else _ANCHOR_PATTERNS
    )
    found: list[NumericAnchor] = []
    taken: list[tuple[int, int]] = []
    for kind, pat in patterns:
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
    domain: Domain = "cs",
) -> FirewallVerdict:
    """Đối chiếu từng anchor trong đầu ra LLM với kho nguồn Layer A.

    Anchor "khớp" ⇔ dạng chuẩn hóa của nó xuất hiện nguyên văn trong ít nhất một
    nguồn đã chuẩn hóa, VÀ không nằm lọt bên trong một số lớn hơn (xem
    `_matches_verbatim`). Không có khái niệm "gần đúng".

    domain="clinical" thay đổi HAI điều, cả hai đều theo hướng chặt hơn:
    1. Bật bộ mỏ neo lâm sàng (liều, mốc thời gian, chỉ số XN, cỡ hiệu ứng).
    2. ĐẢO chính sách zero-anchor: ở miền CS, văn bản không chứa mỏ neo nào là
       hợp lệ (câu tổng quan thuần chữ). Ở miền lâm sàng, một phát biểu KHÔNG
       chứa mỏ neo nào mà vẫn nhắc tên thuốc/thủ thuật là dấu hiệu số đã bị
       viết bằng chữ ("ngưng hai mươi bốn giờ") hoặc bị bỏ sót — cả hai đều
       nguy hiểm hơn là số sai, vì không có gì để đối chiếu. Fail-closed.
    """
    anchors = extract_anchors(llm_output, domain=domain)
    norm_sources = [_normalize(s) for s in source_texts if s]

    violations: list[Violation] = []
    warnings: list[Violation] = []

    if domain == "clinical" and not anchors and _looks_clinical(llm_output):
        violations.append(Violation(
            anchor=NumericAnchor(kind="dose", raw="", span=(0, 0)),
            reason=(
                "Văn bản lâm sàng nhắc thuốc/thủ thuật nhưng KHÔNG bóc được mỏ neo "
                "số nào — không có gì để đối chiếu. Số viết bằng chữ hoặc bị bỏ sót "
                "đều bị từ chối: không kiểm được KHÔNG có nghĩa là đạt."
            ),
        ))
    for anchor in anchors:
        needle = _normalize(anchor.raw)
        if any(_matches_verbatim(needle, src) for src in norm_sources):
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

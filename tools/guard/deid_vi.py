"""De-identification engine cho bệnh án tiếng Việt (NĐ13/DPIA compliance).

Phát hiện và đánh dấu các thông tin định danh cá nhân (PII/PHI) trong
văn bản y tế tiếng Việt bao gồm: MSBA, BHYT, SĐT (di động + cố định),
CCCD/CMND, tên bệnh nhân, giường bệnh, khoa/phòng, địa chỉ.

Nguyên tắc fail-closed: nếu nghi ngờ là PII thì đánh dấu, không bỏ sót.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class DeIdFinding:
    """Một phát hiện PII/PHI."""
    category: str           # MSBA, BHYT, PHONE, CCCD, NAME, BED, DEPT, ADDRESS
    matched_text: str       # chuỗi khớp
    span: tuple[int, int]   # vị trí (start, end)
    confidence: str = "HIGH"  # HIGH, MEDIUM


@dataclass
class DeIdResult:
    """Kết quả quét de-identification."""
    findings: list[DeIdFinding] = field(default_factory=list)
    redacted_text: str = ""

    @property
    def has_pii(self) -> bool:
        return len(self.findings) > 0


# === REGEX PATTERNS ===

# Mã số bệnh án (MSBA / SHS): 5-15 chữ số, thường kèm từ khóa
_MSBA_KEYWORD = re.compile(
    r"(?:MSBA|[Mm]ã\s*(?:số\s*)?[Bb]ệnh\s*[Áá]n|SHS|[Ss]ố\s*[Hh]ồ\s*[Ss]ơ|"
    r"[Mm]ã\s*BN|[Mm]ã\s*[Bb]ệnh\s*[Nn]hân)"
    r"\s*[:.]?\s*(\d{4,15})",
    re.UNICODE,
)

# BHYT: 2 chữ cái + 1 số + 12 số (có thể có dấu gạch)
_BHYT = re.compile(
    r"(?:BHYT|[Bb]ảo\s*[Hh]iểm\s*[Yy]\s*[Tt]ế|[Ss]ố\s*thẻ\s*BHYT)"
    r"\s*[:.]?\s*([A-Z]{2}[-]?\d{1,2}[-]?\d{10,13})",
    re.UNICODE,
)

# SĐT di động Việt Nam: 0[3|5|7|8|9]x xxx xxxx
_PHONE_MOBILE = re.compile(
    r"\b0[35789]\d[\s.]?\d{3,4}[\s.]?\d{3,4}\b"
)

# SĐT cố định Việt Nam: 0[2x] hoặc 0[2xx] + xxx xxxx
_PHONE_LANDLINE = re.compile(
    r"\b0(?:2[0-9]{1,2})[\s.]?\d{3,4}[\s.]?\d{3,4}\b"
)

# SĐT có từ khóa prefix (bắt mọi dạng kể cả quốc tế)
_PHONE_KEYWORD = re.compile(
    r"(?:[SsĐđ][ĐđTt]|[Dd]iện\s*[Tt]hoại|[Ss]ố\s*(?:ĐT|đt|điện\s*thoại)|"
    r"[Ll]iên\s*[Hh]ệ|LL)"
    r"\s*[:.]?\s*([\d\s.+()-]{8,15})",
    re.UNICODE,
)

# CCCD/CMND: 9 hoặc 12 chữ số
_CCCD = re.compile(
    r"(?:CCCD|CMND|[Cc]ăn\s*[Cc]ước|[Cc]hứng\s*[Mm]inh)"
    r"\s*[:.]?\s*(\d{9,12})",
    re.UNICODE,
)

# Giường bệnh: "Giường [số]" hoặc "G.[số]"
_BED = re.compile(
    r"(?:[Gg]iường|[Gg]\.)\s*(?:số\s*)?[:.]?\s*(\d{1,4}[A-Za-z]?)",
    re.UNICODE,
)

# Khoa / Phòng / Bệnh viện
_DEPT = re.compile(
    r"(?:[Kk]hoa|[Pp]hòng|BV|[Bb]ệnh\s*[Vv]iện)\s*[:.]?\s*"
    r"([A-ZÀ-Ỹa-zà-ỹ][A-ZÀ-Ỹa-zà-ỹ\s\-&.]{2,40}?)(?=[,.\n;(]|\s{2,}|$)",
    re.UNICODE,
)

# Địa chỉ (prefix keyword)
_ADDRESS = re.compile(
    r"(?:[ĐđĐĐ]ịa\s*[Cc]hỉ|ĐC|đc|[Nn]ơi\s*[Ởở]|[Tt]hường\s*[Tt]rú)"
    r"\s*[:.]?\s*(.{5,80}?)(?=[.\n;]|$)",
    re.UNICODE,
)

# Tên người (Vietnamese full name pattern: Họ Tên 2-5 từ, capitalized)
_VN_NAME_KEYWORD = re.compile(
    r"(?:[Hh]ọ\s*(?:và\s*)?[Tt]ên|BN|[Bb]ệnh\s*[Nn]hân|[Nn]gười\s*[Nn]hà|"
    r"[Nn]gười\s*[Gg]iám\s*[Hh]ộ|[Tt]hân\s*[Nn]hân)"
    r"\s*[:.]?\s*"
    r"([A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+){1,5})",
    re.UNICODE,
)

# Ngày sinh / Ngày vào viện (sensitive dates with keyword)
_DATE_KEYWORD = re.compile(
    r"(?:[Nn]gày\s*[Ss]inh|NS|[Nn]gày\s*[Vv]ào\s*[Vv]iện|"
    r"[Nn]gày\s*[Rr]a\s*[Vv]iện|[Nn]gày\s*[Kk]hám)"
    r"\s*[:.]?\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
    re.UNICODE,
)

_ALL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("MSBA", _MSBA_KEYWORD),
    ("BHYT", _BHYT),
    ("PHONE", _PHONE_KEYWORD),
    ("PHONE", _PHONE_MOBILE),
    ("PHONE", _PHONE_LANDLINE),
    ("CCCD", _CCCD),
    ("BED", _BED),
    ("DEPT", _DEPT),
    ("ADDRESS", _ADDRESS),
    ("NAME", _VN_NAME_KEYWORD),
    ("DATE", _DATE_KEYWORD),
]


def scan_pii(text: str) -> DeIdResult:
    """Quét văn bản tìm tất cả PII/PHI theo các pattern tiếng Việt.

    Returns:
        DeIdResult with findings and redacted_text.
    """
    findings: list[DeIdFinding] = []
    taken_spans: list[tuple[int, int]] = []

    for category, pattern in _ALL_PATTERNS:
        for m in pattern.finditer(text):
            # Ưu tiên group(1) nếu có, fallback group(0)
            matched = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
            span = (m.start(1), m.end(1)) if m.lastindex and m.lastindex >= 1 else m.span()

            # Tránh chồng lấn
            if any(span[0] < te and span[1] > ts for ts, te in taken_spans):
                continue

            findings.append(DeIdFinding(
                category=category,
                matched_text=matched.strip(),
                span=span,
            ))
            taken_spans.append(span)

    findings.sort(key=lambda f: f.span[0])

    # Tạo redacted text
    redacted = text
    for f in reversed(findings):
        placeholder = f"[{f.category}_REDACTED]"
        redacted = redacted[:f.span[0]] + placeholder + redacted[f.span[1]:]

    return DeIdResult(findings=findings, redacted_text=redacted)

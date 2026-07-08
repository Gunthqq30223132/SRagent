"""Outbound Interceptor — linter tiền-xuất chặn PII/secrets rời khỏi máy local.

TẠI SAO: kiến trúc D31 cho phép một luồng OPT-IN gửi ngữ liệu lên cloud (Gemini File
Search / bundle NotebookLM). Nội dung paper là công khai, nhưng payload xuất đi có thể
vô tình dính: API key, đường dẫn tuyệt đối lộ username, IP nội bộ, email/SĐT/CCCD
(phạm vi NĐ 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân). Interceptor này là chốt chặn
CUỐI CÙNG ngay trước socket: fail-closed — có phát hiện là chặn, không tự sửa.

NGUYÊN TẮC:
- `assert_sanitized()` raise OutboundViolation khi có finding; KHÔNG auto-redact ngầm.
- `redact()` là chế độ opt-in riêng, thay match bằng «REDACTED:rule_id».
- Báo cáo/audit không bao giờ chứa secret nguyên văn: match bị che một phần,
  audit JSONL chỉ ghi rule_id + SHA-256 rút gọn.
- Regex tất định trước; NER là phần mở rộng tương lai (xem docs/specs/D31 §5).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pydantic import BaseModel

_ENV_SECRET_NAMES = (
    "IEEE_API_KEY|NOTION_TOKEN|NOTION_PARENT_PAGE_ID|ALERT_WEBHOOK_URL|"
    "GEMINI_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY"
)

# (rule_id, pattern, mô tả). Thứ tự = thứ tự quét; một đoạn text có thể dính nhiều rule.
RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("SECRET_OPENAI_ANTHROPIC", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
     "API key dạng sk- (OpenAI/Anthropic)"),
    ("SECRET_GITHUB", re.compile(r"\b(?:ghp_|gho_|ghs_|ghr_)[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
     "GitHub token"),
    ("SECRET_AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    ("SECRET_SLACK", re.compile(r"\bxox[bpars]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
    ("SECRET_GOOGLE", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"), "Google API key"),
    ("ENV_ASSIGNMENT", re.compile(rf"\b(?:{_ENV_SECRET_NAMES})\s*=\s*['\"]?\S{{4,}}"),
     "Gán giá trị cho biến môi trường nhạy cảm (tên biến đơn thuần thì không sao)"),
    ("PATH_HOME", re.compile(r"(?:/Users|/home)/[A-Za-z0-9._-]+(?:/[^\s\"'`)\]]*)?"),
     "Đường dẫn tuyệt đối lộ username máy local"),
    ("IP_PRIVATE", re.compile(
        r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
        r"|127\.0\.0\.1)(?::\d{1,5})?\b"
        r"|\blocalhost:\d{2,5}\b"),
     "IP nội bộ (RFC1918/loopback) hoặc endpoint localhost"),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
     "Địa chỉ email (PII theo NĐ 13/2023/NĐ-CP — kể cả email tác giả trong trích dẫn)"),
    ("PHONE_VN", re.compile(r"(?<!\d)(?:\+84|0)(?:3|5|7|8|9)\d{8}(?!\d)"),
     "Số điện thoại di động Việt Nam"),
    ("CCCD_VN", re.compile(r"(?<!\d)\d{12}(?!\d)"),
     "Chuỗi 12 chữ số liền — khớp định dạng CCCD (NĐ 13/2023/NĐ-CP)"),
]

_HIGH_ENTROPY = re.compile(r"\b[A-Za-z0-9+/=_-]{40,}\b")
_ENTROPY_BITS_PER_CHAR = 4.0
DEFAULT_AUDIT_PATH = Path("staging/guard_audit.jsonl")


class Finding(BaseModel):
    rule_id: str
    description: str
    masked_match: str        # KHÔNG BAO GIỜ là secret nguyên văn
    span: tuple[int, int]


class OutboundViolation(Exception):
    """Payload chưa sạch — bị chặn trước khi rời máy."""

    def __init__(self, findings: list[Finding]):
        self.findings = findings
        rules = ", ".join(sorted({f.rule_id for f in findings}))
        super().__init__(
            f"Payload bị chặn: {len(findings)} phát hiện ({rules}). "
            f"Dùng redact() nếu muốn che chủ động, hoặc gỡ nội dung nhạy cảm."
        )


def _mask(match: str) -> str:
    if len(match) <= 8:
        return f"{match[:2]}…(len={len(match)})"
    return f"{match[:4]}…{match[-2:]}(len={len(match)})"


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def scan(payload: str) -> list[Finding]:
    findings: list[Finding] = []
    for rule_id, pat, desc in RULES:
        for m in pat.finditer(payload):
            findings.append(Finding(
                rule_id=rule_id, description=desc,
                masked_match=_mask(m.group(0)), span=m.span(),
            ))
    # Chuỗi entropy cao: token/hash không khớp prefix nào đã biết vẫn bị bắt.
    for m in _HIGH_ENTROPY.finditer(payload):
        s = m.group(0)
        if _shannon_entropy(s) >= _ENTROPY_BITS_PER_CHAR and not any(
            f.span[0] <= m.start() < f.span[1] for f in findings
        ):
            findings.append(Finding(
                rule_id="HIGH_ENTROPY_STRING",
                description="Chuỗi ≥40 ký tự entropy cao — nghi là token/khóa",
                masked_match=_mask(s), span=m.span(),
            ))
    findings.sort(key=lambda f: f.span)
    return findings


def _audit(findings: list[Finding], payload: str, audit_path: Path) -> None:
    """Ghi vết local — chỉ rule_id + hash rút gọn, không nội dung."""
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as fh:
        for f in findings:
            raw = payload[f.span[0]:f.span[1]]
            fh.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "rule_id": f.rule_id,
                "match_sha256_12": hashlib.sha256(raw.encode()).hexdigest()[:12],
            }, ensure_ascii=False) + "\n")


def assert_sanitized(payload: str, *, audit_path: Path = DEFAULT_AUDIT_PATH) -> None:
    """Chốt chặn fail-closed: có finding là raise, kèm audit local."""
    findings = scan(payload)
    if findings:
        _audit(findings, payload, audit_path)
        raise OutboundViolation(findings)


def redact(payload: str) -> str:
    """Chế độ che chủ động (opt-in): thay từng match bằng «REDACTED:rule_id»."""
    findings = scan(payload)
    out: list[str] = []
    cursor = 0
    for f in findings:
        start, end = f.span
        if start < cursor:          # chồng lấn với match đã che
            continue
        out.append(payload[cursor:start])
        out.append(f"«REDACTED:{f.rule_id}»")
        cursor = end
    out.append(payload[cursor:])
    return "".join(out)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("Cách dùng: python tools/guard/outbound.py <file>", file=sys.stderr)
        return 2
    payload = Path(args[0]).read_text(encoding="utf-8")
    findings = scan(payload)
    if not findings:
        print("SẠCH — payload đủ điều kiện xuất.")
        return 0
    for f in findings:
        print(f"[{f.rule_id}] {f.masked_match} — {f.description}", file=sys.stderr)
    print(f"BỊ CHẶN — {len(findings)} phát hiện.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

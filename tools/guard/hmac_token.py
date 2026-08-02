"""HMAC Token Signing cho AGENTS.md Harness Stop-Tokens.

Token `GATE_PASS` phải được ký HMAC-SHA256 với `tree_sha ‖ plan_sha`
để tránh agent tự giả mạo token khi tự động hóa (Gemini Spark).

Token format: GATE_PASS::<hmac_hex>::<timestamp_iso>
"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone


def sign_gate_token(
    tree_sha: str,
    plan_sha: str,
    secret: str,
    *,
    timestamp: str | None = None,
) -> str:
    """Tạo HMAC-SHA256 signed GATE_PASS token.

    Args:
        tree_sha: SHA hash của git tree hiện tại.
        plan_sha: SHA hash của file implementation_plan.md.
        secret: Bí mật chia sẻ giữa gate và verifier.
        timestamp: ISO timestamp tùy chọn (mặc định: now UTC).

    Returns:
        Token dạng "GATE_PASS::<hmac_hex>::<timestamp>"
    """
    if not tree_sha or not plan_sha or not secret:
        raise ValueError("tree_sha, plan_sha, and secret must be non-empty")

    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    # Domain Separation & Length-Prefixed Message Format:
    # "sragent-gate-v1:{len(tree_sha)}:{tree_sha}:{len(plan_sha)}:{plan_sha}:{timestamp}"
    message = f"sragent-gate-v1:{len(tree_sha)}:{tree_sha}:{len(plan_sha)}:{plan_sha}:{timestamp}"
    sig = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return f"GATE_PASS::{sig}::{timestamp}"


def verify_gate_token(
    token: str,
    tree_sha: str,
    plan_sha: str,
    secret: str,
    *,
    max_age_seconds: int = 3600,
) -> bool:
    """Xác thực HMAC-SHA256 signed GATE_PASS token.

    Args:
        token: Token dạng "GATE_PASS::<hmac_hex>::<timestamp>".
        tree_sha: SHA hash của git tree hiện tại.
        plan_sha: SHA hash của file implementation_plan.md.
        secret: Bí mật chia sẻ.
        max_age_seconds: Tuổi tối đa cho phép (mặc định 1 giờ).

    Returns:
        True nếu token hợp lệ, False nếu không.
    """
    if not token or not token.startswith("GATE_PASS::"):
        return False

    parts = token.split("::")
    if len(parts) != 3:
        return False

    _, sig_hex, timestamp = parts

    # Reconstruct expected signature with Domain Separation
    message = f"sragent-gate-v1:{len(tree_sha)}:{tree_sha}:{len(plan_sha)}:{plan_sha}:{timestamp}"
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison
    if not hmac.compare_digest(sig_hex, expected_sig):
        return False

    # Check age
    try:
        token_time = datetime.fromisoformat(timestamp)
        now = datetime.now(timezone.utc)
        age = (now - token_time).total_seconds()
        if age > max_age_seconds or age < -60:  # allow 60s clock skew
            return False
    except (ValueError, TypeError):
        return False

    return True


def parse_gate_token(token: str) -> dict[str, str] | None:
    """Phân tích token thành các thành phần."""
    if not token or not token.startswith("GATE_PASS::"):
        return None

    parts = token.split("::")
    if len(parts) != 3:
        return None

    return {
        "prefix": parts[0],
        "signature": parts[1],
        "timestamp": parts[2],
    }

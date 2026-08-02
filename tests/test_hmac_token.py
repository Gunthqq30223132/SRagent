"""Tests cho HMAC Token Signing & Verification."""

import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.guard.hmac_token import sign_gate_token, verify_gate_token, parse_gate_token


TREE_SHA = "abc123def456789"
PLAN_SHA = "plan_sha_0987654321"
SECRET = "test-secret-key-for-hmac"


def test_sign_and_verify():
    """Token ký ra phải verify thành công."""
    token = sign_gate_token(TREE_SHA, PLAN_SHA, SECRET)
    assert token.startswith("GATE_PASS::"), f"Token should start with GATE_PASS::, got: {token}"
    assert verify_gate_token(token, TREE_SHA, PLAN_SHA, SECRET), "Should verify valid token"


def test_tampered_signature():
    """Sửa chữ ký HMAC phải bị từ chối."""
    token = sign_gate_token(TREE_SHA, PLAN_SHA, SECRET)
    parts = token.split("::")
    tampered = f"{parts[0]}::{'0' * 64}::{parts[2]}"
    assert not verify_gate_token(tampered, TREE_SHA, PLAN_SHA, SECRET), "Tampered sig should fail"


def test_wrong_tree_sha():
    """Khác tree_sha phải bị từ chối (detect code drift)."""
    token = sign_gate_token(TREE_SHA, PLAN_SHA, SECRET)
    assert not verify_gate_token(token, "different_tree_sha", PLAN_SHA, SECRET)


def test_wrong_plan_sha():
    """Khác plan_sha phải bị từ chối (detect plan modification)."""
    token = sign_gate_token(TREE_SHA, PLAN_SHA, SECRET)
    assert not verify_gate_token(token, TREE_SHA, "different_plan_sha", SECRET)


def test_wrong_secret():
    """Sai secret phải bị từ chối."""
    token = sign_gate_token(TREE_SHA, PLAN_SHA, SECRET)
    assert not verify_gate_token(token, TREE_SHA, PLAN_SHA, "wrong-secret")


def test_forged_plain_text_token():
    """Agent tự gõ 'GATE_PASS' (không có HMAC) phải bị từ chối."""
    assert not verify_gate_token("GATE_PASS", TREE_SHA, PLAN_SHA, SECRET)
    assert not verify_gate_token("GATE_PASS::", TREE_SHA, PLAN_SHA, SECRET)
    assert not verify_gate_token("", TREE_SHA, PLAN_SHA, SECRET)


def test_expired_token():
    """Token quá hạn phải bị từ chối."""
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    token = sign_gate_token(TREE_SHA, PLAN_SHA, SECRET, timestamp=old_ts)
    assert not verify_gate_token(token, TREE_SHA, PLAN_SHA, SECRET, max_age_seconds=3600)


def test_parse_token():
    """Parse token thành components."""
    token = sign_gate_token(TREE_SHA, PLAN_SHA, SECRET)
    parsed = parse_gate_token(token)
    assert parsed is not None
    assert parsed["prefix"] == "GATE_PASS"
    assert len(parsed["signature"]) == 64  # SHA256 hex
    assert parsed["timestamp"]  # non-empty


def test_parse_invalid():
    """Parse invalid token trả None."""
    assert parse_gate_token("not a token") is None
    assert parse_gate_token("") is None
    assert parse_gate_token("GATE_PASS::only_one_part") is None


def test_empty_inputs_raise():
    """Inputs rỗng phải raise ValueError."""
    import pytest
    with pytest.raises(ValueError):
        sign_gate_token("", PLAN_SHA, SECRET)
    with pytest.raises(ValueError):
        sign_gate_token(TREE_SHA, "", SECRET)
    with pytest.raises(ValueError):
        sign_gate_token(TREE_SHA, PLAN_SHA, "")


if __name__ == "__main__":
    test_sign_and_verify()
    test_tampered_signature()
    test_wrong_tree_sha()
    test_wrong_plan_sha()
    test_wrong_secret()
    test_forged_plain_text_token()
    test_expired_token()
    test_parse_token()
    test_parse_invalid()
    print("\n✅ All HMAC Token tests passed!")

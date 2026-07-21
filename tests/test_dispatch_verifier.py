"""Tests for sr_agent.store.dispatch_verifier.

Covers:
(a) Combo fallback where model_returned is a verified leaf -> PASS (VERIFIED)
(b) Fallback to an unverified leaf -> FAIL (UNVERIFIABLE)
(c) model_returned equals unresolved combo name -> FAIL (UNVERIFIABLE)
(d) Single leaf model regression -> PASS (VERIFIED)
Edge cases: non-200 HTTP status, 0/negative tokens, invalid SHA256 hashes, empty model_returned.
"""

from __future__ import annotations

import pytest

from sr_agent.store.dispatch_verifier import (
    KNOWN_COMBO_ALIASES,
    VERIFIED_MODELS,
    DispatchVerificationResult,
    normalize_model_name,
    verify_dispatch,
)

VALID_CAPSULE_SHA = "a" * 64
VALID_COMPLETION_SHA = "b" * 64


def test_normalize_model_name() -> None:
    assert normalize_model_name(None) == ""
    assert normalize_model_name("") == ""
    assert normalize_model_name("   ") == ""
    assert normalize_model_name("ollama/qwen2.5:7b-instruct") == "qwen2.5:7b-instruct"
    assert normalize_model_name("9router/combo-smart") == "combo-smart"
    assert normalize_model_name("  QWEN2.5:7B-INSTRUCT  ") == "qwen2.5:7b-instruct"
    assert normalize_model_name("openrouter/openai/gpt-4o") == "gpt-4o"


def test_combo_fallback_to_verified_leaf_passes() -> None:
    """(a) Combo fallback where model_returned is a verified leaf -> PASS (VERIFIED)."""
    result = verify_dispatch(
        req_model="9router/combo-smart",
        model_returned="ollama/qwen2.5:7b-instruct",
        capsule_sha256=VALID_CAPSULE_SHA,
        completion_sha256=VALID_COMPLETION_SHA,
        tokens=150,
        status=200,
    )
    assert result.passed is True
    assert result.status == "VERIFIED"
    assert result.reason == "Dispatch verification successful"
    assert result.req_model == "9router/combo-smart"
    assert result.model_returned == "ollama/qwen2.5:7b-instruct"


def test_combo_fallback_to_unverified_leaf_fails() -> None:
    """(b) Fallback to an unverified leaf -> FAIL (UNVERIFIABLE)."""
    result = verify_dispatch(
        req_model="9router/combo-smart",
        model_returned="ollama/unverified-custom-model:1b",
        capsule_sha256=VALID_CAPSULE_SHA,
        completion_sha256=VALID_COMPLETION_SHA,
        tokens=150,
        status=200,
    )
    assert result.passed is False
    assert result.status == "UNVERIFIABLE"
    assert "is not in VERIFIED_MODELS" in result.reason


def test_unresolved_combo_alias_fails() -> None:
    """(c) model_returned equals unresolved combo name -> FAIL (UNVERIFIABLE)."""
    for alias in KNOWN_COMBO_ALIASES:
        result = verify_dispatch(
            req_model=f"9router/{alias}",
            model_returned=alias,
            capsule_sha256=VALID_CAPSULE_SHA,
            completion_sha256=VALID_COMPLETION_SHA,
            tokens=150,
            status=200,
        )
        assert result.passed is False
        assert result.status == "UNVERIFIABLE"
        assert "matches unresolved combo alias" in result.reason

        result_prefixed = verify_dispatch(
            req_model=alias,
            model_returned=f"9router/{alias}",
            capsule_sha256=VALID_CAPSULE_SHA,
            completion_sha256=VALID_COMPLETION_SHA,
            tokens=150,
            status=200,
        )
        assert result_prefixed.passed is False
        assert result_prefixed.status == "UNVERIFIABLE"
        assert "matches unresolved combo alias" in result_prefixed.reason


def test_single_leaf_model_regression_passes() -> None:
    """(d) Single leaf model regression -> PASS (VERIFIED)."""
    result = verify_dispatch(
        req_model="ollama/qwen2.5:7b-instruct",
        model_returned="ollama/qwen2.5:7b-instruct",
        capsule_sha256=VALID_CAPSULE_SHA,
        completion_sha256=VALID_COMPLETION_SHA,
        tokens=200,
        status=200,
    )
    assert result.passed is True
    assert result.status == "VERIFIED"


def test_non_200_http_status_fails() -> None:
    result = verify_dispatch(
        req_model="qwen2.5:7b-instruct",
        model_returned="qwen2.5:7b-instruct",
        capsule_sha256=VALID_CAPSULE_SHA,
        completion_sha256=VALID_COMPLETION_SHA,
        tokens=100,
        status=500,
    )
    assert result.passed is False
    assert result.status == "HTTP_ERROR"
    assert result.http_status == 500
    assert "HTTP status code 500 != 200" in result.reason


def test_zero_or_negative_tokens_fails() -> None:
    result_zero = verify_dispatch(
        req_model="qwen2.5:7b-instruct",
        model_returned="qwen2.5:7b-instruct",
        capsule_sha256=VALID_CAPSULE_SHA,
        completion_sha256=VALID_COMPLETION_SHA,
        tokens=0,
        status=200,
    )
    assert result_zero.passed is False
    assert result_zero.status == "EMPTY_RESPONSE"
    assert "Token count 0 <= 0" in result_zero.reason

    result_neg = verify_dispatch(
        req_model="qwen2.5:7b-instruct",
        model_returned="qwen2.5:7b-instruct",
        capsule_sha256=VALID_CAPSULE_SHA,
        completion_sha256=VALID_COMPLETION_SHA,
        tokens=-10,
        status=200,
    )
    assert result_neg.passed is False
    assert result_neg.status == "EMPTY_RESPONSE"


def test_invalid_sha256_digests_fail() -> None:
    result_bad_capsule = verify_dispatch(
        req_model="qwen2.5:7b-instruct",
        model_returned="qwen2.5:7b-instruct",
        capsule_sha256="invalid_short_hash",
        completion_sha256=VALID_COMPLETION_SHA,
        tokens=100,
        status=200,
    )
    assert result_bad_capsule.passed is False
    assert result_bad_capsule.status == "INTEGRITY_ERROR"
    assert "capsule_sha256" in result_bad_capsule.reason

    result_bad_completion = verify_dispatch(
        req_model="qwen2.5:7b-instruct",
        model_returned="qwen2.5:7b-instruct",
        capsule_sha256=VALID_CAPSULE_SHA,
        completion_sha256="z" * 64,  # 'z' is not hex
        tokens=100,
        status=200,
    )
    assert result_bad_completion.passed is False
    assert result_bad_completion.status == "INTEGRITY_ERROR"
    assert "completion_sha256" in result_bad_completion.reason


def test_empty_or_none_model_returned_fails() -> None:
    result_empty = verify_dispatch(
        req_model="combo-smart",
        model_returned="",
        capsule_sha256=VALID_CAPSULE_SHA,
        completion_sha256=VALID_COMPLETION_SHA,
        tokens=100,
        status=200,
    )
    assert result_empty.passed is False
    assert result_empty.status == "UNVERIFIABLE"
    assert "model_returned is empty or invalid" in result_empty.reason

    result_none = verify_dispatch(
        req_model="combo-smart",
        model_returned=None,
        capsule_sha256=VALID_CAPSULE_SHA,
        completion_sha256=VALID_COMPLETION_SHA,
        tokens=100,
        status=200,
    )
    assert result_none.passed is False
    assert result_none.status == "UNVERIFIABLE"
    assert "model_returned is empty or invalid" in result_none.reason


def test_all_verified_models_pass() -> None:
    for model in VERIFIED_MODELS:
        result = verify_dispatch(
            req_model="combo-smart",
            model_returned=f"ollama/{model}",
            capsule_sha256=VALID_CAPSULE_SHA,
            completion_sha256=VALID_COMPLETION_SHA,
            tokens=100,
            status=200,
        )
        assert result.passed is True
        assert result.status == "VERIFIED"


def test_custom_verified_models_set() -> None:
    custom_set = {"custom-leaf-v1"}
    result = verify_dispatch(
        req_model="combo-smart",
        model_returned="provider/custom-leaf-v1",
        capsule_sha256=VALID_CAPSULE_SHA,
        completion_sha256=VALID_COMPLETION_SHA,
        tokens=100,
        status=200,
        verified_models=custom_set,
    )
    assert result.passed is True
    assert result.status == "VERIFIED"

    result_fail = verify_dispatch(
        req_model="combo-smart",
        model_returned="gpt-4o",
        capsule_sha256=VALID_CAPSULE_SHA,
        completion_sha256=VALID_COMPLETION_SHA,
        tokens=100,
        status=200,
        verified_models=custom_set,
    )
    assert result_fail.passed is False
    assert result_fail.status == "UNVERIFIABLE"

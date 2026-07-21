"""Dispatch Verifier — Pure deterministic validation of router dispatches.

Validates completion payloads, HTTP status, SHA256 hashes, token counts,
and model provenance against VERIFIED_MODELS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "VERIFIED_MODELS",
    "KNOWN_COMBO_ALIASES",
    "normalize_model_name",
    "DispatchVerificationResult",
    "verify_dispatch",
]

# Set of verified leaf model names
VERIFIED_MODELS: set[str] = {
    "qwen2.5:7b-instruct",
    "deepseek-r1:8b",
    "gpt-4o",
    "gemma3:4b",
    "llama-3.1-8b-instruct",
}

# Set of combo alias names that must resolve to a leaf model
KNOWN_COMBO_ALIASES: set[str] = {
    "combo-smart",
    "combo-fast",
    "combo-fallback",
    "combo-cheap",
}

_HEX_64_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")


def normalize_model_name(name: str | None) -> str:
    """Normalize model name by trimming whitespace, lowercasing, and stripping provider prefix."""
    if not name:
        return ""
    s = name.strip().lower()
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    return s


@dataclass(frozen=True)
class DispatchVerificationResult:
    passed: bool
    status: str  # "VERIFIED", "UNVERIFIABLE", "INTEGRITY_ERROR", "EMPTY_RESPONSE", "HTTP_ERROR"
    reason: str
    req_model: str
    model_returned: str
    tokens: int
    http_status: int


def verify_dispatch(
    *,
    req_model: str,
    model_returned: str | None,
    capsule_sha256: str | None,
    completion_sha256: str | None,
    tokens: int,
    status: int = 200,
    verified_models: set[str] | None = None,
) -> DispatchVerificationResult:
    """Verify dispatch payload integrity, HTTP status, token counts, and model provenance."""
    # 1. HTTP Status check
    if status != 200:
        return DispatchVerificationResult(
            passed=False,
            status="HTTP_ERROR",
            reason=f"HTTP status code {status} != 200",
            req_model=req_model,
            model_returned=model_returned or "",
            tokens=tokens,
            http_status=status,
        )

    # 2. Token count check
    if tokens <= 0:
        return DispatchVerificationResult(
            passed=False,
            status="EMPTY_RESPONSE",
            reason=f"Token count {tokens} <= 0",
            req_model=req_model,
            model_returned=model_returned or "",
            tokens=tokens,
            http_status=status,
        )

    # 3. Payload SHA256 integrity checks
    if not capsule_sha256 or not _HEX_64_REGEX.match(capsule_sha256):
        return DispatchVerificationResult(
            passed=False,
            status="INTEGRITY_ERROR",
            reason="Invalid or missing capsule_sha256 digest",
            req_model=req_model,
            model_returned=model_returned or "",
            tokens=tokens,
            http_status=status,
        )

    if not completion_sha256 or not _HEX_64_REGEX.match(completion_sha256):
        return DispatchVerificationResult(
            passed=False,
            status="INTEGRITY_ERROR",
            reason="Invalid or missing completion_sha256 digest",
            req_model=req_model,
            model_returned=model_returned or "",
            tokens=tokens,
            http_status=status,
        )

    # 4. Model returned normalization & unresolved combo check
    norm_returned = normalize_model_name(model_returned)

    if not norm_returned:
        return DispatchVerificationResult(
            passed=False,
            status="UNVERIFIABLE",
            reason="model_returned is empty or invalid",
            req_model=req_model,
            model_returned=model_returned or "",
            tokens=tokens,
            http_status=status,
        )

    # Check for unresolved combo alias
    normalized_combo_aliases = {normalize_model_name(c) for c in KNOWN_COMBO_ALIASES}
    if norm_returned in normalized_combo_aliases:
        return DispatchVerificationResult(
            passed=False,
            status="UNVERIFIABLE",
            reason=f"model_returned '{model_returned}' matches unresolved combo alias",
            req_model=req_model,
            model_returned=model_returned or "",
            tokens=tokens,
            http_status=status,
        )

    # 5. Provenance check against VERIFIED_MODELS (normalizing both sides)
    target_models = verified_models if verified_models is not None else VERIFIED_MODELS
    normalized_verified_set = {normalize_model_name(m) for m in target_models}

    if norm_returned not in normalized_verified_set:
        return DispatchVerificationResult(
            passed=False,
            status="UNVERIFIABLE",
            reason=f"Returned model '{model_returned}' (normalized: '{norm_returned}') is not in VERIFIED_MODELS",
            req_model=req_model,
            model_returned=model_returned or "",
            tokens=tokens,
            http_status=status,
        )

    # All checks passed
    return DispatchVerificationResult(
        passed=True,
        status="VERIFIED",
        reason="Dispatch verification successful",
        req_model=req_model,
        model_returned=model_returned or "",
        tokens=tokens,
        http_status=status,
    )

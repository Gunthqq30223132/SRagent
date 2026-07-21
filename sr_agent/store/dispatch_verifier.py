"""Dispatch receipt verifier module."""

import hashlib
import json
import os
import re
import subprocess


VERIFIED_MODELS = {
    "kiro/claude-sonnet-4.5",
    "kr/claude-sonnet-4.5",
    "kiro/claude-sonnet-4.5-thinking",
    "kr/claude-sonnet-4.5-thinking",
}

MODEL_PREFIX_REGEX = re.compile(r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+$")


def normalize_model_name(raw_model: str) -> str:
    model = raw_model
    if model.startswith("kiro/"):
        model = "kr/" + model[len("kiro/"):]
    if model.endswith("-thinking"):
        model = model[:-len("-thinking")]
    return model


def get_target_file_content(task_id: str, repo_root: str, target_path: str = "tests/test_new_attempt_adversarial.py") -> bytes | None:
    candidate_paths = [
        os.path.join(repo_root, "..", "attempts", task_id, target_path),
        os.path.join(repo_root, "attempts", task_id, target_path),
        os.path.join(repo_root, target_path),
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    return f.read()
            except Exception:
                pass

    for git_ref in [
        f"attempt/{task_id}:{target_path}",
        f"HEAD:{target_path}",
    ]:
        proc = subprocess.run(["git", "show", git_ref], capture_output=True, cwd=repo_root)
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout

    return None


def verify_dispatch_receipt(task_id: str, repo_root: str = ".") -> tuple[bool, str]:
    """Verify dispatch receipt in .agents/traces/<task-id>/dispatch.jsonl against committed envelope."""
    trace_path = os.path.join(repo_root, ".agents", "traces", task_id, "dispatch.jsonl")

    if not os.path.exists(trace_path):
        return (False, f"FAIL: missing receipt file {trace_path}")

    try:
        with open(trace_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
    except Exception as e:
        return (False, f"FAIL: unable to read receipt file: {e}")

    if not lines:
        return (False, "FAIL: receipt file is empty")

    parsed_records = []
    for line_idx, line_str in enumerate(lines, 1):
        try:
            record = json.loads(line_str)
            if not isinstance(record, dict):
                return (False, f"FAIL: line {line_idx} is not a valid JSON object")
            parsed_records.append(record)
        except json.JSONDecodeError:
            return (False, f"FAIL: invalid JSON in receipt line {line_idx}")

    envelope_raw = None
    dispatch_file_path = os.path.join(repo_root, ".agents", "dispatch", f"{task_id}.md")
    if os.path.exists(dispatch_file_path):
        try:
            with open(dispatch_file_path, "rb") as f:
                envelope_raw = f.read()
        except Exception:
            pass

    if envelope_raw is None:
        for git_spec in [
            f"HEAD:.agents/dispatch/{task_id}.md",
            f"attempt/{task_id}:.agents/dispatch/{task_id}.md",
        ]:
            proc = subprocess.run(["git", "show", git_spec], capture_output=True, cwd=repo_root)
            if proc.returncode == 0 and proc.stdout:
                envelope_raw = proc.stdout
                break

    if not envelope_raw:
        return (False, f"FAIL: dispatch envelope not committed at HEAD:.agents/dispatch/{task_id}.md")

    expected_sha = hashlib.sha256(envelope_raw).hexdigest()[:12]
    envelope_text = envelope_raw.decode("utf-8", errors="replace")

    target_from_envelope = ""
    for line in envelope_text.splitlines():
        if line.strip().startswith("TARGET:"):
            target_from_envelope = line.split("TARGET:", 1)[1].strip()
            break
    normalized_target = normalize_model_name(target_from_envelope) if target_from_envelope else ""

    if target_from_envelope:
        if not MODEL_PREFIX_REGEX.match(target_from_envelope):
            return (
                False,
                "FAIL: target model missing provider prefix or is an unverified bare combo name",
            )
        if (
            target_from_envelope not in VERIFIED_MODELS
            and normalized_target not in VERIFIED_MODELS
        ):
            return (
                False,
                "FAIL: target model missing provider prefix or is an unverified bare combo name",
            )

    total_tokens = 0
    for record in parsed_records:
        capsule_sha = record.get("capsule_sha256")
        if capsule_sha != expected_sha:
            return (
                False,
                f"FAIL: capsule SHA mismatch (expected {expected_sha}, got {capsule_sha})",
            )

        target_path = record.get("target_path") or "tests/test_new_attempt_adversarial.py"
        target_content_bytes = get_target_file_content(task_id, repo_root, target_path)
        if target_content_bytes is None:
            return (
                False,
                f"FAIL: target file '{target_path}' not found in attempt/{task_id} or filesystem",
            )

        file_sha256 = hashlib.sha256(target_content_bytes).hexdigest()[:12]

        # 1. Verify completion_sha256
        rec_completion_sha = record.get("completion_sha256")
        if not rec_completion_sha or file_sha256 != rec_completion_sha:
            return (
                False,
                f"FAIL: completion_sha256 mismatch (expected {file_sha256}, got {rec_completion_sha})",
            )

        # 2. Verify Model Pin & Provider Prefix / Verified Models
        req_model = record.get("req_model") or record.get("model_requested") or ""
        target_model_raw = record.get("target_model_raw") or ""

        has_valid_prefix = bool(
            MODEL_PREFIX_REGEX.match(req_model) or MODEL_PREFIX_REGEX.match(target_model_raw)
        )
        if not has_valid_prefix:
            return (
                False,
                "FAIL: target model missing provider prefix or is an unverified bare combo name",
            )

        if target_from_envelope:
            raw_match = record.get("target_model_raw") == target_from_envelope
            req_match = (record.get("req_model") or record.get("model_requested")) == normalized_target
            if not (raw_match or req_match):
                return (
                    False,
                    f"FAIL: target model pin mismatch (envelope target '{target_from_envelope}', record raw '{record.get('target_model_raw')}', record req '{record.get('model_requested')}')",
                )

        is_verified_model = (
            req_model in VERIFIED_MODELS or target_model_raw in VERIFIED_MODELS
        )
        if not is_verified_model:
            return (
                False,
                "FAIL: target model missing provider prefix or is an unverified bare combo name",
            )

        model_returned = record.get("model_returned")
        if not model_returned:
            return (False, "FAIL: model_returned is empty")

        if normalized_target:
            base_target = normalized_target.split("/")[-1]
            if base_target not in model_returned:
                import sys
                sys.stderr.write(
                    f"Warning: model_returned '{model_returned}' diverges from base model '{base_target}'\n"
                )

        prompt_tokens = record.get("prompt_tokens", 0)
        if not isinstance(prompt_tokens, (int, float)) or prompt_tokens <= 0:
            return (False, f"FAIL: prompt_tokens must be > 0 (got {prompt_tokens})")

        completion_tokens = record.get("completion_tokens", 0)
        if not isinstance(completion_tokens, (int, float)) or completion_tokens <= 0:
            return (False, f"FAIL: completion_tokens must be > 0 (got {completion_tokens})")

        status_code = record.get("status_code")
        if status_code != 200:
            return (False, f"FAIL: status_code must be 200 (got {status_code})")

        line_total = record.get("total_tokens")
        if isinstance(line_total, (int, float)) and line_total > 0:
            total_tokens += int(line_total)
        else:
            total_tokens += int(prompt_tokens + completion_tokens)

    return (True, f"PASS: valid dispatch receipt with {total_tokens} tokens")

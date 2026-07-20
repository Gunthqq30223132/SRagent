"""Dispatch receipt verifier module."""

import hashlib
import json
import os
import subprocess


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

    git_spec = f"HEAD:.agents/dispatch/{task_id}.md"
    proc = subprocess.run(["git", "show", git_spec], capture_output=True, cwd=repo_root)

    if proc.returncode != 0:
        return (False, f"FAIL: dispatch envelope not committed at {git_spec}")

    expected_sha = hashlib.sha256(proc.stdout).hexdigest()[:12]

    total_tokens = 0
    for record in parsed_records:
        capsule_sha = record.get("capsule_sha256")
        if capsule_sha != expected_sha:
            return (
                False,
                f"FAIL: capsule SHA mismatch (expected {expected_sha}, got {capsule_sha})",
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

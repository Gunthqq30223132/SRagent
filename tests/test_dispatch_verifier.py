"""Unit tests for dispatch_verifier module."""

import hashlib
import json
import subprocess
from unittest.mock import patch
import pytest

from sr_agent.store.dispatch_verifier import verify_dispatch_receipt


def test_valid_dispatch_receipt_passes(tmp_path):
    task_id = "test-task-valid"
    envelope_content = b"Sample dispatch envelope content"
    expected_sha = hashlib.sha256(envelope_content).hexdigest()[:12]

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-20T15:15:00Z",
        "task_id": task_id,
        "capsule_sha256": expected_sha,
        "model_requested": "kr/claude-sonnet-4.5",
        "model_returned": "claude-sonnet-4.5",
        "prompt_tokens": 4000,
        "completion_tokens": 150,
        "total_tokens": 4150,
        "latency_ms": 1200,
        "status_code": 200,
    }
    jsonl_file.write_text(json.dumps(record) + "\n", encoding="utf-8")

    def mock_run(cmd, capture_output=False, cwd=None):
        if cmd[:2] == ["git", "show"] and cmd[2] == f"HEAD:.agents/dispatch/{task_id}.md":
            return subprocess.CompletedProcess(cmd, 0, stdout=envelope_content, stderr=b"")
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"Not found")

    with patch("subprocess.run", side_effect=mock_run):
        ok, msg = verify_dispatch_receipt(task_id, repo_root=str(tmp_path))

    assert ok is True
    assert msg == "PASS: valid dispatch receipt with 4150 tokens"


def test_missing_receipt_file_fails(tmp_path):
    task_id = "test-task-missing"
    ok, msg = verify_dispatch_receipt(task_id, repo_root=str(tmp_path))
    assert ok is False
    assert msg.startswith("FAIL:")
    assert "missing receipt file" in msg


def test_mismatched_capsule_sha_fails(tmp_path):
    task_id = "test-task-mismatch"
    envelope_content = b"Real envelope content"

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-20T15:15:00Z",
        "task_id": task_id,
        "capsule_sha256": "wrongsha1234",
        "model_requested": "kr/claude-sonnet-4.5",
        "model_returned": "claude-sonnet-4.5",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "latency_ms": 500,
        "status_code": 200,
    }
    jsonl_file.write_text(json.dumps(record) + "\n", encoding="utf-8")

    def mock_run(cmd, capture_output=False, cwd=None):
        if cmd[:2] == ["git", "show"] and cmd[2] == f"HEAD:.agents/dispatch/{task_id}.md":
            return subprocess.CompletedProcess(cmd, 0, stdout=envelope_content, stderr=b"")
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"Not found")

    with patch("subprocess.run", side_effect=mock_run):
        ok, msg = verify_dispatch_receipt(task_id, repo_root=str(tmp_path))

    assert ok is False
    assert msg.startswith("FAIL:")
    assert "capsule SHA mismatch" in msg


def test_zero_tokens_receipt_fails(tmp_path):
    task_id = "test-task-zero-tokens"
    envelope_content = b"Envelope content"
    expected_sha = hashlib.sha256(envelope_content).hexdigest()[:12]

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-20T15:15:00Z",
        "task_id": task_id,
        "capsule_sha256": expected_sha,
        "model_requested": "kr/claude-sonnet-4.5",
        "model_returned": "claude-sonnet-4.5",
        "prompt_tokens": 0,
        "completion_tokens": 50,
        "total_tokens": 50,
        "latency_ms": 500,
        "status_code": 200,
    }
    jsonl_file.write_text(json.dumps(record) + "\n", encoding="utf-8")

    def mock_run(cmd, capture_output=False, cwd=None):
        if cmd[:2] == ["git", "show"] and cmd[2] == f"HEAD:.agents/dispatch/{task_id}.md":
            return subprocess.CompletedProcess(cmd, 0, stdout=envelope_content, stderr=b"")
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"Not found")

    with patch("subprocess.run", side_effect=mock_run):
        ok, msg = verify_dispatch_receipt(task_id, repo_root=str(tmp_path))

    assert ok is False
    assert msg.startswith("FAIL:")
    assert "prompt_tokens must be > 0" in msg


def test_http_error_receipt_fails(tmp_path):
    task_id = "test-task-http-error"
    envelope_content = b"Envelope content"
    expected_sha = hashlib.sha256(envelope_content).hexdigest()[:12]

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-20T15:15:00Z",
        "task_id": task_id,
        "capsule_sha256": expected_sha,
        "model_requested": "kr/claude-sonnet-4.5",
        "model_returned": "claude-sonnet-4.5",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "latency_ms": 500,
        "status_code": 500,
    }
    jsonl_file.write_text(json.dumps(record) + "\n", encoding="utf-8")

    def mock_run(cmd, capture_output=False, cwd=None):
        if cmd[:2] == ["git", "show"] and cmd[2] == f"HEAD:.agents/dispatch/{task_id}.md":
            return subprocess.CompletedProcess(cmd, 0, stdout=envelope_content, stderr=b"")
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"Not found")

    with patch("subprocess.run", side_effect=mock_run):
        ok, msg = verify_dispatch_receipt(task_id, repo_root=str(tmp_path))

    assert ok is False
    assert msg.startswith("FAIL:")
    assert "status_code must be 200" in msg

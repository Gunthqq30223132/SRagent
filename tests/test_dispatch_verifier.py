"""Unit tests for dispatch_verifier module."""

import hashlib
import json
import subprocess
from unittest.mock import patch
import pytest

from sr_agent.verifier import verify_dispatch_receipt



def setup_target_patch_file(tmp_path, task_id, content=b"def test_foo(): pass\n"):
    target_file = tmp_path / "attempts" / task_id / "tests" / "test_new_attempt_adversarial.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_bytes(content)
    return hashlib.sha256(content).hexdigest()[:12]


def test_valid_dispatch_receipt_passes(tmp_path):
    task_id = "test-task-valid"
    envelope_content = b"TARGET: kiro/claude-sonnet-4.5-thinking\nSample dispatch envelope content"
    expected_capsule_sha = hashlib.sha256(envelope_content).hexdigest()[:12]
    expected_completion_sha = setup_target_patch_file(tmp_path, task_id)

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-20T15:15:00Z",
        "task_id": task_id,
        "capsule_sha256": expected_capsule_sha,
        "completion_sha256": expected_completion_sha,
        "model_requested": "kr/claude-sonnet-4.5",
        "target_model_raw": "kiro/claude-sonnet-4.5-thinking",
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


def test_completion_sha256_mismatch_fails(tmp_path):
    task_id = "test-task-sha-mismatch"
    envelope_content = b"TARGET: kiro/claude-sonnet-4.5-thinking\nEnvelope content"
    expected_capsule_sha = hashlib.sha256(envelope_content).hexdigest()[:12]
    setup_target_patch_file(tmp_path, task_id)

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-20T15:15:00Z",
        "task_id": task_id,
        "capsule_sha256": expected_capsule_sha,
        "completion_sha256": "wrongsha1234",
        "model_requested": "kr/claude-sonnet-4.5",
        "target_model_raw": "kiro/claude-sonnet-4.5-thinking",
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
    assert "completion_sha256 mismatch" in msg


def test_target_model_pin_mismatch_fails(tmp_path):
    task_id = "test-task-model-mismatch"
    envelope_content = b"TARGET: kiro/claude-sonnet-4.5-thinking\nEnvelope content"
    expected_capsule_sha = hashlib.sha256(envelope_content).hexdigest()[:12]
    expected_completion_sha = setup_target_patch_file(tmp_path, task_id)

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-20T15:15:00Z",
        "task_id": task_id,
        "capsule_sha256": expected_capsule_sha,
        "completion_sha256": expected_completion_sha,
        "model_requested": "kr/wrong-model",
        "target_model_raw": "wrong/model-thinking",
        "model_returned": "wrong-model",
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
    assert "target model pin mismatch" in msg


def test_missing_receipt_file_fails(tmp_path):
    task_id = "test-task-missing"
    ok, msg = verify_dispatch_receipt(task_id, repo_root=str(tmp_path))
    assert ok is False
    assert msg.startswith("FAIL:")
    assert "missing receipt file" in msg


def test_mismatched_capsule_sha_fails(tmp_path):
    task_id = "test-task-mismatch"
    envelope_content = b"TARGET: kiro/claude-sonnet-4.5-thinking\nReal envelope content"
    expected_completion_sha = setup_target_patch_file(tmp_path, task_id)

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-20T15:15:00Z",
        "task_id": task_id,
        "capsule_sha256": "wrongsha1234",
        "completion_sha256": expected_completion_sha,
        "model_requested": "kr/claude-sonnet-4.5",
        "target_model_raw": "kiro/claude-sonnet-4.5-thinking",
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
    envelope_content = b"TARGET: kiro/claude-sonnet-4.5-thinking\nEnvelope content"
    expected_sha = hashlib.sha256(envelope_content).hexdigest()[:12]
    expected_completion_sha = setup_target_patch_file(tmp_path, task_id)

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-20T15:15:00Z",
        "task_id": task_id,
        "capsule_sha256": expected_sha,
        "completion_sha256": expected_completion_sha,
        "model_requested": "kr/claude-sonnet-4.5",
        "target_model_raw": "kiro/claude-sonnet-4.5-thinking",
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
    envelope_content = b"TARGET: kiro/claude-sonnet-4.5-thinking\nEnvelope content"
    expected_sha = hashlib.sha256(envelope_content).hexdigest()[:12]
    expected_completion_sha = setup_target_patch_file(tmp_path, task_id)

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-20T15:15:00Z",
        "task_id": task_id,
        "capsule_sha256": expected_sha,
        "completion_sha256": expected_completion_sha,
        "model_requested": "kr/claude-sonnet-4.5",
        "target_model_raw": "kiro/claude-sonnet-4.5-thinking",
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


def test_bare_unprefixed_combo_name_fails(tmp_path):
    task_id = "test-task-bare-combo"
    envelope_content = b"TARGET: claude-sonnet-4.5\nEnvelope content"
    expected_capsule_sha = hashlib.sha256(envelope_content).hexdigest()[:12]
    expected_completion_sha = setup_target_patch_file(tmp_path, task_id)

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-20T15:15:00Z",
        "task_id": task_id,
        "capsule_sha256": expected_capsule_sha,
        "completion_sha256": expected_completion_sha,
        "provider": "",
        "req_model": "claude-sonnet-4.5",
        "model_requested": "claude-sonnet-4.5",
        "target_model_raw": "claude-sonnet-4.5",
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
    assert msg == "FAIL: target model missing provider prefix or is an unverified bare combo name"


def test_valid_provider_prefixed_leaf_model_passes(tmp_path):
    task_id = "test-task-leaf-valid"
    envelope_content = b"TARGET: kiro/claude-sonnet-4.5\nSample dispatch envelope content"
    expected_capsule_sha = hashlib.sha256(envelope_content).hexdigest()[:12]
    expected_completion_sha = setup_target_patch_file(tmp_path, task_id)

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-20T15:15:00Z",
        "task_id": task_id,
        "capsule_sha256": expected_capsule_sha,
        "completion_sha256": expected_completion_sha,
        "provider": "kiro",
        "req_model": "kr/claude-sonnet-4.5",
        "model_requested": "kr/claude-sonnet-4.5",
        "target_model_raw": "kiro/claude-sonnet-4.5",
        "model_returned": "claude-sonnet-4.5",
        "prompt_tokens": 1000,
        "completion_tokens": 100,
        "total_tokens": 1100,
        "latency_ms": 800,
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
    assert msg == "PASS: valid dispatch receipt with 1100 tokens"


def test_dynamic_target_path_file_a_passes(tmp_path):
    task_id = "test-task-file-a"
    envelope_content = b"TARGET: kr/claude-sonnet-4.5\nEnvelope content"
    expected_capsule_sha = hashlib.sha256(envelope_content).hexdigest()[:12]
    
    # Create target file A at tools/custom_tool_a.py
    file_a = tmp_path / "attempts" / task_id / "tools" / "custom_tool_a.py"
    file_a.parent.mkdir(parents=True, exist_ok=True)
    content_a = b"print('Hello from tool A')\n"
    file_a.write_bytes(content_a)
    expected_sha_a = hashlib.sha256(content_a).hexdigest()[:12]

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-21T10:00:00Z",
        "task_id": task_id,
        "capsule_sha256": expected_capsule_sha,
        "completion_sha256": expected_sha_a,
        "target_path": "tools/custom_tool_a.py",
        "model_requested": "kr/claude-sonnet-4.5",
        "target_model_raw": "kr/claude-sonnet-4.5",
        "model_returned": "claude-sonnet-4.5",
        "prompt_tokens": 500,
        "completion_tokens": 100,
        "total_tokens": 600,
        "latency_ms": 400,
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
    assert msg == "PASS: valid dispatch receipt with 600 tokens"


def test_dynamic_target_path_file_b_passes_without_code_changes(tmp_path):
    task_id = "test-task-file-b"
    envelope_content = b"TARGET: kr/claude-sonnet-4.5\nEnvelope content"
    expected_capsule_sha = hashlib.sha256(envelope_content).hexdigest()[:12]

    # Create target file B at sr_agent/submodule/file_b.py
    file_b = tmp_path / "attempts" / task_id / "sr_agent" / "submodule" / "file_b.py"
    file_b.parent.mkdir(parents=True, exist_ok=True)
    content_b = b"class ComponentB:\n    pass\n"
    file_b.write_bytes(content_b)
    expected_sha_b = hashlib.sha256(content_b).hexdigest()[:12]

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-21T10:00:00Z",
        "task_id": task_id,
        "capsule_sha256": expected_capsule_sha,
        "completion_sha256": expected_sha_b,
        "target_path": "sr_agent/submodule/file_b.py",
        "model_requested": "kr/claude-sonnet-4.5",
        "target_model_raw": "kr/claude-sonnet-4.5",
        "model_returned": "claude-sonnet-4.5",
        "prompt_tokens": 600,
        "completion_tokens": 150,
        "total_tokens": 750,
        "latency_ms": 450,
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
    assert msg == "PASS: valid dispatch receipt with 750 tokens"


def test_nonexistent_target_path_fails(tmp_path):
    task_id = "test-task-nonexistent"
    envelope_content = b"TARGET: kr/claude-sonnet-4.5\nEnvelope content"
    expected_capsule_sha = hashlib.sha256(envelope_content).hexdigest()[:12]

    trace_dir = tmp_path / ".agents" / "traces" / task_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = trace_dir / "dispatch.jsonl"

    record = {
        "timestamp": "2026-07-21T10:00:00Z",
        "task_id": task_id,
        "capsule_sha256": expected_capsule_sha,
        "completion_sha256": "abcdef123456",
        "target_path": "nonexistent/path/to/missing_file.py",
        "model_requested": "kr/claude-sonnet-4.5",
        "target_model_raw": "kr/claude-sonnet-4.5",
        "model_returned": "claude-sonnet-4.5",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "latency_ms": 200,
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
    assert "nonexistent/path/to/missing_file.py" in msg or "not found" in msg



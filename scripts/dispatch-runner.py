#!/usr/bin/env python3
"""Dispatch runner for SRagent tasks (Tier 3 execution engine via 9router)."""

import argparse
import datetime
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request


def get_git_repo_root() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if proc.returncode != 0:
        sys.stderr.write("Error: Not inside a git repository.\n")
        sys.exit(1)
    return proc.stdout.strip()


def get_committed_capsule_sha256(repo_root: str, task_id: str, envelope_path: str) -> str:
    # Resolve envelope path relative to repo root
    abs_envelope = os.path.abspath(envelope_path)
    rel_envelope = os.path.relpath(abs_envelope, repo_root)
    git_spec = f"HEAD:{rel_envelope}"

    proc = subprocess.run(["git", "show", git_spec], capture_output=True, cwd=repo_root)
    if proc.returncode != 0:
        sys.stderr.write(f"Error: Dispatch envelope '{rel_envelope}' is not committed at HEAD.\n")
        sys.exit(1)

    return hashlib.sha256(proc.stdout).hexdigest()[:12]


def get_9router_api_key() -> str:
    db_path = os.path.expanduser("~/.9router/db/data.sqlite")
    if not os.path.exists(db_path):
        sys.stderr.write(f"Error: 9router database not found at {db_path}\n")
        sys.exit(1)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT key FROM apiKeys LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if not row or not row[0]:
            sys.stderr.write("Error: No API key found in 9router sqlite DB.\n")
            sys.exit(1)
        return row[0]
    except Exception as e:
        sys.stderr.write(f"Error reading 9router API key: {e}\n")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="SRagent Dispatch Runner")
    parser.add_argument("--task-id", required=True, help="Task ID (e.g. m107-first-light)")
    parser.add_argument(
        "--envelope",
        help="Path to dispatch envelope md file (defaults to .agents/dispatch/<task-id>.md)",
    )
    args = parser.parse_args()

    task_id = args.task_id
    envelope_path = args.envelope if args.envelope else f".agents/dispatch/{task_id}.md"

    repo_root = get_git_repo_root()
    capsule_sha256 = get_committed_capsule_sha256(repo_root, task_id, envelope_path)
    api_key = get_9router_api_key()

    if not os.path.exists(envelope_path):
        sys.stderr.write(f"Error: Envelope file non-existent at '{envelope_path}'.\n")
        sys.exit(1)

    with open(envelope_path, "r", encoding="utf-8") as f:
        envelope_content = f.read()

    model_requested = "kr/claude-sonnet-4.5"
    url = "http://localhost:20128/v1/chat/completions"
    payload = {
        "model": model_requested,
        "stream": True,
        "messages": [{"role": "user", "content": envelope_content}],
        "stream_options": {"include_usage": True},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )

    start_time = time.perf_counter()
    model_returned = ""
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    completion_text_parts = []
    status_code = 200

    try:
        with urllib.request.urlopen(req) as resp:
            status_code = resp.status
            for line in resp:
                line_str = line.decode("utf-8").strip()
                if not line_str or not line_str.startswith("data: "):
                    continue
                data_content = line_str[6:].strip()
                if data_content == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_content)
                except json.JSONDecodeError:
                    continue

                if chunk.get("model"):
                    model_returned = chunk["model"]

                choices = chunk.get("choices", [])
                if choices and isinstance(choices, list) and len(choices) > 0:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        completion_text_parts.append(content)

                if chunk.get("usage"):
                    u = chunk["usage"]
                    prompt_tokens = u.get("prompt_tokens", prompt_tokens)
                    completion_tokens = u.get("completion_tokens", completion_tokens)
                    total_tokens = u.get("total_tokens", total_tokens)
    except urllib.error.HTTPError as e:
        status_code = e.code
        sys.stderr.write(f"HTTP Error {e.code}: {e.reason}\n")
    except Exception as e:
        sys.stderr.write(f"Request error: {e}\n")
        sys.exit(1)

    latency_ms = int((time.perf_counter() - start_time) * 1000)
    if total_tokens == 0 and (prompt_tokens > 0 or completion_tokens > 0):
        total_tokens = prompt_tokens + completion_tokens
    if not model_returned:
        model_returned = model_requested

    # Ensure trace directory exists
    trace_dir = os.path.join(repo_root, ".agents", "traces", task_id)
    os.makedirs(trace_dir, exist_ok=True)
    dispatch_jsonl_path = os.path.join(trace_dir, "dispatch.jsonl")

    utc_now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {
        "timestamp": utc_now,
        "task_id": task_id,
        "capsule_sha256": capsule_sha256,
        "model_requested": model_requested,
        "model_returned": model_returned,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "latency_ms": latency_ms,
        "status_code": status_code,
    }

    with open(dispatch_jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    completion_text = "".join(completion_text_parts)
    sys.stdout.write(completion_text + ("\n" if not completion_text.endswith("\n") else ""))

    if status_code != 200:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

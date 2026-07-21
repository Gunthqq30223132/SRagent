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


def get_committed_envelope_data(repo_root: str, task_id: str, envelope_path: str) -> tuple[bytes, str]:
    # Resolve envelope path relative to repo root
    abs_envelope = os.path.abspath(envelope_path)
    rel_envelope = os.path.relpath(abs_envelope, repo_root)
    git_spec = f"HEAD:{rel_envelope}"

    proc = subprocess.run(["git", "show", git_spec], capture_output=True, cwd=repo_root)
    if proc.returncode != 0:
        sys.stderr.write(f"Error: Dispatch envelope '{rel_envelope}' is not committed at HEAD.\n")
        sys.exit(1)

    return proc.stdout, hashlib.sha256(proc.stdout).hexdigest()[:12]


def normalize_model_name(raw_model: str) -> str:
    model = raw_model
    if model.startswith("kiro/"):
        model = "kr/" + model[len("kiro/"):]
    if model.endswith("-thinking"):
        model = model[:-len("-thinking")]
    return model


def extract_code_block(text: str) -> str:
    import re
    pattern = r"```(?:python)?\s*\n?(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    return text


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
    envelope_bytes, capsule_sha256 = get_committed_envelope_data(repo_root, task_id, envelope_path)
    api_key = get_9router_api_key()

    if not os.path.exists(envelope_path):
        sys.stderr.write(f"Error: Envelope file non-existent at '{envelope_path}'.\n")
        sys.exit(1)

    with open(envelope_path, "r", encoding="utf-8") as f:
        envelope_content = f.read()

    envelope_text = envelope_bytes.decode("utf-8", errors="replace")
    target_model_raw = "kiro/claude-sonnet-4.5-thinking"
    for line in envelope_text.splitlines():
        if line.strip().startswith("TARGET:"):
            target_model_raw = line.split("TARGET:", 1)[1].strip()
            break

    model_requested = normalize_model_name(target_model_raw)
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

    completion_text = "".join(completion_text_parts)
    completion_sha256 = ""
    if completion_text:
        import re
        write_match = re.search(r"<write_file>\s*<path>(.*?)</path>\s*<contents>(.*?)</contents>", completion_text, re.DOTALL)
        if write_match:
            rel_target_path = write_match.group(1).strip()
            extracted_code = write_match.group(2)
            if extracted_code.startswith("\n"):
                extracted_code = extracted_code[1:]
        else:
            extracted_code = extract_code_block(completion_text)
            path_match = re.search(r"<path>(.*?)</path>", completion_text)
            rel_target_path = path_match.group(1).strip() if path_match else os.path.join("tests", "test_new_attempt_adversarial.py")

        if os.path.basename(repo_root) == task_id or "/attempts/" in repo_root:
            target_file_path = os.path.join(repo_root, rel_target_path)
        else:
            target_file_path = os.path.join(
                os.path.dirname(repo_root), "attempts", task_id, rel_target_path
            )

        os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
        with open(target_file_path, "w", encoding="utf-8") as f:
            f.write(extracted_code)
        with open(target_file_path, "rb") as f:
            written_bytes = f.read()
        completion_sha256 = hashlib.sha256(written_bytes).hexdigest()[:12]

    # Ensure trace directory exists
    trace_dir = os.path.join(repo_root, ".agents", "traces", task_id)
    os.makedirs(trace_dir, exist_ok=True)
    dispatch_jsonl_path = os.path.join(trace_dir, "dispatch.jsonl")

    provider = target_model_raw.split("/", 1)[0] if "/" in target_model_raw else ""
    req_model = model_requested

    utc_now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {
        "timestamp": utc_now,
        "task_id": task_id,
        "capsule_sha256": capsule_sha256,
        "completion_sha256": completion_sha256,
        "provider": provider,
        "req_model": req_model,
        "model_requested": model_requested,
        "target_model_raw": target_model_raw,
        "model_returned": model_returned,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "latency_ms": latency_ms,
        "status_code": status_code,
    }

    with open(dispatch_jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    sys.stdout.write(completion_text + ("\n" if not completion_text.endswith("\n") else ""))

    if status_code != 200:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

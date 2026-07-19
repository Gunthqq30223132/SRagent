#!/usr/bin/env bash
set -euo pipefail

# 0. Resolve Repo & Anchor info
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

OWNER_REPO=$(git remote get-url origin 2>/dev/null | sed -E 's/.*github\.com[:\/](.+)\.git/\1/' || echo "Unknown/Repo")
BRANCH=$(git branch --show-current 2>/dev/null || echo "detached")
HEAD_SHA=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
CWD=$(pwd)

echo "================================================================================"
echo "preflight: repo: $OWNER_REPO | branch: $BRANCH | HEAD: $HEAD_SHA | cwd: $CWD"
echo "================================================================================"

# 1. Tree Status Check
DIRTY_COUNT=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
if [ "$DIRTY_COUNT" -eq 0 ]; then
  echo "✅ Working tree: CLEAN"
else
  echo "⚠️ Working tree: DIRTY ($DIRTY_COUNT uncommitted/untracked files)"
fi

# 2. GitHub CLI Auth Check
echo -n "Checking GitHub CLI status... "
if gh auth status >/dev/null 2>&1; then
  echo "✅ Logged in"
else
  echo "⚠️ Unauthenticated (gh auth login required for PR/Issue CLI ops)"
fi

# 3. 9router Liveness & Model Pin Checks
echo "--------------------------------------------------------------------------------"
echo "Checking 9router Gateway (:20128) & Pinned Models..."

python3 - << 'EOF'
import os
import sys
import json
import sqlite3
import urllib.request
import urllib.error

url = "http://127.0.0.1:20128/v1/chat/completions"

def get_api_key():
    env_key = os.environ.get("ROUTER_API_KEY") or os.environ.get("NINEROUTER_API_KEY")
    if env_key: return env_key
    for p in ["~/.omniroute/db/data.sqlite", "~/.9router/db/data.sqlite"]:
        full = os.path.expanduser(p)
        if os.path.exists(full):
            try:
                conn = sqlite3.connect(full)
                cur = conn.cursor()
                cur.execute("SELECT key FROM apiKeys LIMIT 1")
                row = cur.fetchone()
                conn.close()
                if row and row[0]: return row[0]
            except Exception: pass
    return None

api_key = get_api_key()
if not api_key:
    print("❌ 9router Key Check: FAILED (ROUTER_API_KEY not found in env or SQLite)")
    sys.exit(1)

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"
}

def test_model(model_name, prompt="Hi"):
    payload = json.dumps({
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 256
    }).encode('utf-8')
    
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            if resp.status == 200:
                res_body = json.loads(resp.read().decode('utf-8'))
                choice = res_body.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "").strip()
                finish_reason = choice.get("finish_reason", "")
                
                if content and finish_reason == "stop":
                    print(f"✅ Model [{model_name}]: PASS (content length={len(content)}, finish_reason={finish_reason})")
                    return True
                else:
                    print(f"❌ Model [{model_name}]: FAIL (content='{content}', finish_reason='{finish_reason}')")
                    return False
            else:
                print(f"❌ Model [{model_name}]: FAIL (HTTP status={resp.status})")
                return False
    except Exception as e:
        print(f"❌ Model [{model_name}]: ERROR ({e})")
        return False

# Test both pinned models
m1_ok = test_model("kiro/claude-sonnet-4.5-thinking")
m2_ok = test_model("ollama-local/gemma4:e4b")

if m1_ok and m2_ok:
    print("✅ 9router Gateway & Pinned Models: ALL VERIFIED")
    sys.exit(0)
else:
    print("⚠️ 9router Gateway Check: ONE OR MORE MODELS FAILED")
    sys.exit(1)
EOF

echo "================================================================================"

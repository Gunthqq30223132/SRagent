#!/usr/bin/env python3
import os
import sys
import json
import sqlite3
import httpx

# 9router local endpoint
url = "http://127.0.0.1:20128/v1/chat/completions"

def get_api_key():
    env_key = os.environ.get("ROUTER_API_KEY") or os.environ.get("NINEROUTER_API_KEY")
    if env_key:
        return env_key
    
    for path in ["~/.omniroute/db/data.sqlite", "~/.9router/db/data.sqlite"]:
        full = os.path.expanduser(path)
        if os.path.exists(full):
            try:
                conn = sqlite3.connect(full)
                cur = conn.cursor()
                cur.execute("SELECT key FROM apiKeys LIMIT 1")
                row = cur.fetchone()
                conn.close()
                if row and row[0]:
                    return row[0]
            except Exception:
                pass
    return None

api_key = get_api_key()
if not api_key:
    print("[-] Error: ROUTER_API_KEY not found in environment or 9router SQLite DB.", file=sys.stderr)
    sys.exit(1)

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

def test_model(model_name, prompt):
    print(f"\n=== Testing Model: {model_name} ===")
    data = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 50
    }
    try:
        response = httpx.post(url, headers=headers, json=data, timeout=30.0)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"].get("content", "")
            print(f"Response: {content.strip()}")
            return True if content.strip() else False
        else:
            print(f"Error Response: {response.text}")
            return False
    except Exception as e:
        print(f"Exception: {e}")
        return False

if __name__ == "__main__":
    print("Starting 9router Smoke Test...")
    # Test Ollama local
    ollama_ok = test_model("ollama-local/gemma4:e4b", "Say hello in 3 words.")
    
    # Test Kiro cloud
    kiro_ok = test_model("kiro/claude-sonnet-4.5-thinking", "Say hello in 3 words.")
    
    if ollama_ok and kiro_ok:
        print("\n✅ Smoke test PASSED: Both Ollama and Kiro responded successfully.")
        sys.exit(0)
    else:
        print("\n❌ Smoke test FAILED.")
        sys.exit(1)


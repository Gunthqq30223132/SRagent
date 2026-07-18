#!/usr/bin/env python3
import os
import sys
import json
import httpx

# 9router local endpoint
url = "http://127.0.0.1:20128/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer sk-faf1396b6e07c367-gr1o31-f6762b4a"
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
            content = result["choices"][0]["message"]["content"]
            print(f"Response: {content.strip()}")
            return True
        else:
            print(f"Error Response: {response.text}")
            return False
    except Exception as e:
        print(f"Exception: {e}")
        return False

if __name__ == "__main__":
    print("Starting 9router Smoke Test...")
    # Test Ollama local
    ollama_ok = test_model("ollama/qwen2.5:7b-instruct", "Say hello in 3 words.")
    
    # Test Kiro cloud
    kiro_ok = test_model("kiro/claude-sonnet-5", "Say hello in 3 words.")
    
    if ollama_ok and kiro_ok:
        print("\n✅ Smoke test PASSED: Both Ollama and Kiro responded successfully.")
        sys.exit(0)
    else:
        print("\n❌ Smoke test FAILED.")
        sys.exit(1)

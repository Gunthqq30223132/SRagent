#!/usr/bin/env python3
"""scripts/refresh_catalog.py
Fetch available models from OmniRoute and merge them into ~/.config/opencode/opencode.json.
"""

import os
import sys
import json
import urllib.request
import urllib.error
import tempfile

def load_opencode_config(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[!] Warning: failed to parse {path}, starting fresh: {e}")
        return {}

def save_opencode_config_atomic(path: str, config: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    dir_name = os.path.dirname(path)
    fd, temp_path = tempfile.mkstemp(dir=dir_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        os.replace(temp_path, path)
    except Exception as e:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise e

def main() -> int:
    omniroute_url = "http://localhost:20128/v1/models"
    config_path = os.path.expanduser("~/.config/opencode/opencode.json")
    
    print(f"[*] Fetching active model list from OmniRoute at {omniroute_url}...")
    try:
        req = urllib.request.Request(omniroute_url, headers={"User-Agent": "AnesthOS-Catalog-Refresher"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"[ERROR] Failed to connect to OmniRoute: {e}", file=sys.stderr)
        print("[*] Make sure OmniRoute is running. Run 'setup_anesthos_ai.sh' first.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[ERROR] Unexpected error while fetching models: {e}", file=sys.stderr)
        return 1

    # Extract model names
    model_ids = []
    # Standard OpenAI models endpoint returns {"object": "list", "data": [{"id": "model-name", ...}]}
    if isinstance(data, dict) and "data" in data:
        for item in data["data"]:
            if isinstance(item, dict) and "id" in item:
                model_ids.append(item["id"])
            elif isinstance(item, str):
                model_ids.append(item)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "id" in item:
                model_ids.append(item["id"])
            elif isinstance(item, str):
                model_ids.append(item)
    else:
        print(f"[ERROR] Unrecognized models catalog format: {data}", file=sys.stderr)
        return 1
        
    if not model_ids:
        print("[WARNING] OmniRoute returned an empty model list.")
        return 0

    print(f"[+] Fetched {len(model_ids)} models from OmniRoute: {model_ids}")

    # Load existing opencode.json
    config = load_opencode_config(config_path)
    
    # Initialize basic structure if not exists
    if "$schema" not in config:
        config["$schema"] = "https://opencode.ai/config.json"
    if "provider" not in config:
        config["provider"] = {}
    if "9router" not in config["provider"]:
        config["provider"]["9router"] = {}
    
    router = config["provider"]["9router"]
    if "npm" not in router:
        router["npm"] = "@ai-sdk/openai-compatible"
    if "options" not in router:
        router["options"] = {
            "baseURL": "http://127.0.0.1:20128/v1",
            "apiKey": "sk-faf1396b6e07c367-gr1o31-f6762b4a"
        }
    if "models" not in router:
        router["models"] = {}
        
    existing_models = router["models"]
    
    # Modality defaults
    default_modalities = {
        "input": ["text", "image"],
        "output": ["text"]
    }
    
    merged_count = 0
    # Merge fetched models
    for m_id in model_ids:
        if m_id not in existing_models:
            existing_models[m_id] = {
                "name": m_id,
                "modalities": default_modalities
            }
            merged_count += 1
            print(f"[+] Added new model: {m_id}")
        else:
            # Preserve existing modality mappings if they exist
            # but ensure name is set
            existing_models[m_id]["name"] = m_id
            if "modalities" not in existing_models[m_id]:
                existing_models[m_id]["modalities"] = default_modalities

    if merged_count > 0 or not os.path.exists(config_path):
        try:
            save_opencode_config_atomic(config_path, config)
            print(f"[+] Successfully merged {merged_count} new models into {config_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save updated config: {e}", file=sys.stderr)
            return 1
    else:
        print("[*] No new models to merge. Config is up-to-date.")
        
    return 0

if __name__ == "__main__":
    sys.exit(main())

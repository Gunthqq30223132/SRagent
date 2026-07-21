#!/usr/bin/env python3
"""
refresh_catalog.py — AnesthOS OpenCode Catalog Refresher
Fetches live model list from OmniRoute and regenerates ~/.config/opencode/opencode.json
so that OpenCode always shows only healthy, available models.

Usage:
  python3 refresh_catalog.py [--dry-run]

  --dry-run   Print the generated config without writing to disk.
"""

import json
import sys
import os
import urllib.request
import urllib.error
from pathlib import Path

OMNIROUTE_BASE = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128")
OPENCODE_CONFIG = Path.home() / ".config" / "opencode" / "opencode.json"
PROVIDER_KEY = "9router"

# Models that are always included regardless of live status
ALWAYS_INCLUDE = ["anesthos-brain"]

# Default modalities for all chat models
DEFAULT_MODALITIES = {
    "input": ["text", "image"],
    "output": ["text"]
}


def fetch_live_models():
    """Fetch /v1/models from OmniRoute and return list of model IDs."""
    url = f"{OMNIROUTE_BASE}/v1/models"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return [m["id"] for m in data.get("data", []) if isinstance(m.get("id"), str)]
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
        print(f"⚠ Could not fetch models from OmniRoute: {e}", file=sys.stderr)
        return []


def load_existing_config():
    """Load current opencode.json or return a minimal skeleton."""
    if OPENCODE_CONFIG.exists():
        try:
            return json.loads(OPENCODE_CONFIG.read_text())
        except json.JSONDecodeError:
            pass
    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {},
        "model": f"{PROVIDER_KEY}/anesthos-brain"
    }


def build_model_entry(model_id):
    """Build an OpenCode model entry dict."""
    return {
        "name": model_id,
        "modalities": DEFAULT_MODALITIES
    }


def refresh(dry_run=False):
    print("🔄 Fetching live model catalog from OmniRoute...", file=sys.stderr)
    live_models = fetch_live_models()

    if not live_models:
        print("⚠ No models returned from OmniRoute. Keeping existing config.", file=sys.stderr)
        sys.exit(0)

    # Merge: always-include first, then live models (deduped, preserve order)
    seen = set()
    ordered = []
    for mid in ALWAYS_INCLUDE + live_models:
        if mid not in seen:
            seen.add(mid)
            ordered.append(mid)

    config = load_existing_config()

    # Rebuild the provider models section
    config.setdefault("provider", {})
    config["provider"][PROVIDER_KEY] = config["provider"].get(PROVIDER_KEY, {})
    provider = config["provider"][PROVIDER_KEY]

    # Keep existing provider-level options (baseURL, apiKey, npm)
    # Only replace the models dict
    provider["models"] = {mid: build_model_entry(mid) for mid in ordered}

    # Set default model to anesthos-brain if not already set or if stale
    current_default = config.get("model", "")
    if not current_default or current_default.split("/", 1)[-1] not in seen:
        config["model"] = f"{PROVIDER_KEY}/anesthos-brain"

    output = json.dumps(config, indent=2, ensure_ascii=False)

    if dry_run:
        print(output)
        return

    OPENCODE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    OPENCODE_CONFIG.write_text(output)
    print(f"✅ OpenCode catalog refreshed: {len(ordered)} models → {OPENCODE_CONFIG}", file=sys.stderr)
    for mid in ordered:
        marker = " ← default" if mid == "anesthos-brain" else ""
        print(f"   • {mid}{marker}", file=sys.stderr)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    refresh(dry_run=dry_run)

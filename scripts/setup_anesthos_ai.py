#!/usr/bin/env python3
import os
import sqlite3
import json
import sys
from datetime import datetime

def setup_omniroute_db():
    db_dir = os.path.expanduser("~/.omniroute")
    db_path = os.path.join(db_dir, "storage.sqlite")
    env_path = os.path.join(db_dir, ".env")
    
    print(f"[*] Configuring OmniRoute database at: {db_path}")
    
    # Ensure directory exists
    os.makedirs(db_dir, exist_ok=True)
    
    # Write OMNIROUTE_MAX_PENDING_MIGRATIONS=0 to .env to bypass safety checks permanently
    print(f"[*] Writing safety check bypass to {env_path}")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("OMNIROUTE_MAX_PENDING_MIGRATIONS=0\n")
    
    # Connect and initialize schema/data
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Create combos table if not exists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS combos (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        data TEXT NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    
    # Check if context_cache_protection column exists, add if missing
    cursor.execute("PRAGMA table_info(combos)")
    columns = [col[1] for col in cursor.fetchall()]
    has_ccp = "context_cache_protection" in columns
    if not has_ccp:
        try:
            cursor.execute("ALTER TABLE combos ADD COLUMN context_cache_protection INTEGER DEFAULT 0")
            has_ccp = True
            print("[+] Added context_cache_protection column to combos table.")
        except Exception as e:
            print(f"[!] Warning adding context_cache_protection: {e}")
            
    # 2. Insert or replace the 'anesthos-brain' combo model
    now = datetime.utcnow().isoformat() + "Z"
    combo_data = {
        "id": "anesthos-brain",
        "name": "anesthos-brain",
        "models": ["kr/claude-sonnet-4.5", "ag/claude-sonnet-4-6", "ag/gemini-2.5-pro"],
        "strategy": "priority",
        "config": {},
        "isHidden": False,
        "sortOrder": 1,
        "createdAt": now,
        "updatedAt": now,
        "context_cache_protection": False
    }
    
    if has_ccp:
        cursor.execute("""
        INSERT OR REPLACE INTO combos (id, name, data, sort_order, created_at, updated_at, context_cache_protection)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "anesthos-brain",
            "anesthos-brain",
            json.dumps(combo_data),
            1,
            now,
            now,
            0
        ))
    else:
        cursor.execute("""
        INSERT OR REPLACE INTO combos (id, name, data, sort_order, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "anesthos-brain",
            "anesthos-brain",
            json.dumps(combo_data),
            1,
            now,
            now
        ))
    print("[+] Configured combo model 'anesthos-brain'.")
    
    # 3. Create key_value table if not exists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS key_value (
        namespace TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        PRIMARY KEY (namespace, key)
    )
    """)
    
    # Set 'anesthos-brain' as active combo
    cursor.execute("""
    INSERT OR REPLACE INTO key_value (namespace, key, value)
    VALUES ('settings', 'activeCombo', ?)
    """, (json.dumps("anesthos-brain"),))
    print("[+] Set 'anesthos-brain' as active combo.")
    
    conn.commit()
    conn.close()
    print("[+] OmniRoute database configuration complete.")

def setup_claude_profile():
    profile_dir = os.path.expanduser("~/.claude/profiles/anesthos")
    print(f"[*] Configuring Claude Code profile at: {profile_dir}")
    os.makedirs(profile_dir, exist_ok=True)
    
    # settings.json configuration
    settings_path = os.path.join(profile_dir, "settings.json")
    settings_data = {
        "env": {
            "ANTHROPIC_BASE_URL": "http://localhost:20128/v1",
            "ANTHROPIC_AUTH_TOKEN": "sk-anesthos-brain-token",
            "ANTHROPIC_DEFAULT_OPUS_MODEL": "anesthos-brain",
            "ANTHROPIC_DEFAULT_SONNET_MODEL": "anesthos-brain",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "anesthos-brain"
        },
        "model": "anesthos-brain",
        "theme": "auto",
        "hasCompletedOnboarding": True
    }
    
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings_data, f, indent=2)
    print(f"[+] Wrote settings.json: {settings_path}")
    
    # settings.local.json configuration (for workspace read permissions)
    local_settings_path = os.path.join(profile_dir, "settings.local.json")
    local_settings_data = {
        "permissions": {
            "allow": [
                "Read(//Volumes/**)",
                "Read(//Volumes/Gun SSD/**)",
                "WebFetch(domain:www.gmetrix.net)"
            ]
        }
    }
    
    with open(local_settings_path, "w", encoding="utf-8") as f:
        json.dump(local_settings_data, f, indent=2)
    print(f"[+] Wrote settings.local.json: {local_settings_path}")
    print("[+] Claude Code profile configuration complete.")

def setup_opencode_config():
    opencode_dir = os.path.expanduser("~/.config/opencode")
    opencode_path = os.path.join(opencode_dir, "opencode.json")
    print(f"[*] Configuring OpenCode configuration at: {opencode_path}")
    os.makedirs(opencode_dir, exist_ok=True)
    
    if os.path.exists(opencode_path):
        try:
            with open(opencode_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
    else:
        config = {}
        
    changed = False
    if "$schema" not in config:
        config["$schema"] = "https://opencode.ai/config.json"
        changed = True
        
    if "provider" not in config:
        config["provider"] = {}
        changed = True
        
    provider = config["provider"]
    if "9router" not in provider:
        provider["9router"] = {}
        changed = True
        
    router = provider["9router"]
    if "npm" not in router:
        router["npm"] = "@ai-sdk/openai-compatible"
        changed = True
        
    if "options" not in router:
        router["options"] = {}
        changed = True
        
    options = router["options"]
    if "baseURL" not in options:
        options["baseURL"] = "http://127.0.0.1:20128/v1"
        changed = True
    if "apiKey" not in options:
        options["apiKey"] = "sk-faf1396b6e07c367-gr1o31-f6762b4a"
        changed = True
        
    if "models" not in router:
        router["models"] = {}
        changed = True
        
    if "model" not in config:
        config["model"] = "9router/ag/gemini-3.1-pro-high"
        changed = True
        
    if changed:
        with open(opencode_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        print(f"[+] Initialized/updated opencode.json: {opencode_path}")
    else:
        print("[+] opencode.json is already valid.")

if __name__ == "__main__":
    try:
        setup_omniroute_db()
        setup_claude_profile()
        setup_opencode_config()
        print("[*] All configurations successfully written.")
    except Exception as e:
        print(f"[!] Error: {e}")
        sys.exit(1)

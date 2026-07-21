#!/usr/bin/env python3
import os
import sys
import sqlite3
import json
from datetime import datetime

db_path = os.path.expanduser("~/.9router/db/data.sqlite")

def setup_credentials(kiro_api_key):
    if not os.path.exists(db_path):
        print(f"[-] Error: 9router database not found at {db_path}")
        return False
        
    print(f"[*] Updating 9router database at {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    now = datetime.now().isoformat() + "Z"
    
    # 1. Update Kiro OAuth token directly inside the 'data' JSON string
    # Kiro OAuth expects accessToken in the data column. We also push expiresAt far into the future.
    cursor.execute("SELECT data FROM providerConnections WHERE provider = 'kiro'")
    row = cursor.fetchone()
    if row:
        kiro_data = json.loads(row[0])
    else:
        kiro_data = {}
        
    kiro_data["accessToken"] = kiro_api_key
    kiro_data["expiresAt"] = "2030-01-01T00:00:00.000Z" # Far future expiry
    kiro_data["testStatus"] = "active"
    kiro_data["lastUsedAt"] = now
    
    cursor.execute("""
        UPDATE providerConnections
        SET authType = 'oauth',
            data = ?,
            updatedAt = ?
        WHERE provider = 'kiro'
    """, (json.dumps(kiro_data), now))
    
    print("[+] Kiro API credentials updated in database.")
    
    # 2. Update Ollama local
    cursor.execute("SELECT data FROM providerConnections WHERE provider = 'ollama'")
    row = cursor.fetchone()
    if row:
        ollama_data = json.loads(row[0])
    else:
        ollama_data = {}
        
    ollama_data["apiKey"] = "" # Clear key if not needed
    ollama_data["testStatus"] = "active"
    ollama_data["lastUsedAt"] = now
    if "lastError" in ollama_data:
        del ollama_data["lastError"]
    if "errorCode" in ollama_data:
        del ollama_data["errorCode"]
        
    cursor.execute("""
        UPDATE providerConnections
        SET authType = 'apikey',
            data = ?,
            updatedAt = ?
        WHERE provider = 'ollama'
    """, (json.dumps(ollama_data), now))
    
    print("[+] Ollama connection reset to active (no auth).")
    
    conn.commit()
    conn.close()
    print("[+] 9router database updated successfully. Please restart 9router to apply.")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 setup_9router_credentials.py <KIRO_API_KEY>")
        sys.exit(1)
        
    kiro_key = sys.argv[1]
    if setup_credentials(kiro_key):
        sys.exit(0)
    else:
        sys.exit(1)

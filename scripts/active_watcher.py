#!/usr/bin/env python3
import os
import sys
import time
import json
import subprocess
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
STATUS_JSON = os.path.join(REPO_DIR, ".agents", "watcher_status.json")
BUILD_TXT = os.path.join(REPO_DIR, ".agents", "build_status.txt")
DIRTY_FILE = os.path.join(REPO_DIR, ".agents", ".dirty")

EXCLUDE_DIRS = {".git", ".venv", ".pytest_cache", "__pycache__", ".agents", "node_modules", "dist"}

def get_all_files():
    file_map = {}
    for root, dirs, files in os.walk(REPO_DIR):
        # Exclude directories in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for file in files:
            # Skip hidden files and python caches
            if file.startswith('.') or file.endswith('.pyc'):
                continue
            filepath = os.path.join(root, file)
            try:
                mtime = os.path.getmtime(filepath)
                file_map[filepath] = mtime
            except OSError:
                continue
    return file_map

def run_harness():
    print(f"[*] Change detected! Triggering QC harness at {datetime.now().isoformat()}...")
    
    # Write dirty flag to indicate active execution
    with open(DIRTY_FILE, "w") as f:
        f.write("RUNNING\n")
        
    process = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "agent-qc-harness.py")],
        cwd=REPO_DIR
    )
    
    # Remove dirty flag on completion
    if os.path.exists(DIRTY_FILE):
        os.remove(DIRTY_FILE)
        
    status_str = "PASS" if process.returncode == 0 else "FAIL"
    
    # Save status
    status_data = {
        "last_trigger": datetime.utcnow().isoformat() + "Z",
        "status": status_str
    }
    with open(STATUS_JSON, "w") as f:
        json.dump(status_data, f, indent=2)
        
    with open(BUILD_TXT, "w") as f:
        f.write(f"BUILD_STATUS: {status_str}\n")
        
    print(f"[+] Watcher cycle complete. Status: {status_str}\n")

def main():
    print(f"[*] Starting active watcher daemon in {REPO_DIR}...")
    print("[*] Monitoring files for changes (excluding venv, git, agents, etc.)")
    
    # Initial scan
    last_state = get_all_files()
    print(f"[+] Initial scan complete. Monitoring {len(last_state)} files.")
    
    try:
        while True:
            time.sleep(2)
            current_state = get_all_files()
            
            # Check for changes
            changed = False
            for path, mtime in current_state.items():
                if path not in last_state:
                    print(f"[*] New file: {os.path.basename(path)}")
                    changed = True
                elif last_state[path] < mtime:
                    print(f"[*] Modified file: {os.path.basename(path)}")
                    changed = True
                    
            for path in list(last_state.keys()):
                if path not in current_state:
                    print(f"[*] Deleted file: {os.path.basename(path)}")
                    changed = True
            
            last_state = current_state
            
            if changed:
                # Cool-down to let multiple changes settle
                time.sleep(1)
                last_state = get_all_files()  # Refresh state after cool-down
                run_harness()
                
    except KeyboardInterrupt:
        print("\n[-] Watcher stopped by user.")
        sys.exit(0)

if __name__ == "__main__":
    main()

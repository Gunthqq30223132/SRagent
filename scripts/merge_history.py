#!/usr/bin/env python3
"""scripts/merge_history.py
Programmatic merge of pulled remote SQLite databases and local backup databases.
"""

import os
import sys
import sqlite3
from pathlib import Path

def merge_db(main_db_path: Path, backup_db_path: Path) -> None:
    print(f"[*] Merging backup {backup_db_path} into main DB {main_db_path}...")
    try:
        conn = sqlite3.connect(str(main_db_path))
        cursor = conn.cursor()
        
        # Attach backup database
        cursor.execute(f"ATTACH ? AS backup_db", (str(backup_db_path),))
        
        # Find all tables in main DB
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        for table in tables:
            if table.startswith("sqlite_"):
                continue
            
            print(f"    - Merging table: {table}")
            try:
                # Merge records using INSERT OR IGNORE
                cursor.execute(f"INSERT OR IGNORE INTO main.\"{table}\" SELECT * FROM backup_db.\"{table}\"")
            except Exception as table_err:
                print(f"[!] Warning: error merging table {table}: {table_err}", file=sys.stderr)
                
        conn.commit()
        cursor.execute("DETACH backup_db")
        conn.close()
        
        # Successfully merged, clean up backup
        backup_db_path.unlink()
        print(f"[+] Successfully merged and removed local backup: {backup_db_path}")
    except Exception as e:
        print(f"[ERROR] Failed to merge database {main_db_path}: {e}", file=sys.stderr)

def main() -> int:
    sync_dir = os.path.expanduser("~/.claude/profiles/anesthos")
    if not os.path.exists(sync_dir):
        print(f"[WARNING] Sync directory {sync_dir} does not exist. Nothing to merge.")
        return 0

    print(f"[*] Starting semantic merge of SQLite history databases in: {sync_dir}")
    
    # Recursively find any .local files
    db_suffixes = {".db.local", ".sqlite.local", ".sqlite3.local"}
    
    for root, dirs, files in os.walk(sync_dir):
        if ".git" in dirs:
            dirs.remove(".git")
            
        for file in files:
            file_path = Path(root) / file
            
            is_backup = False
            for suffix in db_suffixes:
                if file_path.name.endswith(suffix):
                    is_backup = True
                    break
                    
            if is_backup:
                main_db_path = file_path.with_name(file_path.name[:-6])
                
                if not main_db_path.exists():
                    file_path.rename(main_db_path)
                    print(f"[+] Restored local-only database: {main_db_path}")
                else:
                    merge_db(main_db_path, file_path)
                    
    print("[*] SQLite database merge complete.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

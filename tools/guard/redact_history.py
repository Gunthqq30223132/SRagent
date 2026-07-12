#!/usr/bin/env python3
"""tools/guard/redact_history.py
Scan history files in ~/.claude/profiles/anesthos and redact secrets.
"""

import os
import sys
import sqlite3
from pathlib import Path

# Add project root to sys.path to import outbound.py
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from tools.guard.outbound import redact
except ImportError:
    # Fallback to copy the core redacting regex/logic if import path doesn't resolve
    import re
    _ENV_SECRET_NAMES = (
        "IEEE_API_KEY|NOTION_TOKEN|NOTION_PARENT_PAGE_ID|ALERT_WEBHOOK_URL|"
        "GEMINI_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY"
    )
    RULES = [
        ("SECRET_OPENAI_ANTHROPIC", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "API key"),
        ("SECRET_GITHUB", re.compile(r"\b(?:ghp_|gho_|ghs_|ghr_)[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "GitHub token"),
        ("SECRET_AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
        ("SECRET_SLACK", re.compile(r"\bxox[bpars]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
        ("SECRET_GOOGLE", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"), "Google API key"),
        ("ENV_ASSIGNMENT", re.compile(rf"\b(?:{_ENV_SECRET_NAMES})\s*=\s*['\"]?\S{{4,}}"), "Env var assignment"),
        ("PATH_HOME", re.compile(r"(?:/Users|/home)/[A-Za-z0-9._-]+(?:/[^\s\"'`)\]]*)?"), "Path"),
        ("IP_PRIVATE", re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|127\.0\.0\.1)(?::\d{1,5})?\b|\blocalhost:\d{2,5}\b"), "IP"),
        ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "Email"),
        ("PHONE_VN", re.compile(r"(?<!\d)(?:\+84|0)(?:3|5|7|8|9)\d{8}(?!\d)"), "Phone"),
        ("CCCD_VN", re.compile(r"(?<!\d)\d{12}(?!\d)"), "CCCD"),
    ]
    def redact(payload: str) -> str:
        out = payload
        for rule_id, pat, _ in RULES:
            out = pat.sub(f"«REDACTED:{rule_id}»", out)
        return out

def redact_text_file(filepath: Path) -> None:
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        redacted = redact(content)
        if redacted != content:
            filepath.write_text(redacted, encoding="utf-8")
            print(f"[+] Redacted secrets in text file: {filepath}")
    except Exception as e:
        print(f"[!] Error redacting text file {filepath}: {e}", file=sys.stderr)

def redact_sqlite_db(filepath: Path) -> None:
    try:
        conn = sqlite3.connect(str(filepath))
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        for table in tables:
            # Skip sqlite system tables
            if table.startswith("sqlite_"):
                continue
                
            cursor.execute(f"PRAGMA table_info('{table}');")
            columns_info = cursor.fetchall()
            
            text_columns = []
            pks = []
            for col in columns_info:
                col_name = col[1]
                col_type = (col[2] or "").upper()
                is_pk = col[5] > 0
                if is_pk:
                    pks.append(col_name)
                # Treat empty types (dynamically typed) or text-like types as text candidates
                if col_type == "" or any(kw in col_type for kw in ["TEXT", "CHAR", "CLOB", "JSON", "VARCHAR"]):
                    text_columns.append(col_name)
                    
            if not text_columns:
                continue
                
            # Try to fetch using rowid (which avoids needing to identify primary keys)
            has_rowid = True
            try:
                select_cols = ["rowid"] + text_columns
                cursor.execute(f"SELECT {', '.join([f'\"{c}\"' for c in select_cols])} FROM \"{table}\"")
                rows = cursor.fetchall()
            except sqlite3.OperationalError:
                # WITHOUT ROWID table
                has_rowid = False
                select_cols = pks + text_columns
                cursor.execute(f"SELECT {', '.join([f'\"{c}\"' for c in select_cols])} FROM \"{table}\"")
                rows = cursor.fetchall()
                
            # Scan each row
            for row in rows:
                updated_values = {}
                if has_rowid:
                    row_id = row[0]
                    for idx, col_name in enumerate(text_columns):
                        val = row[idx + 1]
                        if isinstance(val, str):
                            redacted_val = redact(val)
                            if redacted_val != val:
                                updated_values[col_name] = redacted_val
                    if updated_values:
                        set_clause = ", ".join([f"\"{col}\" = ?" for col in updated_values.keys()])
                        params = list(updated_values.values()) + [row_id]
                        cursor.execute(f"UPDATE \"{table}\" SET {set_clause} WHERE rowid = ?", params)
                else:
                    # WITHOUT ROWID table - identify by PK
                    pk_vals = row[:len(pks)]
                    for idx, col_name in enumerate(text_columns):
                        val = row[len(pks) + idx]
                        if isinstance(val, str):
                            redacted_val = redact(val)
                            if redacted_val != val:
                                updated_values[col_name] = redacted_val
                    if updated_values:
                        set_clause = ", ".join([f"\"{col}\" = ?" for col in updated_values.keys()])
                        where_clause = " AND ".join([f"\"{pk}\" = ?" for pk in pks])
                        params = list(updated_values.values()) + list(pk_vals)
                        cursor.execute(f"UPDATE \"{table}\" SET {set_clause} WHERE {where_clause}", params)
        
        conn.commit()
        conn.close()
        print(f"[+] Redacted secrets in SQLite DB: {filepath}")
    except Exception as e:
        print(f"[!] Error redacting SQLite DB {filepath}: {e}", file=sys.stderr)

def main() -> int:
    sync_dir = os.path.expanduser("~/.claude/profiles/anesthos")
    if not os.path.exists(sync_dir):
        print(f"[WARNING] Sync directory {sync_dir} does not exist. Nothing to redact.")
        return 0

    print(f"[*] Starting history scanning and redaction in: {sync_dir}")
    
    text_extensions = {".jsonl", ".json", ".log", ".txt", ".xml", ".yaml", ".yml", ".md"}
    db_extensions = {".db", ".sqlite", ".sqlite3"}
    
    for root, dirs, files in os.walk(sync_dir):
        # Skip git directory
        if ".git" in dirs:
            dirs.remove(".git")
            
        for file in files:
            file_path = Path(root) / file
            
            # Check if text file
            if file_path.suffix.lower() in text_extensions or file_path.name in {".claude.json", "settings.json", "settings.local.json", "opencode.json"}:
                redact_text_file(file_path)
            elif file_path.suffix.lower() in db_extensions:
                redact_sqlite_db(file_path)
                
    print("[*] History scanning and redaction complete.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

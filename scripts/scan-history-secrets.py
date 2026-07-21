#!/usr/bin/env python3
"""
scan-history-secrets.py
Scans Claude Code .jsonl chat history files for leaked secrets and PII.
Designed for macOS, runs standalone without dependencies.

Usage:
  python3 scan-history-secrets.py [--fix] [path_to_scan]

  --fix   Redact detected patterns in-place (creates .backup first)
  Default path: ~/.claude/profiles/anesthos/
"""

import sys
import os
import re
import json
import shutil
from pathlib import Path

# === Pattern Definitions ===
PATTERNS = {
    "API Key (sk-)": re.compile(r'sk-[a-zA-Z0-9_-]{20,}'),
    "Google API Key": re.compile(r'AIzaSy[a-zA-Z0-9_-]{30,}'),
    "GitHub Token": re.compile(r'ghp_[a-zA-Z0-9]{30,}'),
    "GitHub OAuth": re.compile(r'gho_[a-zA-Z0-9]{30,}'),
    "AWS Key": re.compile(r'AKIA[0-9A-Z]{16}'),
    "Slack Token": re.compile(r'xox[bpsa]-[a-zA-Z0-9-]+'),
    "Private Key Block": re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    "Email Address": re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'),
    "Vietnamese CCCD (12 digits)": re.compile(r'(?<!\d)\d{12}(?!\d)'),
    "Vietnamese CMND (9 digits)": re.compile(r'(?<!\d)\d{9}(?!\d)'),
    "Phone Number": re.compile(r'(?<!\d)(?:\+?84|0)[0-9]{9,10}(?!\d)'),
}

# Known safe patterns to ignore (avoid false positives)
SAFE_PATTERNS = {
    # Common 9/12 digit patterns that are NOT IDs
    re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'),  # ISO timestamps
    re.compile(r'"created":\s*\d{9,12}'),  # Unix timestamps in JSON
    re.compile(r'"size":\s*\d{9,12}'),  # File sizes
    re.compile(r'chatcmpl-\d+'),  # Chat completion IDs
    re.compile(r'"total_tokens":\s*\d+'),  # Token counts
    re.compile(r'step_\d+'),  # Step indices
    re.compile(r'task-\d+'),  # Task IDs
}

# Redaction replacement
REDACT = "[REDACTED]"


def is_safe_match(line, match_start, match_end):
    """Check if a match is a known safe pattern (false positive)."""
    context = line[max(0, match_start - 30):min(len(line), match_end + 30)]
    for safe in SAFE_PATTERNS:
        if safe.search(context):
            return True
    return False


def scan_file(filepath, fix_mode=False):
    """Scan a single file for secret patterns. Returns list of findings."""
    findings = []
    try:
        with open(filepath, 'r', errors='replace') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  ⚠️ Cannot read {filepath}: {e}")
        return findings

    redacted_lines = []
    file_modified = False

    for line_num, line in enumerate(lines, 1):
        line_findings = []
        redacted_line = line

        for pattern_name, pattern in PATTERNS.items():
            for match in pattern.finditer(line):
                if is_safe_match(line, match.start(), match.end()):
                    continue

                matched_text = match.group()

                # Skip very short matches for digit-only patterns (too many false positives)
                if pattern_name in ("Vietnamese CCCD (12 digits)", "Vietnamese CMND (9 digits)"):
                    # Only flag if it looks like a standalone ID number
                    before = line[max(0, match.start()-1):match.start()]
                    after = line[match.end():min(len(line), match.end()+1)]
                    if before.isdigit() or after.isdigit():
                        continue

                finding = {
                    "file": str(filepath),
                    "line": line_num,
                    "pattern": pattern_name,
                    "match": matched_text[:20] + "..." if len(matched_text) > 20 else matched_text,
                    "context": line.strip()[:80],
                }
                line_findings.append(finding)
                findings.append(finding)

                if fix_mode:
                    redacted_line = redacted_line.replace(matched_text, REDACT)
                    file_modified = True

        redacted_lines.append(redacted_line)

    if fix_mode and file_modified:
        backup_path = str(filepath) + ".backup"
        shutil.copy2(filepath, backup_path)
        with open(filepath, 'w') as f:
            f.writelines(redacted_lines)
        print(f"  🔧 Redacted {len(findings)} patterns. Backup: {backup_path}")

    return findings


def main():
    fix_mode = "--fix" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    scan_path = args[0] if args else os.path.expanduser("~/.claude/profiles/anesthos/")

    print(f"🔍 Scanning: {scan_path}")
    print(f"   Mode: {'FIX (redact in-place)' if fix_mode else 'SCAN ONLY (read-only)'}")
    print()

    scan_dir = Path(scan_path)
    if scan_dir.is_file():
        files = [scan_dir]
    else:
        files = sorted(scan_dir.rglob("*.jsonl"))

    if not files:
        print("  No .jsonl files found.")
        return

    total_findings = []
    for f in files:
        # Skip .git directory
        if ".git" in f.parts:
            continue
        findings = scan_file(f, fix_mode=fix_mode)
        if findings:
            print(f"\n  📄 {f.name}: {len(findings)} finding(s)")
            for finding in findings:
                print(f"     L{finding['line']}: [{finding['pattern']}] {finding['match']}")
        total_findings.extend(findings)

    print()
    if total_findings:
        print(f"⚠️ Total: {len(total_findings)} potential secret(s)/PII found across {len(files)} file(s).")
        if not fix_mode:
            print("   Run with --fix to redact them in-place (backups created automatically).")
        sys.exit(1)
    else:
        print(f"✅ Clean! No secrets or PII found in {len(files)} file(s).")
        sys.exit(0)


if __name__ == "__main__":
    main()

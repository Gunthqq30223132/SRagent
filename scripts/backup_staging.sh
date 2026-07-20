#!/bin/bash
# HƯỚNG DẪN KHÔI PHỤC (RESTORE INSTRUCTIONS):
# 1. Dừng mọi tác vụ ghi đang chạy (dừng Streamlit UI và các command line runner).
# 2. Sao lưu/rename file DB hiện tại: mv staging/sr_agent.db staging/sr_agent.db.bak
# 3. Copy bản backup đè vào: cp staging/backups/staging-YYYYMMDD-HHMMSS.db staging/sr_agent.db

set -euo pipefail

DB_PATH="${SR_AGENT_DB:-staging/sr_agent.db}"
if [ -n "${1:-}" ]; then
  DB_PATH="$1"
fi

# Resolve directories
BACKUP_DIR="$(dirname "$DB_PATH")/backups"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
BACKUP_FILE="$BACKUP_DIR/staging-$TIMESTAMP.db"

echo "Creating WAL-safe backup of $DB_PATH to $BACKUP_FILE..."
# WAL-safe qua SQLite Online Backup API. Ưu tiên sqlite3 CLI; nếu vắng (CI/runner
# tối giản không cài sqlite3 binary) fallback stdlib Python — cùng một API .backup(),
# WAL-safe như nhau, 0 dep mới.
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"
else
  python3 - "$DB_PATH" "$BACKUP_FILE" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
    s.backup(d)
PY
fi

# Rotate: keep only the 7 newest files
echo "Rotating backups in $BACKUP_DIR..."
(
  cd "$BACKUP_DIR"
  FILES=$(find . -maxdepth 1 -name "staging-*.db" | sort)
  COUNT=$(echo "$FILES" | grep -c "staging-" || true)
  if [ "$COUNT" -gt 7 ]; then
    LIMIT=$((COUNT - 7))
    echo "$FILES" | head -n "$LIMIT" | while read -r f; do
      echo "Deleting old backup: $f"
      rm -f "$f"
    done
  fi
)
echo "Backup completed successfully."

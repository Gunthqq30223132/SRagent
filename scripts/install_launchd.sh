#!/bin/bash
# Cài LaunchAgent chạy SR-Agent ingest hằng ngày 7:00 trên macOS.
#
#   ./scripts/install_launchd.sh "efficient transformer inference"
#
# Chạy lại script này để đổi query (idempotent: tự gỡ bản cũ trước khi nạp).
set -euo pipefail

LABEL="com.sragent.daily"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO_DIR/.venv/bin/python"
TEMPLATE="$REPO_DIR/scripts/${LABEL}.plist.template"
DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"

if [[ "$(uname)" != "Darwin" ]]; then
    echo "LỖI: launchd chỉ có trên macOS. Trên Linux dùng cron/systemd timer." >&2
    exit 1
fi
if [[ $# -lt 1 || -z "$1" ]]; then
    echo "Cách dùng: $0 \"<standing query>\"" >&2
    exit 1
fi
QUERY="$1"

if [[ ! -x "$PY" ]]; then
    echo "LỖI: chưa có $PY — chạy 'make setup' trước." >&2
    exit 1
fi

echo "== Kiểm tra tiền vận hành (doctor) =="
"$PY" -m sr_agent.pipeline doctor   # REQUIRED fail -> exit 1, dừng tại đây (set -e)

echo
echo "== Render plist =="
mkdir -p "$HOME/Library/LaunchAgents" "$REPO_DIR/staging"
"$PY" - "$TEMPLATE" "$REPO_DIR" "$QUERY" > "$DEST" <<'PYEOF'
import pathlib
import sys
from xml.sax.saxutils import escape

template, repo, query = sys.argv[1], sys.argv[2], sys.argv[3]
text = pathlib.Path(template).read_text(encoding="utf-8")
text = text.replace("{{REPO_DIR}}", escape(repo)).replace("{{QUERY}}", escape(query))
sys.stdout.write(text)
PYEOF
plutil -lint "$DEST"

echo
echo "== Nạp vào launchd =="
launchctl bootout "gui/$(id -u)" "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "Đã cài $LABEL — chạy hằng ngày 7:00 (máy ngủ qua giờ đó sẽ chạy bù khi thức dậy)."
echo "Query: $QUERY"
echo "Log:   $REPO_DIR/staging/launchd.log"
echo "Chạy thử ngay: launchctl kickstart gui/$(id -u)/$LABEL"

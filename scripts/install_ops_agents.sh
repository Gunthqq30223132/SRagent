#!/bin/bash
# Cài 2 agent vận hành M4: com.sragent.heal (15 phút/lần) + com.sragent.enrich (02:00).
# Idempotent — chạy lại để cập nhật. Agent ingest hằng ngày cài riêng bằng
# install_launchd.sh (cần standing query).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO_DIR/.venv/bin/python"

if [[ "$(uname)" != "Darwin" ]]; then
    echo "LỖI: launchd chỉ có trên macOS." >&2
    exit 1
fi
if [[ ! -x "$PY" ]]; then
    echo "LỖI: chưa có $PY — chạy 'make setup' trước." >&2
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$REPO_DIR/staging"

for LABEL in com.sragent.heal com.sragent.enrich; do
    TEMPLATE="$REPO_DIR/scripts/${LABEL}.plist.template"
    DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"
    "$PY" - "$TEMPLATE" "$REPO_DIR" > "$DEST" <<'PYEOF'
import pathlib
import sys
from xml.sax.saxutils import escape

template, repo = sys.argv[1], sys.argv[2]
text = pathlib.Path(template).read_text(encoding="utf-8")
sys.stdout.write(text.replace("{{REPO_DIR}}", escape(repo)))
PYEOF
    plutil -lint "$DEST"
    launchctl bootout "gui/$(id -u)" "$DEST" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$DEST"
    echo "Đã cài $LABEL"
done

echo
echo "heal:   mỗi 15 phút + ngay khi máy thức (log: staging/heal.log)"
echo "enrich: 02:00 hằng đêm, tối đa 10 doc (log: staging/enrich.log)"
echo "Chạy thử ngay: launchctl kickstart gui/$(id -u)/com.sragent.heal"

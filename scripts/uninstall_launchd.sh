#!/bin/bash
# Gỡ LaunchAgent com.sragent.daily khỏi launchd và xóa plist.
set -euo pipefail

LABEL="com.sragent.daily"
DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"

if [[ "$(uname)" != "Darwin" ]]; then
    echo "LỖI: launchd chỉ có trên macOS." >&2
    exit 1
fi

launchctl bootout "gui/$(id -u)" "$DEST" 2>/dev/null || true
rm -f "$DEST"
echo "Đã gỡ $LABEL."

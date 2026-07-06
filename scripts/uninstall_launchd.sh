#!/bin/bash
# Gỡ toàn bộ LaunchAgent của SR-Agent (daily + heal + enrich) khỏi launchd.
set -euo pipefail

if [[ "$(uname)" != "Darwin" ]]; then
    echo "LỖI: launchd chỉ có trên macOS." >&2
    exit 1
fi

for LABEL in com.sragent.daily com.sragent.heal com.sragent.enrich; do
    DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"
    if [[ -f "$DEST" ]]; then
        launchctl bootout "gui/$(id -u)" "$DEST" 2>/dev/null || true
        rm -f "$DEST"
        echo "Đã gỡ $LABEL."
    fi
done

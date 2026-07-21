#!/bin/sh
set -eu

# backup-to-ssd.sh
# Sync local APFS repository to external SSD for physical redundancy.

SSD_DIR="/Volumes/Gun SSD/3. PROJECT /3. SẮP XẾP"
if [ ! -d "$SSD_DIR" ]; then
  echo "⚠️ External SSD not mounted. Cannot backup to SSD." >&2
  exit 1
fi

echo "Running backup to SSD..."
rsync -av --delete \
  --exclude="node_modules" \
  --exclude=".venv" \
  --exclude=".next" \
  --exclude=".pytest_cache" \
  --exclude="._*" \
  "$HOME/projects/AnesthOS/" \
  "$SSD_DIR/AnesthOs.backup/"

echo "✅ Backup to SSD completed successfully."

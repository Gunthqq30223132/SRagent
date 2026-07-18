#!/bin/sh
set -euo pipefail
# AnesthOS Infrastructure Setup
# This script installs all infrastructure components

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Setting up AnesthOS infrastructure..."

# 3. Source aliases in .zshrc
if ! grep -q "source.*aliases.sh" ~/.zshrc 2>/dev/null; then
  echo "source ~/.anesthos/aliases.sh" >> ~/.zshrc
  echo "Aliases added to .zshrc"
fi

# 4. Create required directories
mkdir -p ~/.anesthos
mkdir -p ~/Library/Application\ Support/AnesthOS

echo "AnesthOS infrastructure setup complete"

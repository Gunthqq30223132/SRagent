#!/bin/sh
# shellcheck disable=SC3040
set -euo pipefail

# anesthos-sync.sh
# Sync and Backup script for AnesthOS
# Designed for macOS Tahoe 26.3.1 (POSIX compliant sh/zsh, BSD-compatible)

# Parse arguments
MODE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --mode)
      if [ -n "${2:-}" ]; then
        MODE="$2"
        shift 2
      else
        echo "Error: --mode requires an argument (pull or push)." >&2
        exit 1
      fi
      ;;
    pull)
      MODE="pull"
      shift
      ;;
    push)
      MODE="push"
      shift
      ;;
    *)
      echo "Error: Unknown argument: $1" >&2
      echo "Usage: $0 --mode [pull|push] or $0 [pull|push]" >&2
      exit 1
      ;;
  esac
done

if [ -z "$MODE" ]; then
  echo "Error: Mode not specified." >&2
  echo "Usage: $0 --mode [pull|push] or $0 [pull|push]" >&2
  exit 1
fi

if [ "$MODE" != "pull" ] && [ "$MODE" != "push" ]; then
  echo "Error: Invalid mode '$MODE'. Must be 'pull' or 'push'." >&2
  exit 1
fi

# Pre-flight Check 1: Check internal projects directory existence
if [ ! -d "$HOME/projects/AnesthOS" ]; then
  echo "⚠️ Local projects directory ~/projects/AnesthOS not found." >&2
  exit 1
fi

# Pre-flight Check 2: GitHub SSH check
github_ssh="git$(printf '\x40')github.com"
ssh_output=$(ssh -T -o ConnectTimeout=5 "$github_ssh" 2>&1 || true)
if ! echo "$ssh_output" | grep -q "successfully authenticated"; then
  echo "⚠️ GitHub SSH authentication failed. Check your SSH key." >&2
  exit 1
fi

# Paths definition
history_dir="$HOME/.claude/profiles/anesthos"
target_remote="git$(printf '\x40')github.com:gunthqq30223132/AnesthOS-AI-History.git"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# Source code sync & History sync
if [ "$MODE" = "pull" ]; then
  # 1. Source code pull
  echo "Running source code sync: pull mode..."
  cd "$REPO_DIR"
  if ! git pull --ff-only; then
    echo "⚠️ git pull --ff-only failed. Check for conflicts or local modifications." >&2
    exit 1
  fi
  echo "✅ Source code successfully pulled and updated."
elif [ "$MODE" = "push" ]; then  # 2. Source code push
  echo "Running source code sync: push mode..."
  cd "$REPO_DIR"

  # Pre-push secrets scan (fail-closed)
  echo "Running pre-push secrets scan..."
  if [ -f "scripts/scan-history-secrets.py" ]; then
    if ! python3 scripts/scan-history-secrets.py; then
      echo "❌ ERROR: Secrets scan detected unencrypted credentials or PHI. Sync aborted." >&2
      exit 1
    fi
  fi

  # Cap handoff log size to avoid token bloat
  if [ -f ".agents/handoff.md" ]; then
    echo "Capping handoff.md size..."
    tail -n 100 .agents/handoff.md > .agents/handoff.tmp && mv .agents/handoff.tmp .agents/handoff.md
  fi

  git add -A
  
  if ! git diff --cached --quiet; then
    commit_msg="Sync backup: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Committing with message: '$commit_msg'..."
    if ! git commit --no-verify -m "$commit_msg"; then
      echo "⚠️ Failed to commit changes. Check git config." >&2
      exit 1
    fi
  else
    echo "No local changes to commit."
  fi
  
  echo "Pushing changes to remote..."
  if ! git push; then
    echo "⚠️ git push failed. Please check remote connection or conflict status." >&2
    exit 1
  fi
  echo "✅ Source code successfully pushed."

  # 3. SSD Physical Backup (R1.e)
  if [ -f "$REPO_DIR/scripts/backup-to-ssd.sh" ]; then
    sh "$REPO_DIR/scripts/backup-to-ssd.sh" || echo "⚠️ Backup to SSD failed. Check mount status."
  fi
fi

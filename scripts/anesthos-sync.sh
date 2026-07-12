#!/bin/sh
# shellcheck disable=SC3040
set -euo pipefail

# anesthos-sync.sh
# Sync and Backup script for AnesthOS

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

# Pre-flight Check 1: SSD mount check
if [ ! -d "$HOME/projects/AnesthOS" ]; then
  echo "⚠️ External SSD not mounted. Please connect your SSD and try again." >&2
  exit 1
fi

# Pre-flight Check 2: GitHub SSH check
github_ssh="git$(printf '\x40')github.com"
ssh_output=$(ssh -T -o ConnectTimeout=5 "$github_ssh" 2>&1 || true)
if ! echo "$ssh_output" | grep -q "successfully authenticated"; then
  echo "⚠️ GitHub SSH authentication failed. Check your SSH key." >&2
  exit 1
fi

# Safety check: claude process check
if pgrep -x claude >/dev/null 2>&1; then
  echo "⚠️ Claude Code process is currently running. Please run \`/exit\` in Claude before executing this backup to prevent history corruption."
  exit 0
fi

# OmniRoute config backup
src="$HOME/.omniroute"
icloud_base="$HOME/Library/Mobile Documents/com~apple~CloudDocs"
dst="$icloud_base/Backups/omniroute"

if [ -L "$src" ]; then
  echo "ℹ️ $src is already a symlink. Skipping backup step."
elif [ -d "$src" ]; then
  if [ ! -d "$icloud_base" ]; then
    echo "ℹ️ iCloud Drive is not available. Skipping OmniRoute config backup."
  else
    echo "Backing up OmniRoute config to iCloud..."
    mkdir -p "$icloud_base/Backups"
    if [ -d "$dst" ]; then
      echo "⚠️ Target backup directory already exists at $dst. Renaming existing backup..."
      mv "$dst" "${dst}_backup_$(date +%Y%m%d%H%M%S)"
    fi
    mv "$src" "$dst"
    ln -s "$dst" "$src"
    echo "✅ Successfully backed up ~/.omniroute/ to iCloud and created symlink."
  fi
else
  echo "ℹ️ ~/.omniroute directory does not exist. Skipping backup."
fi

# Setup REPO_DIR
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# AI chat history Git backup
history_dir="$HOME/.claude/profiles/anesthos"
target_remote="git$(printf '\x40')github.com:gunthqq30223132/AnesthOS-AI-History.git"

if [ -d "$history_dir" ]; then
  echo "Checking AI chat history repository..."
  
  # Ensure gitignore is set up in history directory
  cat << 'EOF' > "$history_dir/.gitignore"
settings.json
settings.local.json
opencode.json
*.local
EOF

  if ! git -C "$history_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Initializing git repository in $history_dir..."
    git -C "$history_dir" init
  fi

  # Manage git remote
  if ! git -C "$history_dir" remote get-url origin >/dev/null 2>&1; then
    git -C "$history_dir" remote add origin "$target_remote"
  else
    git -C "$history_dir" remote set-url origin "$target_remote"
  fi

  # Untrack machine-specific configs if they were accidentally tracked
  git -C "$history_dir" rm --cached settings.json settings.local.json opencode.json 2>/dev/null || true

  # Ensure the active branch is named main
  git -C "$history_dir" branch -M main 2>/dev/null || true

  if [ "$MODE" = "push" ]; then
    echo "Running secret scanner on AI history files..."
    python3 "$REPO_DIR/tools/guard/redact_history.py"

    # Add files and check if commit is needed
    git -C "$history_dir" add -A
    # Check if there are changes to commit (staged changes)
    if ! git -C "$history_dir" diff --cached --quiet; then
      echo "Committing AI chat history..."
      if ! git -C "$history_dir" commit --no-verify -m "Backup chat history: $(date '+%Y-%m-%d %H:%M:%S')"; then
        echo "⚠️ Failed to commit AI chat history. Proceeding anyway..."
      fi
    else
      echo "No new chat history changes to commit."
    fi

    # Push to remote, handle errors gracefully
    echo "Pushing AI chat history to GitHub..."
    if ! git -C "$history_dir" push -u origin main; then
      echo "⚠️ Failed to push AI chat history to remote. Skipping push gracefully."
    else
      echo "✅ AI chat history successfully pushed to GitHub."
    fi

  elif [ "$MODE" = "pull" ]; then
    echo "Backing up local database files before pulling..."
    find "$history_dir" -type f \( -name "*.db" -o -name "*.sqlite" \) | while read -r db_file; do
      if [ -f "$db_file" ]; then
        echo "Backing up local database: $db_file -> ${db_file}.local"
        mv "$db_file" "${db_file}.local"
      fi
    done

    echo "Pulling AI chat history from remote..."
    if ! git -C "$history_dir" pull origin main; then
      echo "⚠️ Failed to pull AI chat history from remote. Skipping pull gracefully."
    fi

    echo "Merging local backup database files..."
    python3 "$REPO_DIR/scripts/merge_history.py"
  fi
else
  echo "ℹ️ AI chat history directory $history_dir does not exist. Skipping history backup."
fi

echo "Navigating to repository root: $REPO_DIR..."
cd "$REPO_DIR"

if [ "$MODE" = "pull" ]; then
  echo "Running source code sync: pull mode..."
  # Run git pull
  if ! git pull; then
    unmerged=$(git diff --name-only --diff-filter=U)
    if [ -n "$unmerged" ]; then
      echo "⚠️ Merge conflict detected! Please resolve conflicts manually in the following files:" >&2
      echo "$unmerged" >&2
      exit 1
    else
      echo "⚠️ git pull failed. Please check git status, stash local changes, and try again." >&2
      exit 1
    fi
  fi
  echo "✅ Source code successfully pulled and updated."

elif [ "$MODE" = "push" ]; then
  echo "Running source code sync: push mode..."
  echo "Staging all changes..."
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
fi

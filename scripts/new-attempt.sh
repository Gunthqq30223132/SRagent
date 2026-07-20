#!/bin/sh
# new-attempt.sh — Create a git worktree + branch for a dispatch attempt
# POSIX-compatible (no bashisms). Works on macOS and Linux.
#
# Usage: scripts/new-attempt.sh <task-id>
#
# Exit codes:
#   0  success
#   1  usage / validation error
#   2  git error

set -e

# ── Validate arguments ───────────────────────────────────────────────
if [ $# -ne 1 ]; then
    echo "Usage: scripts/new-attempt.sh <task-id>" >&2
    exit 1
fi

# ── Verify we're inside a git repository ─────────────────────────────
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Error: not inside a git repository" >&2
    exit 1
fi

# ── Set variables ────────────────────────────────────────────────────
TASK_ID="$1"
BASE_SHA=$(git rev-parse HEAD) || { echo "Error: failed to resolve HEAD" >&2; exit 2; }
REPO_ROOT=$(git rev-parse --show-toplevel) || { echo "Error: failed to find repo root" >&2; exit 2; }
REPO_NAME=$(basename "$REPO_ROOT")
BRANCH_NAME="attempt/$TASK_ID"
WORKTREE_DIR="$REPO_ROOT/../attempts/$TASK_ID"

# ── Check branch doesn't already exist ───────────────────────────────
if git show-ref --verify --quiet "refs/heads/$BRANCH_NAME" 2>/dev/null; then
    echo "Error: branch '$BRANCH_NAME' already exists" >&2
    exit 1
fi

# ── Create the worktree ──────────────────────────────────────────────
git worktree add -b "$BRANCH_NAME" "$WORKTREE_DIR" HEAD || {
    echo "Error: failed to create worktree at '$WORKTREE_DIR'" >&2
    exit 2
}

# ── Resolve the absolute worktree path for display ───────────────────
# Use cd + pwd to get a clean absolute path (POSIX-portable)
ABS_WORKTREE=$(cd "$WORKTREE_DIR" && pwd)

# ── Print anchor ─────────────────────────────────────────────────────
echo "=== NEW ATTEMPT ==="
echo "repo: $REPO_NAME | branch: $BRANCH_NAME | HEAD: $BASE_SHA | cwd: $ABS_WORKTREE"

# ── Capsule SHA-256 ──────────────────────────────────────────────────
DISPATCH_FILE="$REPO_ROOT/.agents/dispatch/$TASK_ID.md"
if [ -f "$DISPATCH_FILE" ]; then
    CAPSULE_SHA=$(shasum -a 256 "$DISPATCH_FILE" | cut -c1-12)
    echo "Capsule-SHA256: $CAPSULE_SHA"
else
    echo "Capsule-SHA256: (no dispatch envelope found)"
fi

# ── Summary ──────────────────────────────────────────────────────────
echo "Worktree: $ABS_WORKTREE"
echo "Branch: $BRANCH_NAME"
echo "Base: $BASE_SHA"
echo "Ready for dispatch."

exit 0

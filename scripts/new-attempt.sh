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

# ── Validate arguments & TASK_ID ─────────────────────────────────────
if [ $# -ne 1 ]; then
    echo "Usage: scripts/new-attempt.sh <task-id>" >&2
    exit 1
fi

TASK_ID="$1"

# TASK_ID validation: only allow alphanumeric, dot, underscore, hyphen
case "$TASK_ID" in
    *[!A-Za-z0-9._-]*|"")
        echo "Error: TASK_ID '$TASK_ID' contains invalid characters. Only [A-Za-z0-9._-] allowed." >&2
        exit 1
        ;;
esac

# ── Verify we're inside a git repository ─────────────────────────────
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Error: not inside a git repository" >&2
    exit 1
fi

# ── Set variables ────────────────────────────────────────────────────
BASE_SHA=$(git rev-parse HEAD) || { echo "Error: failed to resolve HEAD" >&2; exit 2; }
REPO_ROOT=$(git rev-parse --show-toplevel) || { echo "Error: failed to find repo root" >&2; exit 2; }
REPO_NAME=$(basename "$REPO_ROOT")
BRANCH_NAME="attempt/$TASK_ID"
WORKTREE_DIR="$REPO_ROOT/../attempts/$TASK_ID"
DISPATCH_REL_PATH=".agents/dispatch/$TASK_ID.md"

# ── Enforce committed dispatch envelope ──────────────────────────────
# Must exist in git index/commit HEAD (not just untracked or dirty uncommitted file)
if ! git cat-file -e "HEAD:$DISPATCH_REL_PATH" 2>/dev/null; then
    echo "Error: dispatch envelope '$DISPATCH_REL_PATH' does not exist in committed HEAD." >&2
    echo "Rule (ADR §14 Step 2): dispatch envelope must be committed before dispatch." >&2
    exit 1
fi

# ── Validate TARGET in dispatch envelope ─────────────────────────────
TARGET=$(git show "HEAD:$DISPATCH_REL_PATH" 2>/dev/null | grep '^TARGET:' | head -n 1 | sed 's/^TARGET:[[:space:]]*//')
case "$TARGET" in
    */*)
        ;;
    *)
        echo "Error: TARGET '$TARGET' in dispatch envelope missing provider prefix (must be provider/model)." >&2
        exit 1
        ;;
esac

# Calculate SHA-256 of the COMMITTED version (HEAD), fallback shasum / sha256sum
if command -v shasum >/dev/null 2>&1; then
    CAPSULE_SHA=$(git show "HEAD:$DISPATCH_REL_PATH" | shasum -a 256 | cut -c1-12)
elif command -v sha256sum >/dev/null 2>&1; then
    CAPSULE_SHA=$(git show "HEAD:$DISPATCH_REL_PATH" | sha256sum | cut -c1-12)
else
    echo "Error: neither shasum nor sha256sum found on system" >&2
    exit 1
fi

# ── Check branch doesn't already exist (local or remote) ───────────
if git show-ref --verify --quiet "refs/heads/$BRANCH_NAME" 2>/dev/null || \
   git show-ref --verify --quiet "refs/remotes/origin/$BRANCH_NAME" 2>/dev/null; then
    echo "Error: branch '$BRANCH_NAME' already exists" >&2
    exit 1
fi

# ── Create the worktree ──────────────────────────────────────────────
git worktree add -b "$BRANCH_NAME" "$WORKTREE_DIR" HEAD || {
    echo "Error: failed to create worktree at '$WORKTREE_DIR'" >&2
    exit 2
}

# ── Resolve the absolute worktree path for display ───────────────────
ABS_WORKTREE=$(cd "$WORKTREE_DIR" && pwd)

# ── Print anchor ─────────────────────────────────────────────────────
echo "=== NEW ATTEMPT ==="
echo "repo: $REPO_NAME | branch: $BRANCH_NAME | HEAD: $BASE_SHA | cwd: $ABS_WORKTREE"
echo "Capsule-SHA256: $CAPSULE_SHA"

# ── Summary ──────────────────────────────────────────────────────────
echo "Worktree: $ABS_WORKTREE"
echo "Branch: $BRANCH_NAME"
echo "Base: $BASE_SHA"
echo "Ready for dispatch."

exit 0

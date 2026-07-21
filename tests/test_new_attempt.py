"""Tests for scripts/new-attempt.sh — worktree + branch preflight."""

import os
import subprocess
import textwrap

import pytest

# Resolve script path relative to the actual SRagent repo root.
SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "new-attempt.sh",
)


def _git(args: list[str], cwd: str, **kwargs) -> subprocess.CompletedProcess:
    """Run a git command in the given directory."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        **kwargs,
    )


def _init_repo(path: str) -> str:
    """Create a minimal git repo with one commit. Returns repo path."""
    os.makedirs(path, exist_ok=True)
    _git(["init"], cwd=path)
    _git(["config", "user.email", "noreply@localhost"], cwd=path)
    _git(["config", "user.name", "CI"], cwd=path)
    # Create an initial commit so HEAD exists
    readme = os.path.join(path, "README.md")
    with open(readme, "w") as f:
        f.write("# test repo\n")
    _git(["add", "."], cwd=path)
    _git(["commit", "-m", "init"], cwd=path)
    return path


# ── Happy-path test ──────────────────────────────────────────────────


class TestNewAttemptHappyPath:
    """Exercise the normal success path when committed dispatch file exists."""

    def test_creates_worktree_and_branch_with_committed_dispatch(self, tmp_path):
        repo_dir = str(tmp_path / "repo")
        _init_repo(repo_dir)

        # Create & commit dispatch envelope
        dispatch_dir = os.path.join(repo_dir, ".agents", "dispatch")
        os.makedirs(dispatch_dir, exist_ok=True)
        dispatch_file = os.path.join(dispatch_dir, "test-task-001.md")
        with open(dispatch_file, "w") as f:
            f.write("TARGET: kiro/claude-sonnet-4.5-thinking\n# Dispatch envelope for test-task-001\n")
        _git(["add", "."], cwd=repo_dir)
        _git(["commit", "-m", "add dispatch envelope"], cwd=repo_dir)

        result = subprocess.run(
            ["sh", SCRIPT_PATH, "test-task-001"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )

        # ── Exit code ────────────────────────────────────────────────
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # ── Worktree directory exists ────────────────────────────────
        worktree_dir = tmp_path / "attempts" / "test-task-001"
        assert worktree_dir.is_dir(), f"Worktree dir not found: {worktree_dir}"

        # ── Branch exists ────────────────────────────────────────────
        branch_check = _git(
            ["branch", "--list", "attempt/test-task-001"], cwd=repo_dir
        )
        assert "attempt/test-task-001" in branch_check.stdout

        # ── Stdout assertions ────────────────────────────────────────
        assert "=== NEW ATTEMPT ===" in result.stdout
        assert "attempt/test-task-001" in result.stdout
        assert "Capsule-SHA256:" in result.stdout
        assert "Ready for dispatch." in result.stdout

        # ── Cleanup worktree ─────────────────────────────────────────
        _git(["worktree", "remove", str(worktree_dir), "--force"], cwd=repo_dir)


# ── Error-case tests ─────────────────────────────────────────────────


class TestNewAttemptErrors:
    """Validate that the script fails correctly on bad input or missing envelope."""

    def test_missing_dispatch_envelope_exits_nonzero(self, tmp_path):
        repo_dir = str(tmp_path / "repo")
        _init_repo(repo_dir)

        result = subprocess.run(
            ["sh", SCRIPT_PATH, "missing-envelope-task"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "does not exist in committed HEAD" in result.stderr

    def test_uncommitted_dispatch_envelope_exits_nonzero(self, tmp_path):
        repo_dir = str(tmp_path / "repo")
        _init_repo(repo_dir)

        # Create uncommitted dispatch file
        dispatch_dir = os.path.join(repo_dir, ".agents", "dispatch")
        os.makedirs(dispatch_dir, exist_ok=True)
        with open(os.path.join(dispatch_dir, "uncommitted-task.md"), "w") as f:
            f.write("# Uncommitted dispatch\n")

        result = subprocess.run(
            ["sh", SCRIPT_PATH, "uncommitted-task"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "does not exist in committed HEAD" in result.stderr

    def test_invalid_task_id_exits_nonzero(self, tmp_path):
        repo_dir = str(tmp_path / "repo")
        _init_repo(repo_dir)

        result = subprocess.run(
            ["sh", SCRIPT_PATH, "../invalid/path"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "invalid characters" in result.stderr

    def test_no_arguments_exits_nonzero(self, tmp_path):
        repo_dir = str(tmp_path / "repo")
        _init_repo(repo_dir)

        result = subprocess.run(
            ["sh", SCRIPT_PATH],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "Usage:" in result.stderr

    def test_duplicate_branch_exits_nonzero(self, tmp_path):
        repo_dir = str(tmp_path / "repo")
        _init_repo(repo_dir)

        dispatch_dir = os.path.join(repo_dir, ".agents", "dispatch")
        os.makedirs(dispatch_dir, exist_ok=True)
        with open(os.path.join(dispatch_dir, "dup-task.md"), "w") as f:
            f.write("TARGET: kiro/claude-sonnet-4.5-thinking\n# Dup task dispatch\n")
        _git(["add", "."], cwd=repo_dir)
        _git(["commit", "-m", "add dup dispatch"], cwd=repo_dir)

        # First run — should succeed
        result1 = subprocess.run(
            ["sh", SCRIPT_PATH, "dup-task"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert result1.returncode == 0

        # Remove worktree but keep the branch
        worktree_dir = tmp_path / "attempts" / "dup-task"
        _git(["worktree", "remove", str(worktree_dir), "--force"], cwd=repo_dir)

        # Second run — branch already exists → error
        result2 = subprocess.run(
            ["sh", SCRIPT_PATH, "dup-task"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert result2.returncode != 0
        assert "already exists" in result2.stderr

    def test_not_a_git_repo(self, tmp_path):
        plain_dir = str(tmp_path / "not-a-repo")
        os.makedirs(plain_dir, exist_ok=True)

        result = subprocess.run(
            ["sh", SCRIPT_PATH, "some-task"],
            cwd=plain_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "not inside a git repository" in result.stderr

    def test_target_missing_provider_prefix_exits_nonzero(self, tmp_path):
        repo_dir = str(tmp_path / "repo")
        _init_repo(repo_dir)

        dispatch_dir = os.path.join(repo_dir, ".agents", "dispatch")
        os.makedirs(dispatch_dir, exist_ok=True)
        with open(os.path.join(dispatch_dir, "bare-combo-task.md"), "w") as f:
            f.write("TARGET: claude-sonnet-4.5\n# Bare combo dispatch\n")
        _git(["add", "."], cwd=repo_dir)
        _git(["commit", "-m", "add bare combo dispatch"], cwd=repo_dir)

        result = subprocess.run(
            ["sh", SCRIPT_PATH, "bare-combo-task"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "Error: TARGET 'claude-sonnet-4.5' in dispatch envelope missing provider prefix (must be provider/model)." in result.stderr


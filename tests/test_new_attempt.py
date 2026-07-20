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
    """Exercise the normal success path."""

    def test_creates_worktree_and_branch(self, tmp_path):
        repo_dir = str(tmp_path / "repo")
        _init_repo(repo_dir)

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
        assert "Ready for dispatch." in result.stdout

        # ── Capsule-SHA256 absent case ───────────────────────────────
        assert "no dispatch envelope found" in result.stdout

        # ── Cleanup worktree ─────────────────────────────────────────
        _git(["worktree", "remove", str(worktree_dir), "--force"], cwd=repo_dir)


class TestNewAttemptWithCapsule:
    """Test capsule SHA-256 computation when dispatch file exists."""

    def test_capsule_sha_printed(self, tmp_path):
        repo_dir = str(tmp_path / "repo")
        _init_repo(repo_dir)

        # Create the dispatch envelope
        dispatch_dir = os.path.join(repo_dir, ".agents", "dispatch")
        os.makedirs(dispatch_dir, exist_ok=True)
        dispatch_file = os.path.join(dispatch_dir, "task-capsule.md")
        with open(dispatch_file, "w") as f:
            f.write("# Dispatch envelope for task-capsule\n")
        _git(["add", "."], cwd=repo_dir)
        _git(["commit", "-m", "add dispatch"], cwd=repo_dir)

        result = subprocess.run(
            ["sh", SCRIPT_PATH, "task-capsule"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "Capsule-SHA256:" in result.stdout
        assert "no dispatch envelope found" not in result.stdout

        # The SHA line should have a 12-char hex prefix
        for line in result.stdout.splitlines():
            if line.startswith("Capsule-SHA256:"):
                sha_val = line.split(":", 1)[1].strip()
                assert len(sha_val) == 12, f"Expected 12 hex chars, got: {sha_val!r}"
                assert all(
                    c in "0123456789abcdef" for c in sha_val
                ), f"Non-hex chars in: {sha_val!r}"
                break

        # Cleanup
        worktree_dir = tmp_path / "attempts" / "task-capsule"
        _git(["worktree", "remove", str(worktree_dir), "--force"], cwd=repo_dir)


# ── Error-case tests ─────────────────────────────────────────────────


class TestNewAttemptErrors:
    """Validate that the script fails correctly on bad input."""

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
        """Running outside a git repo should fail."""
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

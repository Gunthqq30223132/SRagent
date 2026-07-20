# tests/test_new_attempt_adversarial.py
"""
Adversarial test suite for scripts/new-attempt.sh
Tests edge cases, injection attempts, and contract violations.
"""
import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary git repository with a valid dispatch envelope."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "noreply@localhost"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    
    # Create dispatch directory structure
    dispatch_dir = repo_dir / ".agents" / "dispatch"
    dispatch_dir.mkdir(parents=True)
    
    return repo_dir


def create_envelope(repo_dir, task_id, content="# Test Capsule\nTest content"):
    """Create and commit a dispatch envelope for the given task_id."""
    envelope_path = repo_dir / ".agents" / "dispatch" / f"{task_id}.md"
    envelope_path.write_text(content)
    
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"Add {task_id} envelope"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )


def get_script_path():
    """Get the absolute path to new-attempt.sh script."""
    # Script is at scripts/new-attempt.sh relative to repo root
    current_file = Path(__file__).resolve()
    repo_root = current_file.parent.parent
    return repo_root / "scripts" / "new-attempt.sh"


def test_dotdot_path_traversal(temp_repo):
    """Test that task-id '..' does not create directories outside attempts/."""
    task_id = ".."
    create_envelope(temp_repo, task_id)
    
    # Capture parent directory contents before
    parent_dir = temp_repo.parent
    before_contents = set(parent_dir.iterdir())
    
    script = get_script_path()
    result = subprocess.run(
        [str(script), task_id],
        cwd=temp_repo,
        capture_output=True,
        text=True,
    )
    
    # Should fail
    assert result.returncode != 0, "Script should reject '..' as task-id"
    
    # Parent directory should be unchanged (only attempts/ subdirectory allowed)
    after_contents = set(parent_dir.iterdir())
    new_items = after_contents - before_contents
    
    # Filter out only the 'attempts' directory if it was created
    unexpected_items = [
        item for item in new_items 
        if item.name != "attempts"
    ]
    
    assert len(unexpected_items) == 0, (
        f"Unexpected items created in parent directory: {unexpected_items}"
    )
    
    # Ensure no worktree at attempts/..
    attempts_dir = parent_dir / "attempts"
    if attempts_dir.exists():
        assert not (attempts_dir / "..").is_dir() or (attempts_dir / "..").resolve() == parent_dir


def test_dot_path_traversal(temp_repo):
    """Test that task-id '.' is rejected with no side effects."""
    task_id = "."
    create_envelope(temp_repo, task_id)
    
    parent_dir = temp_repo.parent
    before_contents = set(parent_dir.iterdir())
    
    script = get_script_path()
    result = subprocess.run(
        [str(script), task_id],
        cwd=temp_repo,
        capture_output=True,
        text=True,
    )
    
    # Should fail
    assert result.returncode != 0, "Script should reject '.' as task-id"
    
    # No side effects
    after_contents = set(parent_dir.iterdir())
    new_items = after_contents - before_contents
    
    # Only 'attempts' directory is allowed
    unexpected_items = [
        item for item in new_items 
        if item.name != "attempts"
    ]
    
    assert len(unexpected_items) == 0, (
        f"Unexpected side effects: {unexpected_items}"
    )


def test_whitespace_in_task_id(temp_repo):
    """Test that task-id with whitespace is rejected with proper error message."""
    task_id = "a b"
    # Don't create envelope since it should fail validation first
    
    script = get_script_path()
    result = subprocess.run(
        [str(script), task_id],
        cwd=temp_repo,
        capture_output=True,
        text=True,
    )
    
    # Should exit with code 1
    assert result.returncode == 1, f"Expected exit code 1, got {result.returncode}"
    
    # Stderr should mention invalid characters
    stderr_lower = result.stderr.lower()
    assert "invalid" in stderr_lower or "character" in stderr_lower, (
        f"Expected error message about invalid characters, got: {result.stderr}"
    )


def test_leading_dash_no_injection(temp_repo):
    """Test that task-id starting with '-' doesn't cause option injection."""
    task_id = "-foo"
    create_envelope(temp_repo, task_id)
    
    script = get_script_path()
    result = subprocess.run(
        [str(script), task_id],
        cwd=temp_repo,
        capture_output=True,
        text=True,
    )
    
    # Should either succeed cleanly or fail cleanly - no traceback/crash
    if result.returncode == 0:
        # If it succeeds, verify the branch was created correctly
        branch_name = f"attempt/{task_id}"
        branch_check = subprocess.run(
            ["git", "branch", "--list", branch_name],
            cwd=temp_repo,
            capture_output=True,
            text=True,
        )
        assert branch_name in branch_check.stdout, (
            f"Expected branch {branch_name} to be created"
        )
        
        # Verify worktree exists at correct location
        attempts_dir = temp_repo.parent / "attempts"
        worktree_path = attempts_dir / task_id
        assert worktree_path.exists(), f"Expected worktree at {worktree_path}"
    else:
        # If it fails, should be a clean failure (exit code 1 or 2)
        assert result.returncode in [1, 2], (
            f"Expected clean exit code 1 or 2, got {result.returncode}"
        )
        
        # No Python traceback or bash errors in output
        combined_output = result.stdout + result.stderr
        assert "Traceback" not in combined_output, (
            "Should not have Python traceback"
        )
        assert "line " not in combined_output.lower() or "error" not in combined_output.lower(), (
            "Should not have bash line errors"
        )


def test_dirty_working_tree_uses_committed_version(temp_repo):
    """Test that SHA-256 is computed from committed version, not working tree."""
    task_id = "test-dirty"
    committed_content = "# Committed Content\nThis is committed"
    create_envelope(temp_repo, task_id, committed_content)
    
    # Now modify the envelope in working tree (dirty)
    envelope_path = temp_repo / ".agents" / "dispatch" / f"{task_id}.md"
    dirty_content = "# Dirty Content\nThis is NOT committed"
    envelope_path.write_text(dirty_content)
    
    # Compute expected SHA-256 from committed version
    git_show_result = subprocess.run(
        ["git", "show", f"HEAD:.agents/dispatch/{task_id}.md"],
        cwd=temp_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    committed_bytes = git_show_result.stdout.encode('utf-8')
    expected_sha = hashlib.sha256(committed_bytes).hexdigest()[:12]
    
    # Run the script
    script = get_script_path()
    result = subprocess.run(
        [str(script), task_id],
        cwd=temp_repo,
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    
    # Extract SHA from output
    match = re.search(r"Capsule-SHA256:\s*([0-9a-f]+)", result.stdout)
    assert match, f"Could not find Capsule-SHA256 in output: {result.stdout}"
    
    actual_sha = match.group(1)
    assert actual_sha == expected_sha, (
        f"SHA mismatch: expected {expected_sha} (from committed version), "
        f"got {actual_sha}"
    )


def test_output_format_validation(temp_repo):
    """Test that Capsule-SHA256 output has exactly 12 lowercase hex characters."""
    task_id = "format-test"
    create_envelope(temp_repo, task_id)
    
    script = get_script_path()
    result = subprocess.run(
        [str(script), task_id],
        cwd=temp_repo,
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    
    # Find the Capsule-SHA256 line
    match = re.search(r"Capsule-SHA256:\s*([0-9a-f]+)", result.stdout)
    assert match, f"Could not find Capsule-SHA256 in output: {result.stdout}"
    
    sha_value = match.group(1)
    
    # Verify exactly 12 characters
    assert len(sha_value) == 12, (
        f"Expected 12 hex characters, got {len(sha_value)}: {sha_value}"
    )
    
    # Verify all lowercase hex
    assert re.fullmatch(r"[0-9a-f]{12}", sha_value), (
        f"Expected lowercase hex characters only, got: {sha_value}"
    )


def test_missing_committed_envelope_fails(temp_repo):
    """Test that script fails when envelope is not committed."""
    task_id = "not-committed"
    
    # Create envelope but don't commit it
    envelope_path = temp_repo / ".agents" / "dispatch" / f"{task_id}.md"
    envelope_path.write_text("# Uncommitted Content")
    
    script = get_script_path()
    result = subprocess.run(
        [str(script), task_id],
        cwd=temp_repo,
        capture_output=True,
        text=True,
    )
    
    # Should fail with exit code 1
    assert result.returncode == 1, (
        f"Expected exit code 1 for missing committed envelope, got {result.returncode}"
    )


def test_existing_branch_fails(temp_repo):
    """Test that script fails when branch already exists."""
    task_id = "existing-branch"
    create_envelope(temp_repo, task_id)
    
    # Create the branch manually
    branch_name = f"attempt/{task_id}"
    subprocess.run(
        ["git", "branch", branch_name],
        cwd=temp_repo,
        check=True,
        capture_output=True,
    )
    
    script = get_script_path()
    result = subprocess.run(
        [str(script), task_id],
        cwd=temp_repo,
        capture_output=True,
        text=True,
    )
    
    # Should fail with exit code 1
    assert result.returncode == 1, (
        f"Expected exit code 1 for existing branch, got {result.returncode}"
    )

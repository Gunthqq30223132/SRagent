"""
Adversarial test suite for scripts/new-attempt.sh

Tests edge cases and security boundaries without modifying the script itself.
Each test uses an isolated temporary git repository.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


def run_script(repo_path: Path, task_id: str) -> subprocess.CompletedProcess:
    """Execute new-attempt.sh in the given repository context."""
    script_path = Path(__file__).parent.parent / "scripts" / "new-attempt.sh"
    result = subprocess.run(
        ["bash", str(script_path), task_id],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return result


def setup_repo_with_capsule(tmp_path: Path, task_id: str, content: str) -> Path:
    """Create a git repo with a committed dispatch capsule."""
    repo = tmp_path / "repo"
    repo.mkdir()
    
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "noreply@localhost"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    
    # Create dispatch capsule
    capsule_dir = repo / ".agents" / "dispatch"
    capsule_dir.mkdir(parents=True)
    capsule_file = capsule_dir / f"{task_id}.md"
    capsule_file.write_text(content)
    
    # Commit the capsule
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add capsule"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    
    return repo


def get_committed_capsule_sha256(repo: Path, task_id: str) -> str:
    """Calculate SHA-256 of the committed capsule file."""
    result = subprocess.run(
        ["git", "show", f"HEAD:.agents/dispatch/{task_id}.md"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    return hashlib.sha256(result.stdout).hexdigest()[:12]


def test_dotdot_path_traversal_no_side_effects(tmp_path):
    """
    Test case 1: task-id '..' should not create directories outside attempts/
    """
    repo = setup_repo_with_capsule(tmp_path, "..", "# Test capsule\n")
    parent_before = set(tmp_path.iterdir())
    
    result = run_script(repo, "..")
    
    assert result.returncode != 0, "Script should reject '..' task-id"
    
    # Verify no new directories created in parent
    parent_after = set(tmp_path.iterdir())
    new_items = parent_after - parent_before
    
    # Only 'attempts' dir is allowed if created
    attempts_dir = tmp_path / "attempts"
    if attempts_dir in new_items:
        # If attempts exists, verify it's empty or doesn't contain dangerous paths
        if attempts_dir.exists():
            attempts_contents = list(attempts_dir.iterdir())
            assert len(attempts_contents) == 0 or all(
                item.name != ".."
                for item in attempts_contents
            ), "No '..' worktree should be created"
    else:
        # Ideally nothing should be created
        assert len(new_items) == 0, f"Unexpected items created: {new_items}"


def test_dot_current_directory_rejection(tmp_path):
    """
    Test case 2: task-id '.' should fail without side effects
    """
    repo = setup_repo_with_capsule(tmp_path, ".", "# Test capsule\n")
    
    result = run_script(repo, ".")
    
    assert result.returncode != 0, "Script should reject '.' task-id"
    
    # Verify no worktree created
    attempts_dir = tmp_path / "attempts"
    if attempts_dir.exists():
        contents = list(attempts_dir.iterdir())
        assert len(contents) == 0, "No worktree should be created for '.'"


def test_whitespace_in_task_id(tmp_path):
    """
    Test case 3: task-id with whitespace should exit 1 with error message
    """
    task_id = "a b"
    repo = setup_repo_with_capsule(tmp_path, task_id, "# Test capsule\n")
    
    result = run_script(repo, task_id)
    
    assert result.returncode == 1, "Should exit 1 for invalid characters"
    assert "invalid" in result.stderr.lower() or "character" in result.stderr.lower(), \
        "stderr should mention invalid characters"


def test_leading_dash_no_option_injection(tmp_path):
    """
    Test case 4: task-id starting with '-' should not cause option injection
    Should either succeed creating attempt/-foo or fail cleanly (exit != 0)
    """
    task_id = "-foo"
    content = "# Test capsule for -foo\n"
    repo = setup_repo_with_capsule(tmp_path, task_id, content)
    
    result = run_script(repo, task_id)
    
    # Accept either success or clean failure, but no crashes/tracebacks
    if result.returncode == 0:
        # If successful, verify worktree was created correctly
        attempts_dir = tmp_path / "attempts"
        worktree_path = attempts_dir / task_id
        assert worktree_path.exists(), f"Worktree should exist at {worktree_path}"
        
        # Verify branch exists
        branch_check = subprocess.run(
            ["git", "branch", "--list", f"attempt/{task_id}"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        assert f"attempt/{task_id}" in branch_check.stdout, "Branch should exist"
    else:
        # If failed, should be clean exit without crash
        assert result.returncode in [1, 2], \
            f"Should exit cleanly with 1 or 2, got {result.returncode}"
        # Should not contain bash errors or tracebacks
        combined_output = result.stdout + result.stderr
        assert "line" not in combined_output.lower() or "error" in combined_output.lower(), \
            "Should not have bash line errors"


def test_dirty_working_tree_uses_committed_version(tmp_path):
    """
    Test case 5: Modified capsule in working tree should not affect SHA output
    Output SHA must match the committed version, not the working tree version
    """
    task_id = "test-dirty"
    committed_content = "# Original committed content\n"
    modified_content = "# Modified working tree content\n"
    
    repo = setup_repo_with_capsule(tmp_path, task_id, committed_content)
    
    # Calculate expected SHA from committed version
    expected_sha = get_committed_capsule_sha256(repo, task_id)
    
    # Modify the capsule in working tree (make it dirty)
    capsule_file = repo / ".agents" / "dispatch" / f"{task_id}.md"
    capsule_file.write_text(modified_content)
    
    # Verify working tree is dirty
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert status.stdout.strip() != "", "Working tree should be dirty"
    
    # Run script
    result = run_script(repo, task_id)
    
    assert result.returncode == 0, f"Script should succeed: {result.stderr}"
    
    # Extract SHA from output
    output_lines = result.stdout.strip().split("\n")
    sha_line = [line for line in output_lines if "Capsule-SHA256:" in line]
    assert len(sha_line) == 1, "Should have exactly one Capsule-SHA256 line"
    
    output_sha = sha_line[0].split(":")[-1].strip()
    
    assert output_sha == expected_sha, \
        f"SHA should match committed version: expected {expected_sha}, got {output_sha}"


def test_sha_output_format(tmp_path):
    """
    Test case 6: Capsule-SHA256 output format validation
    Should contain exactly 12 lowercase hex characters
    """
    task_id = "format-test"
    content = "# Test capsule for format validation\n"
    repo = setup_repo_with_capsule(tmp_path, task_id, content)
    
    result = run_script(repo, task_id)
    
    assert result.returncode == 0, f"Script should succeed: {result.stderr}"
    
    # Find the SHA line
    sha_line = None
    for line in result.stdout.strip().split("\n"):
        if "Capsule-SHA256:" in line:
            sha_line = line
            break
    
    assert sha_line is not None, "Output should contain Capsule-SHA256 line"
    
    # Extract SHA value
    sha_value = sha_line.split(":")[-1].strip()
    
    # Validate format: exactly 12 hex characters, lowercase
    assert len(sha_value) == 12, f"SHA should be 12 characters, got {len(sha_value)}"
    assert sha_value.islower(), "SHA should be lowercase"
    assert all(c in "0123456789abcdef" for c in sha_value), \
        f"SHA should only contain hex characters, got {sha_value}"

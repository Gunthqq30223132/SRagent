import hashlib
import os
import subprocess
import pytest
from pathlib import Path


class TestNewAttemptAdversarial:
    """Adversarial tests for scripts/new-attempt.sh"""

    @pytest.fixture
    def temp_repo(self, tmp_path):
        """Create a clean temporary git repository with the script available."""
        repo = tmp_path / "repo"
        repo.mkdir()
        
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "noreply@localhost"],
            cwd=repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo, check=True, capture_output=True
        )
        
        # Copy the script into the temp repo
        script_src = Path(__file__).parent.parent / "scripts" / "new-attempt.sh"
        script_dst = repo / "scripts"
        script_dst.mkdir(parents=True)
        (script_dst / "new-attempt.sh").write_text(script_src.read_text())
        
        # Make script executable
        os.chmod(script_dst / "new-attempt.sh", 0o755)
        
        return repo

    def _create_envelope(self, repo: Path, task_id: str, content: str = "test envelope"):
        """Create and commit a dispatch envelope file."""
        envelope_path = repo / ".agents" / "dispatch" / f"{task_id}.md"
        envelope_path.parent.mkdir(parents=True, exist_ok=True)
        if "TARGET:" not in content:
            content = "TARGET: kiro/claude-sonnet-4.5-thinking\n" + content
        envelope_path.write_text(content)
        
        subprocess.run(["git", "add", str(envelope_path)], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"Add envelope for {task_id}"],
            cwd=repo, check=True, capture_output=True
        )
        
        return envelope_path

    def _get_committed_sha256(self, repo: Path, task_id: str) -> str:
        """Get SHA-256 of committed envelope file."""
        result = subprocess.run(
            ["git", "show", f"HEAD:.agents/dispatch/{task_id}.md"],
            cwd=repo, check=True, capture_output=True, text=True
        )
        return hashlib.sha256(result.stdout.encode()).hexdigest()[:12]

    def _run_script(self, repo: Path, task_id: str):
        """Run the new-attempt.sh script and return result."""
        return subprocess.run(
            ["./scripts/new-attempt.sh", task_id],
            cwd=repo,
            capture_output=True,
            text=True
        )

    def test_dotdot_task_id_no_directory_traversal(self, temp_repo):
        """task-id '..' should exit ≠ 0 and NOT create anything outside attempts/"""
        repo = temp_repo
        parent_dir = repo.parent
        
        # Snapshot parent directory contents before
        before = set(parent_dir.iterdir())
        
        result = self._run_script(repo, "..")
        
        # Should fail
        assert result.returncode != 0, "Script should reject '..' task-id"
        
        # Parent directory should be unchanged (no traversal)
        after = set(parent_dir.iterdir())
        assert after == before, "Parent directory should not be modified"
        
        # attempts directory should not exist or be empty if it exists
        attempts_dir = parent_dir / "attempts"
        if attempts_dir.exists():
            assert list(attempts_dir.iterdir()) == [], "No worktrees should be created"

    def test_dot_task_id_no_side_effects(self, temp_repo):
        """task-id '.' should exit ≠ 0 with no side effects"""
        repo = temp_repo
        parent_dir = repo.parent
        
        # Snapshot before
        before_parent = set(parent_dir.iterdir())
        before_repo = set(repo.rglob("*"))
        
        result = self._run_script(repo, ".")
        
        # Should fail
        assert result.returncode != 0, "Script should reject '.' task-id"
        
        # No side effects
        after_parent = set(parent_dir.iterdir())
        after_repo = set(repo.rglob("*"))
        
        assert after_parent == before_parent, "Parent directory unchanged"
        assert after_repo == before_repo, "Repository unchanged"

    def test_whitespace_in_task_id_rejected(self, temp_repo):
        """task-id with whitespace should exit 1 with error message"""
        repo = temp_repo
        
        result = self._run_script(repo, "a b")
        
        assert result.returncode == 1, "Should exit 1 for invalid characters"
        assert "invalid" in result.stderr.lower() or "character" in result.stderr.lower(), \
            "stderr should mention invalid characters"

    def test_leading_dash_no_option_injection(self, temp_repo):
        """task-id starting with '-' should not cause option injection"""
        repo = temp_repo
        task_id = "-foo"
        
        # Create valid committed envelope
        self._create_envelope(repo, task_id, "test content for -foo")
        
        result = self._run_script(repo, task_id)
        
        # Should either succeed cleanly or fail cleanly (no traceback)
        assert "Traceback" not in result.stderr, "Should not have Python traceback"
        assert "error:" not in result.stderr.lower() or result.returncode != 0, \
            "Should handle gracefully"
        
        if result.returncode == 0:
            # If succeeded, verify correct worktree was created
            worktree_path = repo.parent / "attempts" / task_id
            assert worktree_path.exists(), f"Worktree should exist at {worktree_path}"
            
            # Verify branch name
            branch_result = subprocess.run(
                ["git", "branch", "--list", f"attempt/{task_id}"],
                cwd=repo, capture_output=True, text=True
            )
            assert f"attempt/{task_id}" in branch_result.stdout, \
                "Branch attempt/-foo should exist"
        else:
            # If failed, should be a clean exit (documented in contract)
            assert result.returncode in (1, 2), \
                "Should exit with documented error code"

    def test_dirty_working_tree_uses_committed_version(self, temp_repo):
        """SHA should match committed version, not dirty working tree"""
        repo = temp_repo
        task_id = "test-dirty"
        
        # Create and commit initial envelope
        original_content = "original committed content"
        envelope_path = self._create_envelope(repo, task_id, original_content)
        
        # Get expected SHA from committed version
        expected_sha = self._get_committed_sha256(repo, task_id)
        
        # Modify envelope in working tree (make it dirty)
        envelope_path.write_text("MODIFIED CONTENT NOT COMMITTED")
        
        # Verify working tree is dirty
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo, capture_output=True, text=True
        )
        assert envelope_path.name in status.stdout, "Working tree should be dirty"
        
        result = self._run_script(repo, task_id)
        
        assert result.returncode == 0, "Should succeed with dirty working tree"
        
        # Extract SHA from output
        output_lines = result.stdout.strip().split("\n")
        sha_line = [line for line in output_lines if "Capsule-SHA256:" in line]
        assert len(sha_line) == 1, "Should have exactly one SHA line"
        
        actual_sha = sha_line[0].split("Capsule-SHA256:")[1].strip()
        
        assert actual_sha == expected_sha, \
            f"SHA should match committed version: expected {expected_sha}, got {actual_sha}"

    def test_output_format_exactly_12_hex_lowercase(self, temp_repo):
        """Output should contain 'Capsule-SHA256:' with exactly 12 lowercase hex chars"""
        repo = temp_repo
        task_id = "test-format"
        
        # Create committed envelope
        self._create_envelope(repo, task_id, "test content for format check")
        
        result = self._run_script(repo, task_id)
        
        assert result.returncode == 0, "Should succeed"
        
        # Find the SHA line
        output_lines = result.stdout.strip().split("\n")
        sha_line = [line for line in output_lines if "Capsule-SHA256:" in line]
        assert len(sha_line) == 1, "Should have exactly one SHA line"
        
        # Extract SHA value
        sha_value = sha_line[0].split("Capsule-SHA256:")[1].strip()
        
        # Verify format: exactly 12 characters, all lowercase hex
        assert len(sha_value) == 12, f"SHA should be exactly 12 characters, got {len(sha_value)}"
        assert sha_value.islower(), "SHA should be lowercase"
        assert all(c in "0123456789abcdef" for c in sha_value), \
            "SHA should contain only hex characters (0-9a-f)"

# RED divergence

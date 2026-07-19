import os
import sys
import subprocess
import pytest

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
HARNESS_PY = os.path.join(REPO_DIR, "scripts", "agent-qc-harness.py")

def test_path_guard_rejects_tier3_path(tmp_path):
    # Create dummy patch touching .agents/gates.yml
    patch_file = tmp_path / "violation_tier3.patch"
    patch_content = """--- a/gates.yml
+++ b/gates.yml
@@ -1,3 +1,3 @@
-# fake patch
+# touched by worker
"""
    patch_file.write_text(patch_content)
    
    cmd = [sys.executable, HARNESS_PY, "--patch", str(patch_file), "--role", "worker"]
    proc = subprocess.run(cmd, cwd=REPO_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    assert proc.returncode != 0
    assert "PRE-FLIGHT REJECTED" in proc.stderr
    assert "Tier-3 Path Guard" in proc.stderr

def test_oracle_rule_rejects_fixer_modifying_test_file(tmp_path):
    # Create dummy patch modifying a test file
    patch_file = tmp_path / "violation_oracle.patch"
    patch_content = """--- a/tests/test_guards.py
+++ b/tests/test_guards.py
@@ -1,3 +1,3 @@
-# fake test patch
+# modified expected value
"""
    patch_file.write_text(patch_content)
    
    cmd = [sys.executable, HARNESS_PY, "--patch", str(patch_file), "--role", "fixer"]
    proc = subprocess.run(cmd, cwd=REPO_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    assert proc.returncode != 0
    assert "PRE-FLIGHT REJECTED" in proc.stderr
    assert "Oracle Rule Guard" in proc.stderr

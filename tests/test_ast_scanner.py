"""Tests cho AST Scanner — broad except, silent clamping, gate file protection."""

import ast
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.guard.ast_scanner import (
    scan_file,
    scan_directory,
    check_gate_file_modifications,
    ASTViolation,
    GATE_FILES,
)


def _write_temp_py(code: str) -> Path:
    """Helper: write code to a temp .py file."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
    f.write(code)
    f.close()
    return Path(f.name)


# ============ VIOLATION SAMPLES ============

BROAD_EXCEPT_CODE = '''
def verify_evidence(data):
    try:
        result = extract_claims(data)
    except:
        pass
'''

SILENT_CLAMP_CODE = '''
def get_coverage(source):
    try:
        score = compute_coverage(source)
    except Exception:
        score = 1.0  # silent default
        return score
    return score
'''

BROAD_EXCEPT_WITH_RAISE = '''
def safe_function(data):
    try:
        result = process(data)
    except Exception as e:
        log(e)
        raise
'''

CLEAN_CODE = '''
def calculate_ibw(height_cm: float) -> float:
    if height_cm <= 0:
        raise ValueError("Invalid height")
    return 50 + 2.3 * ((height_cm / 2.54) - 60)
'''


def test_broad_except_detected():
    """Bare except without raise phải bị phát hiện."""
    path = _write_temp_py(BROAD_EXCEPT_CODE)
    violations = scan_file(path)
    assert len(violations) >= 1, f"Should detect broad except, got {len(violations)}"
    assert violations[0].rule == "BROAD_EXCEPT"
    path.unlink()


def test_silent_clamp_detected():
    """Except Exception gán default KHÔNG raise phải bị phát hiện."""
    path = _write_temp_py(SILENT_CLAMP_CODE)
    violations = scan_file(path)
    assert len(violations) >= 1, f"Should detect silent clamp, got {len(violations)}"
    assert violations[0].rule == "SILENT_CLAMP"
    path.unlink()


def test_broad_except_with_raise_ok():
    """Except Exception CÓ raise KHÔNG phải là vi phạm."""
    path = _write_temp_py(BROAD_EXCEPT_WITH_RAISE)
    violations = scan_file(path)
    assert len(violations) == 0, f"Should not flag except with raise, got {violations}"
    path.unlink()


def test_clean_code_passes():
    """Code sạch KHÔNG có vi phạm."""
    path = _write_temp_py(CLEAN_CODE)
    violations = scan_file(path)
    assert len(violations) == 0, f"Clean code should have 0 violations, got {violations}"
    path.unlink()


def test_gate_file_protection():
    """Sửa file gate phải bị chặn."""
    changed = ["sr_agent/main.py", "tools/guard/firewall.py", "dev_gate.py"]
    violations = check_gate_file_modifications(changed)
    assert len(violations) == 2, f"Should detect 2 gate files modified, got {len(violations)}"
    assert all(v.rule == "GATE_FILE_MODIFIED" for v in violations)


def test_gate_file_normal_changes_ok():
    """Sửa file bình thường KHÔNG bị chặn."""
    changed = ["sr_agent/pipeline.py", "tests/test_new.py"]
    violations = check_gate_file_modifications(changed)
    assert len(violations) == 0, f"Normal files should not trigger gate check"


if __name__ == "__main__":
    test_broad_except_detected()
    test_silent_clamp_detected()
    test_broad_except_with_raise_ok()
    test_clean_code_passes()
    test_gate_file_protection()
    test_gate_file_normal_changes_ok()
    print("\n✅ All AST Scanner tests passed!")

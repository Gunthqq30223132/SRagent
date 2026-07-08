#!/bin/bash
set -euo pipefail

echo "=========================================="
echo "RUNNING SPRINT M6 VERIFICATION GATE"
echo "=========================================="

FAILED=0

# Use venv python if available, otherwise fallback to system python
PYTHON_CMD="python"
if [ -d ".venv" ] && [ -f ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
fi

# --- G1: Code integrity and core boundaries ---
echo "--- G1: Running Pytest full suite ---"
if $PYTHON_CMD -m pytest; then
    echo "[PASS] Pytest full suite"
else
    echo "[FAIL] Pytest full suite"
    FAILED=1
fi

BASE_REF="origin/claude/sr-agent-pipeline-design-rqtctp"
if git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
    echo "--- G1: Checking git diff against design branch ($BASE_REF) ---"
    
    # Check core files zero-touch
    CORE_DIFF=$(git diff "$BASE_REF" -- sr_agent/ingest/ sr_agent/config.py sr_agent/models/schemas.py sr_agent/pipeline.py)
    if [ -z "$CORE_DIFF" ]; then
        echo "[PASS] Core files zero-touch check"
    else
        echo "[FAIL] Core files zero-touch check - diff is not empty!"
        echo "$CORE_DIFF"
        FAILED=1
    fi

    # Check pyproject.toml zero-touch
    DEPS_DIFF=$(git diff "$BASE_REF" -- pyproject.toml)
    if [ -z "$DEPS_DIFF" ]; then
        echo "[PASS] Dependencies zero-touch check"
    else
        echo "[FAIL] Dependencies zero-touch check - pyproject.toml modified!"
        echo "$DEPS_DIFF"
        FAILED=1
    fi
else
    echo "--- G1: Base reference ($BASE_REF) not available, skipping git diff checks ---"
fi

# Check domain leaks into core
echo "--- G1: Checking for domain terminology leaks inside core sr_agent/ ---"
if grep -rn "population\|intervention\|topic_vi" sr_agent/ >/dev/null 2>&1; then
    echo "[FAIL] Domain terminology leaked into core sr_agent/ !"
    grep -rn "population\|intervention\|topic_vi" sr_agent/
    FAILED=1
else
    echo "[PASS] Domain terminology zero-leak check"
fi


# --- G2: Test suite discipline ---
echo "--- G2: Checking for bypassed tests (assert True / skip / xfail) ---"
if grep -rn "assert True\|mark\.skip\|mark\.xfail" tests/ >/dev/null 2>&1; then
    echo "[FAIL] Bypassed tests detected in tests/ !"
    grep -rn "assert True\|mark\.skip\|mark\.xfail" tests/
    FAILED=1
else
    echo "[PASS] No bypassed tests"
fi

# Ratio count on new test files
echo "--- G2: Verifying assert-to-test ratio in new test files ---"
NEW_TEST_FILES=(
    "tests/test_protocol.py"
    "tests/test_screening.py"
    "tests/test_extraction.py"
    "tests/test_prisma_report.py"
    "tests/test_m6_hotfix.py"
)

for file in "${NEW_TEST_FILES[@]}"; do
    if [ -f "$file" ]; then
        test_count=$(grep -c "def test_" "$file" || true)
        assert_count=$(grep -c "assert " "$file" || true)
        if [ "$test_count" -gt 0 ]; then
            ratio=$($PYTHON_CMD -c "print($assert_count / $test_count)")
            if $PYTHON_CMD -c "exit(1 if $ratio < 1.0 else 0)"; then
                echo "[PASS] $file assert/test ratio: $ratio"
            else
                echo "[FAIL] $file has assert/test ratio of $ratio (< 1.0)"
                FAILED=1
            fi
        else
            echo "[WARNING] $file has no tests defined"
        fi
    fi
done

echo "--- G2: Total test cases count ---"
$PYTHON_CMD -m pytest --collect-only -q

# Final verdict
if [ "$FAILED" -ne 0 ]; then
    echo "=========================================="
    echo "[FAIL] Sprint M6 verification FAILED!"
    echo "=========================================="
    exit 1
else
    echo "=========================================="
    echo "[PASS] Sprint M6 verification PASSED!"
    echo "=========================================="
    exit 0
fi

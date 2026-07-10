#!/bin/bash
set -euo pipefail

echo "=========================================="
echo "RUNNING D32 COMPLIANCE-OS VERIFICATION GATE"
echo "=========================================="

FAILED=0

PYTHON_CMD="python"
if [ -d ".venv" ] && [ -f ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
fi

# --- D1: Test suite compliance + guard nguyên trạng ---
echo "--- D1: Pytest compliance + guard suites ---"
if $PYTHON_CMD -m pytest tests/test_compliance_layer_a.py tests/test_compliance_kb.py \
    tests/test_compliance_agents.py tests/test_compliance_scenarios.py tests/test_guards.py -q; then
    echo "[PASS] Compliance + guard test suites"
else
    echo "[FAIL] Compliance + guard test suites"
    FAILED=1
fi

# --- D2: tools/guard/ zero-touch (Agent-V/R chỉ được IMPORT, không được SỬA) ---
BASE_REF="origin/claude/sr-agent-pipeline-design-rqtctp"
if git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
    echo "--- D2: Checking tools/guard/ zero-touch vs $BASE_REF ---"
    GUARD_DIFF=$(git diff "$BASE_REF" -- tools/guard/)
    if [ -z "$GUARD_DIFF" ]; then
        echo "[PASS] tools/guard/ zero-touch"
    else
        echo "[FAIL] tools/guard/ modified!"
        echo "$GUARD_DIFF"
        FAILED=1
    fi

    DEPS_DIFF=$(git diff "$BASE_REF" -- pyproject.toml)
    if [ -z "$DEPS_DIFF" ]; then
        echo "[PASS] Dependencies zero-touch"
    else
        echo "[FAIL] pyproject.toml modified!"
        FAILED=1
    fi
else
    echo "--- D2: Base reference not available, skipping diff checks ---"
fi

# --- D3: CẤM cosine/fuzzy trong đường verify (chỉ kb.py được dùng cosine cho recall).
# Grep theo TÊN API thật (import/call) chứ không theo khái niệm — docstring được phép
# nhắc tới từ "cosine" khi tuyên bố lệnh cấm.
echo "--- D3: No cosine/fuzzy in verification path ---"
if grep -n "cosine_similarity\|difflib\|SequenceMatcher\|rapidfuzz\|fuzzywuzzy\|\.ratio(" \
    tools/compliance/reconcile.py tools/compliance/assertions.py 2>/dev/null; then
    echo "[FAIL] Fuzzy/cosine matching detected in verification path!"
    FAILED=1
else
    echo "[PASS] Verification path is exact-match only"
fi

# --- D4: assert/test ratio trên các file test compliance ---
echo "--- D4: assert-to-test ratio on compliance test files ---"
for file in tests/test_compliance_layer_a.py tests/test_compliance_kb.py \
    tests/test_compliance_agents.py tests/test_compliance_scenarios.py; do
    if [ -f "$file" ]; then
        test_count=$(grep -c "def test_" "$file" || true)
        assert_count=$(grep -c "assert " "$file" || true)
        if [ "$test_count" -gt 0 ]; then
            ratio=$($PYTHON_CMD -c "print($assert_count / $test_count)")
            if $PYTHON_CMD -c "exit(1 if $ratio < 1.0 else 0)"; then
                echo "[PASS] $file assert/test ratio: $ratio"
            else
                echo "[FAIL] $file assert/test ratio: $ratio (< 1.0)"
                FAILED=1
            fi
        fi
    fi
done

if [ "$FAILED" -ne 0 ]; then
    echo "=========================================="
    echo "[FAIL] D32 verification FAILED!"
    echo "=========================================="
    exit 1
else
    echo "=========================================="
    echo "[PASS] D32 verification PASSED!"
    echo "=========================================="
    exit 0
fi

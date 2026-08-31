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

# Base ref để đối chiếu vùng cấm. Override khi cần: SR_GATE_BASE_REF=<ref> bash scripts/gate_m6.sh
BASE_REF="${SR_GATE_BASE_REF:-origin/main}"

# FAIL-CLOSED: không phân giải được base ref thì KHÔNG kiểm được vùng cấm.
# Không kiểm được != đạt. Trước đây nhánh này 'skip' rồi vẫn cho PASS — cổng PASS rỗng.
if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
    echo "[FAIL] G1: base ref '$BASE_REF' không phân giải được."
    echo "       Không kiểm được vùng cấm KHÔNG có nghĩa là đạt — cổng đóng."
    echo "       Khắc phục: git fetch origin, hoặc đặt SR_GATE_BASE_REF=<ref hợp lệ>."
    exit 1
fi

echo "--- G1: Checking git diff against base ref ($BASE_REF) ---"

# Check core files zero-touch.
#
# Nền đối chiếu là "bản ĐÃ DUYỆT gần nhất", không phải bản gốc. Một thay đổi đã có
# quyết định trong docs/DECISIONS.md thì không báo động lại — nhưng nếu nó ĐỔI TIẾP
# sau khi duyệt thì phải báo động ngay. Nội dung đã duyệt ghi bằng băm sha256 trong
# scripts/vung_cam_da_duyet.tsv.
DANH_SACH_DUYET="scripts/vung_cam_da_duyet.tsv"

# FAIL-CLOSED: mất danh sách thì KHÔNG kiểm được vùng cấm. Không kiểm được != đạt.
if [ ! -f "$DANH_SACH_DUYET" ]; then
    echo "[FAIL] G1: thiếu $DANH_SACH_DUYET — không kiểm được nền đã duyệt của vùng cấm."
    echo "       Không kiểm được vùng cấm KHÔNG có nghĩa là đạt — cổng đóng."
    exit 1
fi

CORE_CHANGED=$(git diff --name-only "$BASE_REF" -- sr_agent/ingest/ sr_agent/config.py sr_agent/models/schemas.py sr_agent/pipeline.py)

if [ -z "$CORE_CHANGED" ]; then
    echo "[PASS] Core files zero-touch check"
else
    CORE_FAILED=0
    while IFS= read -r tep; do
        [ -z "$tep" ] && continue

        if [ ! -f "$tep" ]; then
            echo "[FAIL] Vùng cấm: $tep đã bị XOÁ so với $BASE_REF"
            CORE_FAILED=1
            continue
        fi

        bam_hien_tai=$(sha256sum "$tep" | cut -d' ' -f1)
        dong=$(awk -F'\t' -v f="$tep" '!/^[[:space:]]*#/ && $1==f {print; exit}' "$DANH_SACH_DUYET")

        if [ -z "$dong" ]; then
            echo "[FAIL] Vùng cấm: $tep khác $BASE_REF nhưng KHÔNG có trong $DANH_SACH_DUYET"
            echo "       Thay đổi chưa được duyệt — cần quyết định trong docs/DECISIONS.md trước."
            CORE_FAILED=1
            continue
        fi

        bam_duyet=$(printf '%s' "$dong" | awk -F'\t' '{print $2}')
        ly_do=$(printf '%s' "$dong" | awk -F'\t' '{print $3}')

        if [ "$bam_hien_tai" = "$bam_duyet" ]; then
            echo "[PASS] Vùng cấm: $tep khác $BASE_REF — ĐÃ DUYỆT ($ly_do)"
        else
            echo "[FAIL] Vùng cấm: $tep ĐÃ SỬA THÊM sau khi được duyệt"
            echo "       băm đã duyệt : $bam_duyet"
            echo "       băm hiện tại : $bam_hien_tai"
            echo "       Cho phép trước đó: $ly_do"
            CORE_FAILED=1
        fi
    done <<< "$CORE_CHANGED"

    if [ "$CORE_FAILED" -ne 0 ]; then
        FAILED=1
    fi
fi

# Mục thừa trong danh sách: tệp hết khác bản gốc mà vẫn còn dòng cho phép.
# Cảnh báo, KHÔNG trượt — mục thừa không nới lỏng gì, chỉ gây hiểu nhầm khi đọc.
while IFS=$'\t' read -r tep _bam _ly_do; do
    case "$tep" in ''|\#*) continue ;; esac
    if ! printf '%s\n' "$CORE_CHANGED" | grep -qxF "$tep"; then
        echo "[WARNING] $DANH_SACH_DUYET còn dòng cho $tep nhưng tệp đã hết khác $BASE_REF — nên dọn"
    fi
done < "$DANH_SACH_DUYET"

# Check pyproject.toml zero-touch
DEPS_DIFF=$(git diff "$BASE_REF" -- pyproject.toml)
if [ -z "$DEPS_DIFF" ]; then
    echo "[PASS] Dependencies zero-touch check"
else
    echo "[FAIL] Dependencies zero-touch check - pyproject.toml modified!"
    echo "$DEPS_DIFF"
    FAILED=1
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

# Ratio count on test files.
#
# Trước đây chỉ soi 5 tệp ghi tên cứng từ chặng M6. Kho đã có nhiều tệp hơn hẳn, nên
# 5 tên cứng nghĩa là phần lớn tệp không ai soi — và mọi tệp viết sau đó cũng không.
# Soi toàn bộ tests/test_*.py: đã đo, mọi tệp hiện có đều >= 1,00 nên mở rộng không
# làm cổng đỏ oan, mà lại áp được cho việc mới về sau.
echo "--- G2: Verifying assert-to-test ratio across ALL test files ---"
RATIO_CHECKED=0

for file in tests/test_*.py; do
    if [ -f "$file" ]; then
        RATIO_CHECKED=$((RATIO_CHECKED + 1))
        test_count=$(grep -c "def test_" "$file" || true)
        # Đếm cả pytest.raises / pytest.warns / mock .assert_*: chúng LÀ khẳng định,
        # chỉ là không chứa chữ "assert ". Phép đếm cũ chỉ grep "assert " nên phạt oan
        # đúng lối viết tốt hơn — khẳng định rằng đầu vào xấu phải NÉM LỖI, thay vì
        # khẳng định trên giá trị trả về.
        assert_count=$(grep -cE "assert |pytest\.raises|pytest\.warns|\.assert_" "$file" || true)
        if [ "$test_count" -gt 0 ]; then
            ratio=$($PYTHON_CMD -c "print($assert_count / $test_count)")
            # Chỉ in tệp TRƯỢT. In cả tệp đạt thì 39 dòng xanh sẽ dìm mất dòng đỏ.
            if ! $PYTHON_CMD -c "exit(1 if $ratio < 1.0 else 0)"; then
                echo "[FAIL] $file has assert/test ratio of $ratio (< 1.0)"
                FAILED=1
                RATIO_FAILED=$((${RATIO_FAILED:-0} + 1))
            fi
        else
            echo "[WARNING] $file has no tests defined"
        fi
    fi
done

if [ "${RATIO_FAILED:-0}" -eq 0 ]; then
    echo "[PASS] assert/test ratio >= 1.0 trên toàn bộ $RATIO_CHECKED tệp kiểm thử"
fi

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

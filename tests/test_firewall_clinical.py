"""Test miền LÂM SÀNG của Numeric Firewall.

File riêng, KHÔNG sửa tests/test_guards.py: hợp đồng miền CS phải giữ nguyên
byte-for-byte, và cách chứng minh điều đó là để nguyên bộ test cũ rồi cộng thêm
bộ mới. Mọi test ở đây gọi check_output(..., domain="clinical").

Bối cảnh: probe trước khi vá cho thấy văn bản 'Enoxaparin 40 mg, ngưng 12 giờ,
INR 1.5' bóc được 0 mỏ neo và PASS sạch — firewall V24 gốc chỉ biết đơn vị tin
học (ms, GHz, GB, tokens).
"""

from __future__ import annotations

from tools.guard.firewall import check_output, extract_anchors

# Nguồn Layer A giả lập, giữ nguyên dấu tiếng Việt như tài liệu thật.
SRC = [
    "Warfarin: ngưng 5 ngày trước mổ. INR mục tiêu < 1.2 trước tê tủy sống.",
    "Enoxaparin liều dự phòng: ngưng 12 giờ. Liều điều trị: ngưng 24 giờ.",
    "Rivaroxaban: ngưng 72 giờ nếu CrCl < 30 mL/phút.",
    "Bắc cầu heparin làm tăng chảy máu nặng (OR 3.60, 95% CI 1.52 đến 8.50).",
]


class TestClinicalUnitsAreSeen:
    """Trước khi vá, mọi trường hợp dưới đây đều cho anchors_checked == 0."""

    def test_dose_becomes_anchor(self):
        kinds = {a.kind for a in extract_anchors("Liều 40 mg", domain="clinical")}
        assert "dose" in kinds

    def test_duration_becomes_anchor(self):
        kinds = {a.kind for a in extract_anchors("ngưng 12 giờ", domain="clinical")}
        assert "duration" in kinds

    def test_lab_value_with_operator_becomes_anchor(self):
        anchors = extract_anchors("CrCl < 30 mL/phút", domain="clinical")
        assert any(a.kind == "lab_value" for a in anchors)

    def test_effect_size_becomes_anchor(self):
        anchors = extract_anchors("OR 3.60", domain="clinical")
        assert [a.kind for a in anchors] == ["effect_size"]

    def test_range_is_one_anchor_not_two_numbers(self):
        # '5-7 ngày' phải là MỘT mỏ neo. Nếu tách thành '5' và '7', mỗi số có
        # thể mượn nguồn từ hai chỗ khác nhau và cả hai đều "hợp lệ".
        anchors = extract_anchors("Clopidogrel: ngưng 5-7 ngày.", domain="clinical")
        assert [a.raw for a in anchors] == ["5-7 ngày"]

    def test_bare_number_is_still_anchored(self):
        # Số trần không đơn vị vẫn phải bị bắt — liệt kê đủ mọi cách viết lâm
        # sàng là việc không bao giờ xong, nên bắt tất rồi mới lọc.
        anchors = extract_anchors("INR mục tiêu < 1.2", domain="clinical")
        assert any("1.2" in a.raw for a in anchors)


class TestClinicalFabricationIsBlocked:
    def test_probe_that_previously_passed_now_fails(self):
        out = ("Enoxaparin dự phòng: ngưng 12 giờ trước tê tủy sống. "
               "Rivaroxaban ngưng 72 giờ nếu CrCl < 30 mL/phút. "
               "Liều 40 mg tiêm dưới da. INR mục tiêu 1.5.")
        verdict = check_output(out, ["Nguồn không chứa con số nào."],
                               domain="clinical")
        assert verdict.passed is False
        assert verdict.anchors_checked >= 4

    def test_wrong_inr_is_caught(self):
        verdict = check_output(
            "Warfarin: ngưng 5 ngày trước mổ, INR mục tiêu < 1.8.",
            SRC, domain="clinical")
        assert verdict.passed is False
        assert any("1.8" in v.anchor.raw for v in verdict.violations)

    def test_wrong_hold_time_is_caught(self):
        verdict = check_output("Rivaroxaban: ngưng 27 giờ.", SRC, domain="clinical")
        assert verdict.passed is False

    def test_number_written_as_words_fails_closed(self):
        # Không bóc được mỏ neo nào mà vẫn nói chuyện thuốc = không có gì để
        # đối chiếu. Không kiểm được KHÔNG có nghĩa là đạt.
        verdict = check_output("Enoxaparin: ngưng hai mươi bốn giờ trước tê tủy sống.",
                               SRC, domain="clinical")
        assert verdict.passed is False

    def test_smaller_dose_cannot_borrow_digits_from_larger(self):
        # '2 giờ' không được coi là hợp lệ nhờ '12 giờ' trong nguồn.
        verdict = check_output("Enoxaparin: ngưng 2 giờ.", SRC, domain="clinical")
        assert verdict.passed is False


class TestNoFalseAlarmOnTruthfulOutput:
    """Cổng báo động giả nhiều thì bác sĩ sẽ bỏ dùng — đó cũng là một chế độ hỏng."""

    def test_faithful_statement_passes(self):
        verdict = check_output(
            "Warfarin: ngưng 5 ngày trước mổ, INR mục tiêu < 1.2.",
            SRC, domain="clinical")
        assert verdict.passed is True, [v.anchor.raw for v in verdict.violations]

    def test_faithful_effect_size_passes(self):
        verdict = check_output(
            "Bắc cầu heparin làm tăng chảy máu nặng (OR 3.60, 95% CI 1.52 đến 8.50).",
            SRC, domain="clinical")
        assert verdict.passed is True, [v.anchor.raw for v in verdict.violations]

    def test_prose_without_drug_names_is_not_forced_to_have_numbers(self):
        # Câu tổng quan thuần chữ, không nhắc thuốc/thủ thuật -> không áp luật
        # zero-anchor, tránh báo động giả trên phần thảo luận.
        verdict = check_output("Bằng chứng hiện có còn nhiều hạn chế.",
                               SRC, domain="clinical")
        assert verdict.passed is True


class TestCsContractUnchanged:
    """Miền CS phải hành xử y hệt trước khi vá — đây là bằng chứng không hồi quy."""

    def test_cs_default_ignores_clinical_units(self):
        verdict = check_output("Liều 40 mg mỗi ngày.", ["không có số"])
        assert verdict.anchors_checked == 0 and verdict.passed is True

    def test_cs_zero_anchor_still_passes(self):
        verdict = check_output("Enoxaparin được dùng rộng rãi.", ["không có số"])
        assert verdict.passed is True

    def test_cs_anchors_still_work(self):
        verdict = check_output("Chạy trong O(n log n).", ["cost O(n log n) total"])
        assert verdict.passed is True and verdict.anchors_checked == 1

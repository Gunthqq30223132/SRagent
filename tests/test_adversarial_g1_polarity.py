"""Adversarial validation test suite for G1 Whitelist (Strip-and-Verify) and Polarity checks in Firewall V24.

Constructed by Challenger 2 for Milestone 1 adversarial audit.
"""

import pytest
from sr_agent.errors import VacuousPassError
from sr_agent.models.schemas import ClinicalPayloadItem, Polarity
from tools.guard.firewall import check_output, verify_clinical_payload


class TestAdversarialG1Whitelist:
    """Group A & B: Unslotted digits and raw digits with punctuation/leading zeroes."""

    def test_unslotted_digit_prose_pills(self):
        """Unslotted digit '3' outside {{slot_id}} in LLM prose."""
        source = ["Liều dùng Paracetamol là 50 mg."]
        attack_output = "Patient took 3 pills of 50 mg."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert any("Raw unslotted digits" in v.reason or "không xuất hiện" in v.reason for v in verdict.violations)

    def test_unslotted_digit_prose_frequency(self):
        """Unslotted digit '2' outside slot template in LLM prose."""
        source = ["Dùng 500 mg Paracetamol."]
        attack_output = "Dùng {{slot_dosage}} mg, uống 2 lần mỗi ngày."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert any("Raw unslotted digits" in v.reason for v in verdict.violations)

    def test_unslotted_digit_prose_duration(self):
        """Unslotted digit '5' outside slot template in LLM prose."""
        source = ["Liều 100 mg."]
        attack_output = "Liều {{slot_1}} mg trong 5 ngày liên tục."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert any("Raw unslotted digits" in v.reason for v in verdict.violations)

    def test_unslotted_digit_prose_patient_weight(self):
        """Unslotted digit '70' (weight) in LLM prose."""
        source = ["Bệnh nhân dùng 50 mg."]
        attack_output = "Bệnh nhân nặng 70 kg, dùng 50 mg."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert any("Raw unslotted digits" in v.reason or "không xuất hiện" in v.reason for v in verdict.violations)

    def test_raw_digit_surrounding_parentheses(self):
        """Raw digit with surrounding punctuation '(3)'."""
        source = ["Liều dùng là 50 mg."]
        attack_output = "Patient took (3) pills of 50 mg."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert any("Raw unslotted digits" in v.reason or "không xuất hiện" in v.reason for v in verdict.violations)

    def test_raw_digit_leading_zeroes(self):
        """Raw digit with leading zeroes '03'."""
        source = ["Liều dùng là 50 mg."]
        attack_output = "Dùng 03 viên 50 mg."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False

    def test_raw_digit_ref_hashtag(self):
        """Raw digit with ref hashtag '#1'."""
        source = ["Liều dùng là 50 mg."]
        attack_output = "Liều 50 mg [ref: #1]."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False

    def test_raw_digit_leading_zero_dose(self):
        """Raw digit with leading zeroes in dose '0050 mg'."""
        source = ["Liều 50 mg."]
        attack_output = "Uống 0050 mg."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False

    def test_raw_digit_decimal_zeroes(self):
        """Decimal point modification '50.00 mg' vs '50 mg'."""
        source = ["Liều 50 mg."]
        attack_output = "Uống 50.00 mg."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False


class TestAdversarialPolarityInversion:
    """Group C: Polarity inversion payloads."""

    def test_polarity_khong_vuot_qua_to_positive(self):
        """Source has 'KHÔNG vượt quá 50 mg', output has positive 'Liều 50 mg'."""
        source = ["KHÔNG vượt quá 50 mg mỗi ngày."]
        attack_output = "Liều 50 mg mỗi ngày."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert any("Polarity inversion" in v.reason for v in verdict.violations)

    def test_polarity_positive_to_khong_vuot_qua(self):
        """Source has positive 'Liều 50 mg', output has negative 'KHÔNG vượt quá 50 mg'."""
        source = ["Liều 50 mg mỗi ngày."]
        attack_output = "KHÔNG vượt quá 50 mg mỗi ngày."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert any("Polarity inversion" in v.reason for v in verdict.violations)

    def test_polarity_lieu_toi_da_to_positive(self):
        """Source has 'Liều tối đa 50 mg', output has positive 'Cho bệnh nhân dùng 50 mg'."""
        source = ["Liều tối đa 50 mg."]
        attack_output = "Cho bệnh nhân dùng 50 mg."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert any("Polarity inversion" in v.reason for v in verdict.violations)

    def test_polarity_chong_chi_dinh_to_positive(self):
        """Source has 'Chống chỉ định 50 mg cho trẻ em', output has 'Cho trẻ em dùng 50 mg'."""
        source = ["Chống chỉ định 50 mg cho trẻ em."]
        attack_output = "Cho trẻ em dùng 50 mg."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert any("Polarity inversion" in v.reason for v in verdict.violations)

    def test_polarity_do_not_exceed_to_positive(self):
        """Source has English 'Do not exceed 50 mg daily', output has 'Take 50 mg daily'."""
        source = ["Do not exceed 50 mg daily."]
        attack_output = "Take 50 mg daily."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert any("Polarity inversion" in v.reason for v in verdict.violations)

    def test_clinical_payload_polarity_negative_mismatch(self):
        """ClinicalPayloadItem with MAX_LIMIT polarity against non-negated source."""
        source = ["Liều 50 mg."]
        item = ClinicalPayloadItem(
            value=50,
            unit="mg",
            polarity=Polarity.MAX_LIMIT,
        )
        verdict = verify_clinical_payload(item, source)
        assert verdict.passed is False
        assert any("Polarity mismatch" in v.reason for v in verdict.violations)

    def test_clinical_payload_polarity_positive_mismatch(self):
        """ClinicalPayloadItem with POSITIVE polarity against negated source."""
        source = ["Không được dùng 50 mg."]
        item = ClinicalPayloadItem(
            value=50,
            unit="mg",
            polarity=Polarity.POSITIVE,
        )
        verdict = verify_clinical_payload(item, source)
        assert verdict.passed is False
        assert any("Polarity mismatch" in v.reason for v in verdict.violations)

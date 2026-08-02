"""Clinical Probe Attack Harness (V24 Hardened) — 10 Attack Vectors.

Validates that Firewall V24 detects and blocks all 10 clinical attack vectors fail-closed.
"""

import pytest

from sr_agent.errors import VacuousPassError
from sr_agent.models.schemas import ClinicalPayloadItem, Polarity
from tools.guard.firewall import check_output, verify_clinical_payload


class TestClinicalProbeAttacks:
    """Suite 10/10 probe attack scenarios targeting clinical AI firewall gaps."""

    def test_probe_01_substring_match_evasion(self):
        """Probe 1: Substring match attack ('5 mg' trying to pass via '25 mg')."""
        source = ["Liều khuyến cáo Paracetamol cho người lớn là 25 mg."]
        attack_output = "Bệnh nhân được chỉ định dùng 5 mg Paracetamol."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert len(verdict.violations) > 0

    def test_probe_02_vacuous_pass_attack(self):
        """Probe 2: Vacuous pass attack (prose with 0 numeric anchors checked)."""
        source = ["Liều dùng Paracetamol là 500 mg."]
        attack_output = "Bệnh nhân cần tuân thủ hướng dẫn điều trị và nghỉ ngơi đầy đủ."
        with pytest.raises(VacuousPassError):
            check_output(attack_output, source)

    def test_probe_03_unrecognized_clinical_units(self):
        """Probe 3: Extended clinical unit mismatch ('5 mg/kg/min' vs '5 mcg/kg/min')."""
        source = ["Liều Dopamine duy trì là 5 mcg/kg/min."]
        attack_output = "Cho bệnh nhân dùng 5 mg/kg/min Dopamine."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False

    def test_probe_04_unslotted_raw_digits(self):
        """Probe 4: Unslotted raw digits remaining in LLM prose text."""
        source = ["Liều dùng là 500 mg."]
        attack_output = "Liều dùng là {{slot_1}} mg, uống 3 lần một ngày."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert any("Raw unslotted digits" in v.reason for v in verdict.violations)

    def test_probe_05_polarity_inversion(self):
        """Probe 5: Polarity inversion attack (negation / max limit reversed to positive)."""
        source = ["Liều Paracetamol KHÔNG được vượt quá 4000 mg mỗi ngày."]
        attack_output = "Khuyên dùng 4000 mg Paracetamol mỗi ngày."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert any("Polarity inversion" in v.reason for v in verdict.violations)

    def test_probe_06_applicability_range_inversion(self):
        """Probe 6: Applicability condition mismatch / omission attack."""
        source = ["Đối với bệnh nhân suy thận eGFR < 30 mL/min, liều dùng là 250 mg."]
        item = ClinicalPayloadItem(
            value=250,
            unit="mg",
            polarity=Polarity.POSITIVE,
            applicability_condition="suy thận",
        )
        # Verify against source lacking applicability condition
        bad_source = ["Liều dùng chuẩn cho tất cả bệnh nhân là 250 mg."]
        verdict = verify_clinical_payload(item, bad_source)
        assert verdict.passed is False
        assert any("Applicability mismatch" in v.reason for v in verdict.violations)

    def test_probe_07_unit_order_of_magnitude_swap(self):
        """Probe 7: Unit order-of-magnitude swap attack ('500 mg' vs '500 mcg')."""
        source = ["Liều khởi đầu Fentanyl là 500 mcg."]
        attack_output = "Liều khởi đầu Fentanyl là 500 mg."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False

    def test_probe_08_decimal_alteration(self):
        """Probe 8: Decimal point alteration attack ('8 ng/mL' vs '0.8 ng/mL')."""
        source = ["Nồng độ Digoxin mục tiêu là 0.8 ng/mL."]
        attack_output = "Nồng độ Digoxin mục tiêu là 8 ng/mL."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False

    def test_probe_09_delimiter_evasion(self):
        """Probe 9: Delimiter evasion attack ('1020 mg' vs range '10-20 mg')."""
        source = ["Khoảng liều an toàn là 10-20 mg."]
        attack_output = "Khoảng liều an toàn là 1020 mg."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False

    def test_probe_10_citation_scope_mismatch(self):
        """Probe 10: Citation scope mismatch attack (citing source A for number in source B)."""
        source_doc_a = ["Paracetamol dùng 500 mg."]
        attack_output = "Paracetamol dùng 400 mg."
        verdict = check_output(attack_output, source_doc_a)
        assert verdict.passed is False

    def test_probe_11_compound_clinical_units_valid_pass(self):
        """Probe 11: Compound clinical units pass cleanly without false-positive violations."""
        compound_cases = [
            ("Bệnh nhân dùng 5 mcg/dL levothyroxine", ["Bệnh nhân dùng 5 mcg/dL levothyroxine"]),
            ("Nồng độ Tacrolimus là 5 ng/mL trong máu", ["Nồng độ Tacrolimus là 5 ng/mL trong máu"]),
            ("Liều hoá chất là 100 mg/m² cho một chu kỳ", ["Liều hoá chất là 100 mg/m² cho một chu kỳ"]),
            ("Tốc độ truyền duy trì 2 mL/kg/h dung dịch Nacl", ["Tốc độ truyền duy trì 2 mL/kg/h dung dịch Nacl"]),
            ("Bệnh nhân có nồng độ 15 ug/dL trong huyết thanh", ["Bệnh nhân có nồng độ 15 ug/dL trong huyết thanh"]),
        ]
        for output, source in compound_cases:
            verdict = check_output(output, source)
            assert verdict.passed is True, f"Failed for output: '{output}' with violations: {verdict.violations}"
            assert verdict.anchors_checked >= 1

    def test_probe_12_leading_dot_boundary_lookbehind(self):
        """Probe 12: Leading dot boundary lookbehind prevents partial decimal match (e.g. '.5' matching '10.5')."""
        from tools.guard.firewall import is_strict_substring
        assert is_strict_substring(".5", "10.5 mg") is False
        assert is_strict_substring(".5 mg", "10.5 mg") is False
        assert is_strict_substring(".5 mg", "Dùng .5 mg Levothyroxine") is True

        source = ["Liều khuyến cáo là 10.5 mg."]
        attack_output = "Liều dùng là .5 mg."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert len(verdict.violations) > 0


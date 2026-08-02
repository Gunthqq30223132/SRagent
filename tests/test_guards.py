"""Tests cho tools/guard/ — Numeric Firewall V24 + Outbound Interceptor. Offline 100%.

Các "secret" trong file này đều là chuỗi giả có chủ đích (EXAMPLE/FAKE) — chúng tồn tại
để chứng minh interceptor bắt được, không phải credential thật.
"""

import json

import pytest

from tools.guard.firewall import check_output, extract_anchors
from tools.guard.outbound import (
    OutboundViolation,
    assert_sanitized,
    redact,
    scan,
)

SOURCE = (
    "We evaluate on ImageNet-1k. The server listens on port 8080 and achieves "
    "99.9% top-1 accuracy with O(n log n) preprocessing at 12 ms latency (v2.1.0)."
)


class TestFirewallExtract:
    def test_extracts_expected_kinds(self):
        kinds = {a.kind for a in extract_anchors(SOURCE)}
        assert {"port", "percentage", "complexity", "unit", "version"} <= kinds

    def test_prose_without_numbers_has_no_anchors(self):
        text = "This survey reviews retrieval augmented generation approaches."
        assert extract_anchors(text) == []


class TestFirewallVerdicts:
    def test_exact_match_passes(self):
        out = "The system uses O(n log n) preprocessing on port 8080 (99.9% top-1)."
        verdict = check_output(out, [SOURCE])
        assert verdict.passed is True
        assert verdict.anchors_checked >= 3
        assert verdict.violations == []

    def test_single_digit_port_mismatch_fails_closed(self):
        verdict = check_output("The server listens on port 8081.", [SOURCE])
        assert verdict.passed is False
        assert "8081" in verdict.violations[0].reason

    def test_complexity_mutation_fails(self):
        verdict = check_output("Preprocessing runs in O(n²).", [SOURCE])
        assert verdict.passed is False

    def test_percentage_off_by_one_decimal_fails(self):
        verdict = check_output("It reaches 99.8% top-1 accuracy.", [SOURCE])
        assert verdict.passed is False

    def test_no_anchor_output_passes_with_zero_checked(self):
        verdict = check_output("The paper proposes a novel retrieval method.", [SOURCE], allow_vacuous=True)
        assert verdict.passed is True and verdict.anchors_checked == 0

    def test_no_anchor_output_raises_vacuous_pass_error(self):
        from sr_agent.errors import VacuousPassError
        with pytest.raises(VacuousPassError):
            check_output("The paper proposes a novel retrieval method.", [SOURCE])

    def test_whitespace_difference_still_matches(self):
        # Chuẩn hóa nhẹ chỉ vượt khác biệt trình bày, không vượt sai số
        verdict = check_output("complexity of O(n  log   n)", ["cost O(n log n) total"])
        assert verdict.passed is True

    def test_nonstrict_missing_anchor_is_warning_not_violation(self):
        verdict = check_output("We use 32 GB of memory.", [SOURCE], strict=False)
        assert verdict.passed is True
        assert len(verdict.warnings) == 1
        # nhưng strict mặc định thì fail
        assert check_output("We use 32 GB of memory.", [SOURCE]).passed is False


CLEAN_ACADEMIC = (
    "The model achieves 99.9% accuracy using O(n log n) attention; "
    "see https://arxiv.org/abs/2401.12345 — dataset of 10,000 samples, version 2.1.0."
)


class TestInterceptorRules:
    @pytest.mark.parametrize("payload,rule", [
        ("key sk-FAKEabc123def456ghi789jkl here", "SECRET_OPENAI_ANTHROPIC"),
        ("token ghp_FAKEABCDEFGHIJKLMNOPQRST12 leaked", "SECRET_GITHUB"),
        ("aws AKIAIOSFODNN7EXAMPLE key", "SECRET_AWS"),
        ("slack xoxb-1234567890-FAKEFAKE", "SECRET_SLACK"),
        ("google AIzaFAKE1234567890abcdefghijklmnopqr", "SECRET_GOOGLE"),
        ("IEEE_API_KEY=abcd1234efgh", "ENV_ASSIGNMENT"),
        ("log tại /Users/thanh/projects/9router/.env cho thấy", "PATH_HOME"),
        ("nối tới 192.168.1.10:5432 nội bộ", "IP_PRIVATE"),
        ("Ollama chạy ở localhost:11434 trên máy", "IP_PRIVATE"),
        ("liên hệ someone@example.com nhé", "EMAIL"),
        ("gọi +84912345678 hoặc 0987654321", "PHONE_VN"),
        ("CCCD 079203012345 của bệnh nhân", "CCCD_VN"),
    ])
    def test_each_rule_fires(self, payload, rule):
        assert rule in {f.rule_id for f in scan(payload)}

    def test_high_entropy_token_caught_but_long_words_are_not(self):
        random_token = "aB3dE9fG2hJ7kL0mN5pQ8rS1tU4vW6xY9zA2bC5d"
        assert any(f.rule_id == "HIGH_ENTROPY_STRING" for f in scan(f"x {random_token} y"))
        slug = "self-attention-mechanisms-are-all-you-need-here"
        assert scan(f"về {slug} trong paper") == []

    def test_clean_academic_text_has_zero_findings(self):
        assert scan(CLEAN_ACADEMIC) == []

    def test_env_var_name_alone_is_not_a_finding(self):
        # README/nhật ký nhắc TÊN biến là hợp lệ — chỉ dạng gán giá trị mới bị chặn
        assert scan("hãy điền IEEE_API_KEY vào .env trước khi chạy") == []


class TestInterceptorFailClosed:
    def test_assert_sanitized_raises_without_leaking_secret(self, tmp_path):
        secret = "sk-FAKEabc123def456ghi789jkl"
        with pytest.raises(OutboundViolation) as exc_info:
            assert_sanitized(f"payload chứa {secret}", audit_path=tmp_path / "a.jsonl")
        msg = str(exc_info.value)
        assert "SECRET_OPENAI_ANTHROPIC" in msg
        assert secret not in msg  # thông điệp lỗi không được lộ lại secret

    def test_clean_payload_passes_silently(self, tmp_path):
        assert_sanitized(CLEAN_ACADEMIC, audit_path=tmp_path / "a.jsonl")
        assert not (tmp_path / "a.jsonl").exists()  # sạch thì không ghi audit

    def test_audit_log_contains_rule_and_hash_only(self, tmp_path):
        secret = "AKIAIOSFODNN7EXAMPLE"
        audit = tmp_path / "audit.jsonl"
        with pytest.raises(OutboundViolation):
            assert_sanitized(f"aws {secret} key", audit_path=audit)
        entries = [json.loads(line) for line in audit.read_text().splitlines()]
        assert entries[0]["rule_id"] == "SECRET_AWS"
        assert len(entries[0]["match_sha256_12"]) == 12
        assert secret not in audit.read_text()

    def test_masked_match_never_contains_full_secret(self):
        secret = "ghp_FAKEABCDEFGHIJKLMNOPQRST12"
        finding = scan(f"x {secret} y")[0]
        assert secret not in finding.masked_match
        assert "len=" in finding.masked_match


class TestRedact:
    def test_redact_masks_secret_and_preserves_clean_text(self):
        payload = "chạy pipeline với IEEE_API_KEY=abcd1234efgh xong báo lại"
        cleaned = redact(payload)
        assert "abcd1234efgh" not in cleaned
        assert "«REDACTED:ENV_ASSIGNMENT»" in cleaned
        assert cleaned.startswith("chạy pipeline với ") and cleaned.endswith(" xong báo lại")

    def test_redact_on_clean_text_is_identity(self):
        assert redact(CLEAN_ACADEMIC) == CLEAN_ACADEMIC


class TestCompoundUnitsAndBoundaries:
    @pytest.mark.parametrize("text", [
        "Bệnh nhân dùng 5 mcg/dL levothyroxine",
        "Nồng độ 5 ng/mL",
        "Liều 100 mg/m²",
        "Tốc độ truyền 2 mL/kg/h",
        "Nồng độ 15 ug/dL",
    ])
    def test_compound_units_pass_verdict(self, text):
        verdict = check_output(text, [text])
        assert verdict.passed is True
        assert verdict.anchors_checked == 1

    def test_leading_dot_boundary_lookbehind(self):
        from tools.guard.firewall import is_strict_substring
        assert is_strict_substring(".5", "10.5 mg") is False
        assert is_strict_substring(".5 mg", "10.5 mg") is False
        assert is_strict_substring(".5 mg", "Bệnh nhân dùng .5 mg") is True

    def test_leading_dot_firewall_verdict_blocks_partial_match(self):
        source = ["Bệnh nhân dùng 10.5 mg Paracetamol."]
        attack_output = "Bệnh nhân dùng .5 mg Paracetamol."
        verdict = check_output(attack_output, source)
        assert verdict.passed is False
        assert len(verdict.violations) > 0


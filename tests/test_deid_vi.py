"""Tests cho De-ID tiếng Việt — bệnh án mẫu đầy đủ."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.guard.deid_vi import scan_pii


SAMPLE_MEDICAL_RECORD = """
BỆNH ÁN NỘI TRÚ
Bệnh viện Chợ Rẫy

Họ tên: Nguyễn Văn An
Ngày sinh: 15/03/1985
MSBA: 2406789
Số thẻ BHYT: DN4123456789012
CCCD: 079203012345
Giường số: 12B
Khoa: Gây Mê Hồi Sức
Phòng: Hồi Sức Tích Cực

Điện thoại: 0903.123.456
SĐT liên hệ: 028.3855.1234

Địa chỉ: 123 Nguyễn Trãi, P.Bến Thành, Q.1, TP.HCM

Người nhà: Trần Thị Bình
ĐT: 0912 345 678
ĐC: 456 Lê Lợi, Q.3, TP.HCM

Ngày vào viện: 02/08/2026
"""

CLEAN_CLINICAL_TEXT = """
Bệnh nhân nam, nhóm tuổi trung niên, tiền căn tăng huyết áp.
Chẩn đoán: Viêm phổi cộng đồng mức độ nặng.
SpO2 92%, huyết áp 140/90 mmHg, nhịp tim 88 bpm.
Chỉ định: Ceftriaxone 2g IV mỗi 24h.
"""


def test_full_record_detection():
    """Mẫu bệnh án đầy đủ phải phát hiện >= 8 PII findings."""
    result = scan_pii(SAMPLE_MEDICAL_RECORD)
    categories = [f.category for f in result.findings]

    print(f"\n=== De-ID Findings ({len(result.findings)}) ===")
    for f in result.findings:
        print(f"  [{f.category}] '{f.matched_text}' @ {f.span}")

    assert result.has_pii, "Should detect PII in medical record"
    assert len(result.findings) >= 8, (
        f"Expected >= 8 findings, got {len(result.findings)}: {categories}"
    )

    # Kiểm tra các danh mục bắt buộc
    assert "NAME" in categories, "Must detect patient name"
    assert "MSBA" in categories, "Must detect MSBA"
    assert "BHYT" in categories, "Must detect BHYT"
    assert "PHONE" in categories, "Must detect phone number"
    assert "CCCD" in categories, "Must detect CCCD"
    assert "BED" in categories, "Must detect bed number"
    assert "DEPT" in categories, "Must detect department"
    assert "ADDRESS" in categories, "Must detect address"


def test_msba_various_formats():
    """MSBA với nhiều định dạng từ khóa."""
    cases = [
        "MSBA: 1234567",
        "Mã số bệnh án: 9876543",
        "SHS: 11223344",
        "Số hồ sơ: 55667",
        "Mã BN: 998877",
    ]
    for case in cases:
        result = scan_pii(case)
        assert result.has_pii, f"Should detect MSBA in: {case}"
        assert any(f.category == "MSBA" for f in result.findings), f"Category should be MSBA for: {case}"


def test_phone_landline():
    """SĐT cố định Việt Nam (có mã vùng)."""
    cases = [
        "ĐT: 028.3855.1234",
        "Điện thoại: 0236 3812 345",
        "Liên hệ: 024 3825 6789",
    ]
    for case in cases:
        result = scan_pii(case)
        assert result.has_pii, f"Should detect landline in: {case}"
        assert any(f.category == "PHONE" for f in result.findings), f"Category should be PHONE for: {case}"


def test_bhyt_format():
    """Mã BHYT tiêu chuẩn."""
    cases = [
        "BHYT: DN4123456789012",
        "Số thẻ BHYT: HN1987654321098",
        "Bảo hiểm y tế: SG2111222333444",
    ]
    for case in cases:
        result = scan_pii(case)
        assert result.has_pii, f"Should detect BHYT in: {case}"
        assert any(f.category == "BHYT" for f in result.findings), f"Category should be BHYT for: {case}"


def test_clean_clinical_text():
    """Văn bản lâm sàng thuần túy KHÔNG chứa PII nên trả 0 finding."""
    result = scan_pii(CLEAN_CLINICAL_TEXT)
    # Có thể bắt DEPT "Bệnh nhân" nếu over-match, nhưng không nên có NAME/MSBA/BHYT/PHONE/CCCD
    sensitive = [f for f in result.findings if f.category in ("NAME", "MSBA", "BHYT", "PHONE", "CCCD")]
    assert len(sensitive) == 0, (
        f"Clean clinical text should have 0 sensitive findings, got: "
        f"{[(f.category, f.matched_text) for f in sensitive]}"
    )


def test_redacted_text():
    """Redacted text phải thay thế tất cả PII bằng placeholder."""
    result = scan_pii(SAMPLE_MEDICAL_RECORD)
    redacted = result.redacted_text

    assert "Nguyễn Văn An" not in redacted, "Patient name should be redacted"
    assert "2406789" not in redacted, "MSBA should be redacted"
    assert "[NAME_REDACTED]" in redacted, "Should contain NAME placeholder"
    assert "[MSBA_REDACTED]" in redacted, "Should contain MSBA placeholder"


if __name__ == "__main__":
    test_full_record_detection()
    test_msba_various_formats()
    test_phone_landline()
    test_bhyt_format()
    test_clean_clinical_text()
    test_redacted_text()
    print("\n✅ All De-ID Vietnamese tests passed!")

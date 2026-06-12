"""Tests for the QRIS payment provider module.

Ported test cases from the Go reference implementation at
``kvc-gate/internal/payments/qris_test.go`` plus additional Python-specific tests.
"""

from __future__ import annotations

import pytest

from bot_app.infrastructure.payments.qris import (
    TLV,
    QRISSummary,
    ValidationResult,
    build_tlv,
    convert_static_to_dynamic,
    crc16,
    parse_tlv,
    summarize_qris,
    validate_static_qris,
)

# ── Test data ────────────────────────────────────────────────

SAMPLE_STATIC_QRIS = (
    "00020101021126380014ID.CO.QRIS.WWW0116936000000000000"
    "05204581253033605802ID5908TestShop6007Jakarta6304F2F0"
)


# ── CRC16 tests ────────────────────────────────────────────


class TestCRC16:
    def test_known_value(self) -> None:
        """CRC16 of the sample QRIS (without CRC value) should match the embedded CRC."""
        # The CRC is the last 4 chars: F2F0
        data_without_crc = SAMPLE_STATIC_QRIS[:-4]
        assert crc16(data_without_crc) == "F2F0"

    def test_empty_string(self) -> None:
        result = crc16("")
        assert len(result) == 4
        assert result == "FFFF"

    def test_deterministic(self) -> None:
        """Same input produces same output."""
        assert crc16("hello") == crc16("hello")


# ── TLV parsing / building ─────────────────────────────────


class TestTLVParsing:
    def test_parse_simple(self) -> None:
        """Parse a simple QRIS and verify essential tags."""
        elements = parse_tlv(SAMPLE_STATIC_QRIS)
        assert len(elements) > 0

        tags = {e.tag for e in elements}
        assert "00" in tags  # Payload Format Indicator
        assert "01" in tags  # Point of Initiation Method
        assert "59" in tags  # Merchant Name
        assert "63" in tags  # CRC

    def test_parse_and_rebuild_roundtrip(self) -> None:
        """parse → build should produce the original string."""
        elements = parse_tlv(SAMPLE_STATIC_QRIS)
        rebuilt = build_tlv(elements)
        assert rebuilt == SAMPLE_STATIC_QRIS

    def test_parse_empty_string(self) -> None:
        elements = parse_tlv("")
        assert elements == []

    def test_tag_01_value(self) -> None:
        """Tag 01 should be '11' (static) in the sample."""
        elements = parse_tlv(SAMPLE_STATIC_QRIS)
        tag01 = next((e for e in elements if e.tag == "01"), None)
        assert tag01 is not None
        assert tag01.value == "11"


# ── Validation tests ────────────────────────────────────────


class TestValidateStaticQRIS:
    def test_valid_sample(self) -> None:
        result = validate_static_qris(SAMPLE_STATIC_QRIS)
        assert result.valid is True
        assert result.errors == []

    def test_empty_string_rejected(self) -> None:
        result = validate_static_qris("")
        assert result.valid is False

    def test_whitespace_only_rejected(self) -> None:
        result = validate_static_qris("   ")
        assert result.valid is False

    def test_wrong_prefix_rejected(self) -> None:
        result = validate_static_qris("0102010102116304FFFF")
        assert result.valid is False
        assert any("000201" in e for e in result.errors)

    def test_crc_mismatch_rejected(self) -> None:
        """Changing the last 4 chars should cause CRC mismatch."""
        bad_qris = SAMPLE_STATIC_QRIS[:-4] + "XXXX"
        result = validate_static_qris(bad_qris)
        assert result.valid is False
        assert any("CRC" in e for e in result.errors)

    def test_too_short_rejected(self) -> None:
        result = validate_static_qris("000201")
        assert result.valid is False

    def test_valid_static_method(self) -> None:
        result = validate_static_qris(SAMPLE_STATIC_QRIS)
        assert result.valid is True
        # The sample QRIS has method "11" (static)


# ── Summary tests ──────────────────────────────────────────


class TestSummarizeQRIS:
    def test_reads_core_fields(self) -> None:
        summary = summarize_qris(SAMPLE_STATIC_QRIS)
        assert summary.initiation_method == "Static"
        assert summary.merchant_name == "TestShop"
        assert summary.merchant_city == "Jakarta"
        assert summary.country_code == "ID"
        assert summary.currency_code == "360"
        assert summary.crc == "F2F0"

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid QRIS"):
            summarize_qris("")

    def test_payload_length(self) -> None:
        summary = summarize_qris(SAMPLE_STATIC_QRIS)
        assert summary.payload_length == len(SAMPLE_STATIC_QRIS)


# ── Static → Dynamic conversion ────────────────────────────


class TestConvertStaticToDynamic:
    def test_converts_method_to_dynamic(self) -> None:
        converted = convert_static_to_dynamic(SAMPLE_STATIC_QRIS, 50321)
        assert "010212" in converted  # dynamic initiation method

    def test_inserts_amount_tag(self) -> None:
        converted = convert_static_to_dynamic(SAMPLE_STATIC_QRIS, 50321)
        # tag 54, length 05, value 50321
        assert "540550321" in converted

    def test_converted_differs_from_static(self) -> None:
        converted = convert_static_to_dynamic(SAMPLE_STATIC_QRIS, 50321)
        assert converted != SAMPLE_STATIC_QRIS

    def test_converted_is_valid_qris(self) -> None:
        converted = convert_static_to_dynamic(SAMPLE_STATIC_QRIS, 50321)
        result = validate_static_qris(converted)
        assert result.valid is True

    def test_zero_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="amount must be greater than 0"):
            convert_static_to_dynamic(SAMPLE_STATIC_QRIS, 0)

    def test_negative_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="amount must be greater than 0"):
            convert_static_to_dynamic(SAMPLE_STATIC_QRIS, -100)

    def test_invalid_qris_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid QRIS"):
            convert_static_to_dynamic("not a qris", 50000)

    def test_crc_recalculated(self) -> None:
        """The CRC should be recalculated for the converted payload."""
        converted = convert_static_to_dynamic(SAMPLE_STATIC_QRIS, 12345)
        # The CRC should be valid
        data_without_crc = converted[:-4]
        declared_crc = converted[-4:].upper()
        calculated_crc = crc16(data_without_crc)
        assert declared_crc == calculated_crc

    def test_amount_100(self) -> None:
        """Smallest valid amount."""
        converted = convert_static_to_dynamic(SAMPLE_STATIC_QRIS, 100)
        result = validate_static_qris(converted)
        assert result.valid is True

    def test_various_amounts(self) -> None:
        """Multiple amounts should all produce valid QRIS."""
        for amount in [100, 15000, 999999]:
            converted = convert_static_to_dynamic(SAMPLE_STATIC_QRIS, amount)
            result = validate_static_qris(converted)
            assert result.valid is True, f"amount={amount} produced invalid QRIS"

    def test_converted_summary_shows_dynamic(self) -> None:
        converted = convert_static_to_dynamic(SAMPLE_STATIC_QRIS, 50000)
        summary = summarize_qris(converted)
        assert summary.initiation_method == "Dynamic"
        assert summary.amount == "50000"

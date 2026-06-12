"""QRIS payment provider — static-to-dynamic QRIS conversion.

Ported from the Go reference implementation at ``kvc-gate/internal/payments/qris.go``.
This module provides:

* TLV parsing and building for EMVCo QR codes
* CRC16-CCITT-FALSE calculation
* Static QRIS validation
* Static → Dynamic QRIS conversion with amount injection
* QRIS summary extraction
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Constants ────────────────────────────────────────────────

CRC_TAG = "63"
CRC_TAG_HEADER = "6304"

TAG_NAMES: dict[str, str] = {
    "00": "Payload Format Indicator",
    "01": "Point of Initiation Method",
    "52": "Merchant Category Code",
    "53": "Transaction Currency",
    "54": "Transaction Amount",
    "55": "Tip or Convenience Indicator",
    "56": "Value of Convenience Fee (Fixed)",
    "57": "Value of Convenience Fee (%)",
    "58": "Country Code",
    "59": "Merchant Name",
    "60": "Merchant City",
    "61": "Postal Code",
    "62": "Additional Data Field",
    "63": "CRC",
}

NESTED_TAGS: set[str] = {f"{i:02d}" for i in range(26, 52)} | {"62"}


# ── Data classes ─────────────────────────────────────────────


@dataclass(slots=True)
class TLV:
    """Tag-Length-Value element for QRIS/EMVCo payloads."""

    tag: str
    name: str
    length: int
    value: str
    children: list[TLV] = field(default_factory=list)


@dataclass(slots=True)
class QRISSummary:
    """Extracted summary from a QRIS payload."""

    payload_length: int
    initiation_method: str
    merchant_name: str
    merchant_city: str
    country_code: str
    merchant_category: str
    currency_code: str
    amount: str | None
    crc: str


@dataclass(slots=True)
class ValidationResult:
    """Result of validating a QRIS string."""

    valid: bool
    errors: list[str] = field(default_factory=list)


# ── CRC16-CCITT-FALSE ────────────────────────────────────────


def crc16(payload: str) -> str:
    """Calculate CRC16-CCITT-FALSE for EMVCo/QRIS payloads.

    This is identical to the Go reference ``crc16()`` function.
    """
    crc = 0xFFFF
    for char in payload:
        crc ^= ord(char) << 8
        for _ in range(8):
            crc = (crc << 1 ^ 4129) & 65535 if crc & 32768 else crc << 1 & 65535
    return f"{crc & 0xFFFF:04X}"


# ── TLV parsing / building ──────────────────────────────────


def parse_tlv(data: str) -> list[TLV]:
    """Parse a TLV-encoded string into a list of :class:`TLV` elements."""
    elements: list[TLV] = []
    pos = 0
    while pos < len(data):
        if pos + 4 > len(data):
            break
        tag = data[pos : pos + 2]
        try:
            length = int(data[pos + 2 : pos + 4])
        except ValueError:
            break
        end = pos + 4 + length
        if end > len(data):
            break
        value = data[pos + 4 : end]
        element = TLV(
            tag=tag,
            name=TAG_NAMES.get(tag, f"Unknown ({tag})"),
            length=length,
            value=value,
        )
        if tag in NESTED_TAGS:
            element.children = parse_tlv(value)
        elements.append(element)
        pos = end
    return elements


def build_tlv(items: list[TLV]) -> str:
    """Serialize a list of :class:`TLV` elements back to a string."""
    chunks: list[str] = []
    for item in items:
        value = build_tlv(item.children) if item.children else item.value
        chunks.append(f"{item.tag}{len(value):02d}{value}")
    return "".join(chunks)


def _make_tlv(tag: str, value: str, name: str = "") -> TLV:
    """Helper to create a simple TLV element."""
    return TLV(tag=tag, name=name or TAG_NAMES.get(tag, ""), length=len(value), value=value)


# ── Validation ───────────────────────────────────────────────


def validate_static_qris(qris_string: str) -> ValidationResult:
    """Validate a static QRIS payload string.

    Checks:
    * Starts with Payload Format Indicator ``000201``
    * Contains required tags (00, 01, 52, 53, 58, 59, 60, 63)
    * CRC matches
    * Point of Initiation Method is ``11`` (static) or ``12`` (dynamic)
    * Contains Merchant Account Information (tags 26-51)
    """
    errors: list[str] = []
    value = qris_string.strip()

    if not value:
        return ValidationResult(False, ["QRIS string is empty"])

    if not value.startswith("000201"):
        errors.append('QRIS must start with Payload Format Indicator "000201"')

    if len(value) < 20:
        errors.append("QRIS string is too short")
        return ValidationResult(False, errors)

    # CRC check
    data_without_crc = value[:-4]
    declared_crc = value[-4:].upper()
    calculated_crc = crc16(data_without_crc)
    if declared_crc != calculated_crc:
        errors.append(f"CRC mismatch: expected {calculated_crc}, got {declared_crc}")

    elements = parse_tlv(value)
    if not elements:
        errors.append("Failed to parse any TLV elements")
        return ValidationResult(False, errors)

    tags = {element.tag for element in elements}
    required = [
        ("00", "Payload Format Indicator"),
        ("01", "Point of Initiation Method"),
        ("52", "Merchant Category Code"),
        ("53", "Transaction Currency"),
        ("58", "Country Code"),
        ("59", "Merchant Name"),
        ("60", "Merchant City"),
        ("63", "CRC"),
    ]
    for tag, name in required:
        if tag not in tags:
            errors.append(f"Missing required tag {tag} ({name})")

    # Validate Point of Initiation Method
    method = next((element for element in elements if element.tag == "01"), None)
    if method and method.value not in {"11", "12"}:
        errors.append(
            f'Invalid Point of Initiation Method: "{method.value}" (must be "11" or "12")'
        )

    # Must have Merchant Account Information (tags 26-51)
    has_merchant = any(
        26 <= int(element.tag) <= 51 for element in elements if element.tag.isdigit()
    )
    if not has_merchant:
        errors.append("No Merchant Account Information found (tags 26-51)")

    return ValidationResult(not errors, errors)


# ── Summary ─────────────────────────────────────────────────


def summarize_qris(qris_string: str) -> QRISSummary:
    """Extract a summary from a validated QRIS payload."""
    value = qris_string.strip()
    validation = validate_static_qris(value)
    if not validation.valid:
        raise ValueError("Invalid QRIS: " + "; ".join(validation.errors))

    elements = parse_tlv(value)

    def find(tag: str) -> TLV | None:
        return next((item for item in elements if item.tag == tag), None)

    method_value = find("01").value if find("01") else "11"
    method = "Static" if method_value == "11" else "Dynamic"

    return QRISSummary(
        payload_length=len(value),
        initiation_method=method,
        merchant_name=find("59").value if find("59") else "",
        merchant_city=find("60").value if find("60") else "",
        country_code=find("58").value if find("58") else "ID",
        merchant_category=find("52").value if find("52") else "",
        currency_code=find("53").value if find("53") else "360",
        amount=find("54").value if find("54") else None,
        crc=value[-4:].upper(),
    )


# ── Static → Dynamic conversion ─────────────────────────────


def convert_static_to_dynamic(qris_string: str, amount: int) -> str:
    """Convert a static QRIS payload to a dynamic one with a specific amount.

    Based on the Go reference ``ConvertStaticToDynamic``:

    1. Change tag 01 from ``11`` (static) to ``12`` (dynamic)
    2. Remove any existing tag 54 (amount) and tag 63 (CRC)
    3. Insert tag 54 with the new amount before tag 58 (Country Code)
    4. Recalculate tag 63 CRC

    Parameters
    ----------
    qris_string : str
        A validated static QRIS payload.
    amount : int
        The transaction amount in smallest currency unit (e.g. IDR 50321).

    Returns
    -------
    str
        A new dynamic QRIS payload with the amount embedded.

    Raises
    ------
    ValueError
        If the QRIS is invalid or *amount* ≤ 0.
    """
    if amount <= 0:
        raise ValueError("amount must be greater than 0")

    value = qris_string.strip()
    validation = validate_static_qris(value)
    if not validation.valid:
        raise ValueError("Invalid QRIS: " + "; ".join(validation.errors))

    items = parse_tlv(value)
    result: list[TLV] = []
    inserted_amount = False
    managed_tags = {"54", "55", "56", "57", CRC_TAG}

    for item in items:
        if item.tag in managed_tags:
            continue

        # Change initiation method to dynamic
        if item.tag == "01":
            result.append(_make_tlv("01", "12", "Point of Initiation Method"))
            continue

        # Insert amount before Country Code (tag 58)
        if item.tag == "58" and not inserted_amount:
            result.append(_make_tlv("54", str(amount), "Transaction Amount"))
            inserted_amount = True

        result.append(item)

    if not inserted_amount:
        raise ValueError("QRIS payload does not contain tag 58; cannot insert amount")

    without_crc = build_tlv(result)
    crc_input = without_crc + CRC_TAG_HEADER
    return crc_input + crc16(crc_input)

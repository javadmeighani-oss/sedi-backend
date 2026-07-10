"""Section 10 — phone normalization utilities."""

from backend.app.utils.phone_normalization import normalize_contact_phone, validate_contact_phone


def test_iranian_phone_normalization():
    assert normalize_contact_phone("09123456789") == "+989123456789"
    assert normalize_contact_phone("989123456789") == "+989123456789"
    assert normalize_contact_phone("+989123456789") == "+989123456789"


def test_international_preserved():
    assert normalize_contact_phone("+14155552671") == "+14155552671"


def test_invalid_iranian_rejected():
    valid, norm = validate_contact_phone("0912345")
    assert valid is False
    assert norm is None

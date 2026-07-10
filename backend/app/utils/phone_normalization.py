"""Canonical phone normalization for caregiver contacts (Iran + international)."""

from __future__ import annotations

import re
from typing import Optional, Tuple

_IRAN_MOBILE_RE = re.compile(r"^\+98\d{10}$")


def normalize_contact_phone(phone: Optional[str]) -> Optional[str]:
    """Normalize phone to E.164-style +98... for Iranian mobiles; preserve other + numbers."""
    if phone is None:
        return None
    s = phone.strip().replace(" ", "").replace("-", "")
    if not s:
        return None
    if s.startswith("+"):
        return s
    if s.startswith("0") and len(s) == 11:
        return f"+98{s[1:]}"
    if s.startswith("9") and len(s) == 10:
        return f"+98{s}"
    if s.startswith("98") and len(s) == 12:
        return f"+{s}"
    return s


def validate_contact_phone(phone: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Return (is_valid, normalized_phone). Does not expose internal validation details."""
    normalized = normalize_contact_phone(phone)
    if normalized is None:
        return True, None
    if normalized.startswith("+98"):
        if _IRAN_MOBILE_RE.match(normalized):
            return True, normalized
        return False, None
    if normalized.startswith("+") and len(normalized) >= 8:
        return True, normalized
    if len(normalized) >= 8:
        return True, normalized
    return False, None

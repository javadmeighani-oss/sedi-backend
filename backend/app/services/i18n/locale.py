from __future__ import annotations

from typing import Optional


SUPPORTED_LANGS = ("en", "fa", "ar")
DEFAULT_LANG = "en"


def normalize_lang(lang: Optional[str]) -> str:
    """
    Normalize language to one of: en|fa|ar.
    Fallback is always DEFAULT_LANG (en).
    """
    if not lang:
        return DEFAULT_LANG
    s = (lang or "").strip().lower()
    if not s:
        return DEFAULT_LANG
    # Keep first two letters (en-US -> en)
    s2 = s.split("-")[0].strip()[:2]
    return s2 if s2 in SUPPORTED_LANGS else DEFAULT_LANG


def parse_accept_language(header_value: Optional[str]) -> str:
    """
    Parse Accept-Language header and return en|fa|ar.
    - Simple V1: uses the first language tag only.
    - Fallback is DEFAULT_LANG (en).
    """
    if not header_value or not header_value.strip():
        return DEFAULT_LANG
    first = header_value.split(",")[0].strip()
    return normalize_lang(first)


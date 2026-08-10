"""Unicode normalization for EN/FA/AR lexical indexing (no stemming/translation)."""

from __future__ import annotations

import re
import unicodedata

# Yeh / Kaf variants (Arabic vs Persian forms)
_YEH_MAP = str.maketrans({
    "\u064a": "\u06cc",  # Arabic Yeh → Persian Yeh
    "\u0649": "\u06cc",  # Alef Maqsura → Persian Yeh
})
_KAF_MAP = str.maketrans({
    "\u0643": "\u06a9",  # Arabic Kaf → Persian Kaf
})
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_ZWNJ_RE = re.compile(r"[\u200c\u200d\u200e\u200f\ufeff]")
_PUNCT_RE = re.compile(r"[^\w\s\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+", re.UNICODE)


def strip_diacritics(text: str) -> str:
    # NFKD then drop combining marks (Arabic diacritics / tatweel)
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn" and ch != "\u0640")


def normalize_fa_ar_text(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text)
    t = _ZWNJ_RE.sub(" ", t)
    t = t.translate(_YEH_MAP).translate(_KAF_MAP)
    t = t.translate(_ARABIC_DIGITS).translate(_PERSIAN_DIGITS)
    t = strip_diacritics(t)
    t = _PUNCT_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def normalize_for_language(text: str, language: str | None) -> str:
    lang = (language or "en").lower()
    if lang.startswith("fa") or lang.startswith("ar") or lang in {"persian", "arabic", "farsi"}:
        return normalize_fa_ar_text(text)
    # English / default: NFC + lower + collapse space (no aggressive stemming)
    t = unicodedata.normalize("NFC", text or "")
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t

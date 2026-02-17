# backend/app/behavior/texts_fa.py
"""Behavior Layer V1: female caring persona texts in FA (multi-locale ready)."""
from typing import Dict

# Caring lead-in for next_question (short, polite, non-commanding). Key = lang.
LEAD_IN_BY_LANG: Dict[str, str] = {
    "fa": "یک لحظه، یه سوال دارم: ",
    "en": "Quick question: ",
    "ar": "سؤال سريع: ",
}

# Companion ping body (Sedi initiates conversation). Key = lang.
COMPANION_PING_BODY_BY_LANG: Dict[str, str] = {
    "fa": "سلام؛ دلم برات تنگ شده. اگر دوست داری بگو امروز چطوره؟ 🌿",
    "en": "Hi; I was thinking of you. If you’d like, tell me how today’s going? 🌿",
    "ar": "مرحباً؛ كنت أفكر بك. إذا أحببت، أخبرني كيف يومك؟ 🌿",
}

COMPANION_PING_TITLE_BY_LANG: Dict[str, str] = {
    "fa": "صدی",
    "en": "Sedi",
    "ar": "سيدي",
}


def get_lead_in(lang: str) -> str:
    """Return caring lead-in for question; default fa."""
    lang = (lang or "fa").strip().lower()
    if lang not in ("en", "fa", "ar"):
        lang = "fa"
    return LEAD_IN_BY_LANG.get(lang, LEAD_IN_BY_LANG["fa"])


def get_companion_ping_body(lang: str) -> str:
    """Return companion ping body; default fa."""
    lang = (lang or "fa").strip().lower()
    if lang not in ("en", "fa", "ar"):
        lang = "fa"
    return COMPANION_PING_BODY_BY_LANG.get(lang, COMPANION_PING_BODY_BY_LANG["fa"])


def get_companion_ping_title(lang: str) -> str:
    """Return companion ping title; default fa."""
    lang = (lang or "fa").strip().lower()
    if lang not in ("en", "fa", "ar"):
        lang = "fa"
    return COMPANION_PING_TITLE_BY_LANG.get(lang, COMPANION_PING_TITLE_BY_LANG["fa"])

# backend/app/knowledge/tone/companion_v1.py
"""Companion Tone Layer V1: warm, short, non-technical phrasing for KC confirm_candidate questions."""
import re
from typing import Any, Dict

# --- In-code copy (fa / en). No technical words in display text. ---

COPY_FA = {
    "opener": "یه سوال کوتاه",
    "body_template": "فقط می‌خوام مطمئن شم: {question}",
    "body_fallback_weak": "یه نکته کوتاه دیدم اما دقیق نیست. می‌خوای دوباره بپرسم یا فعلاً ردش کنم؟",
    "choice_accept": "بله، درسته",
    "choice_reject": "نه، ردش کن",
    "reassurance": "فقط برای اینکه بهتر مراقبتت کنم.",
}

COPY_EN = {
    "opener": "Quick question",
    "body_template": "Just checking: {question}",
    "body_fallback_weak": "I noticed something short but not sure. Want me to ask again or skip for now?",
    "choice_accept": "Yes, that’s right",
    "choice_reject": "No, skip it",
    "reassurance": "Just so I can care for you better.",
}

# Stopwords / suspiciously short extracted phrases (FA) — never show raw in body
WEAK_STOPWORDS_FA = {"هم", "و", "یا", "که"}
WEAK_MIN_LEN = 2

# Extract value from «...» or "..." in text for weak check
_VALUE_PATTERN = re.compile(r"[«\"]([^»\"]*)[»\"]")


def _get_extracted_value_from_text(text: str) -> str:
    """Return first quoted/guillemet value from question text, or empty."""
    if not text or not isinstance(text, str):
        return ""
    m = _VALUE_PATTERN.search(text)
    return (m.group(1) or "").strip() if m else ""


def _is_weak_extraction(text: str, lang: str) -> bool:
    """True if extracted phrase is suspiciously short or stopword-like."""
    val = _get_extracted_value_from_text(text or "")
    if len(val) < WEAK_MIN_LEN:
        return True
    if lang == "fa" and val in WEAK_STOPWORDS_FA:
        return True
    return False


def _pick_copy(lang: str) -> Dict[str, str]:
    return COPY_EN if (lang or "").strip().lower() in ("en", "en-us", "en-gb") else COPY_FA


def apply_companion_tone(question: Dict[str, Any], lang: str = "fa") -> Dict[str, Any]:
    """
    Transform a raw confirm_candidate question into companion-styled payload.
    Keeps all existing keys; adds display_title, display_body, display_choices, tone_version, ui_hints.
    """
    out = dict(question)
    copy = _pick_copy(lang or "fa")
    raw_text = (question.get("text") or "").strip()

    if not raw_text:
        raw_text = copy["body_template"].format(question="…")

    use_fallback = _is_weak_extraction(raw_text, lang)

    if use_fallback:
        display_body = copy["body_fallback_weak"]
    else:
        display_body = copy["body_template"].format(question=raw_text)

    out["display_title"] = copy["opener"]
    out["display_body"] = display_body
    out["display_choices"] = [
        {"key": "accept", "label": copy["choice_accept"]},
        {"key": "reject", "label": copy["choice_reject"]},
    ]
    out["tone_version"] = "companion_v1"
    out["ui_hints"] = {"style": "companion", "compact": True}
    # Optional minimal reassurance (non-legal)
    out["display_reassurance"] = copy["reassurance"]

    return out

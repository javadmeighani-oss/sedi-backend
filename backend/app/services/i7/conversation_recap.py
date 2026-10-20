# backend.app.services.i7.conversation_recap
"""One-phrase recap of what Sedi and the user last talked about (R-011, 2026-10-20).

Used by the in-app opener, the notification-origin opener and follow-up notifications so Sedi can say, naturally,
"last time we talked about X — shall we continue, or is something else on your mind?". Read-only, no schema,
deterministic (no LLM), consent-gated (memory.read) and retention-gated (eligible raw only). It never quotes the
user's own words back: it maps the recent turns to a small set of coarse topics.

Two privacy levels:
- "in_app": may name a verified disease concept ("بیماری ALS"), feelings, family.
- "lock_screen": push copy; disease -> "a health topic of yours"; feelings/family -> no topic (generic copy).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

_LIMIT = 12

_ACK_ONLY = frozenset(
    {
        "ندارم", "نه", "آره", "اره", "بله", "باشه", "ممنون", "مرسی", "خوبم", "هیچی", "خب", "اوکی", "سلام", "خداحافظ",
        "ok", "okay", "yes", "no", "yep", "nope", "thanks", "thank you", "none", "hi", "hello", "bye",
        "لا", "نعم", "شكرا", "حسنا", "مرحبا",
    }
)

# Ordered: the most specific topic wins; first match in the newest meaningful turn decides.
_CATEGORIES = (
    ("nutrition", ("رژیم", "برنامه غذایی", "برنامه‌ی غذایی", "برنامه ی غذایی", "تغذیه", "غذا", "diet", "meal", "nutrition", "food", "حمية", "تغذية", "طعام")),
    ("exercise", ("ورزش", "تمرین", "پیاده‌روی", "پیاده روی", "exercise", "workout", "training", "walking", "رياضة", "تمرين")),
    ("sleep", ("خواب", "بی‌خوابی", "بیخوابی", "sleep", "insomnia", "نوم", "أرق")),
    ("work", ("سر کار", "محل کار", "شغل", "رئیس", "همکار", "my job", "at work", "my boss", "العمل", "مديري")),
    ("family", ("مادرم", "پدرم", "همسرم", "فرزندم", "خانواده", "my mother", "my father", "my wife", "my husband", "my family", "أمي", "أبي", "زوجي", "عائلتي")),
)

_PHRASE_IN_APP = {
    "nutrition": {"fa": "برنامه‌ی غذایی و تغذیه‌ات", "en": "your eating and meal plan", "ar": "تغذيتك وخطتك الغذائية"},
    "exercise": {"fa": "ورزش و تحرکت", "en": "exercise and staying active", "ar": "الرياضة والحركة"},
    "sleep": {"fa": "خوابت", "en": "your sleep", "ar": "نومك"},
    "work": {"fa": "کار و دغدغه‌هات", "en": "work and what's on your plate", "ar": "العمل وما يشغلك"},
    "family": {"fa": "خانواده‌ات", "en": "your family", "ar": "عائلتك"},
    "feelings": {"fa": "حال و روحیه‌ات", "en": "how you've been feeling", "ar": "مزاجك وحالك"},
    "disease_generic": {"fa": "موضوع سلامتت", "en": "a health topic of yours", "ar": "موضوع صحي يهمك"},
}
# Lock-screen copy: only coarse, non-revealing topics (feelings / family give no topic at all).
_PHRASE_LOCK = {
    "nutrition": _PHRASE_IN_APP["nutrition"],
    "exercise": _PHRASE_IN_APP["exercise"],
    "sleep": _PHRASE_IN_APP["sleep"],
    "work": _PHRASE_IN_APP["work"],
    "disease": _PHRASE_IN_APP["disease_generic"],
}


def _lang(language: Optional[str]) -> str:
    raw = (language or "fa").strip().lower().split("-")[0]
    return raw if raw in ("fa", "en", "ar") else "en"


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def is_trivial_turn(text: str) -> bool:
    """Acknowledgements / one-word answers are never "the topic" (e.g. «ندارم»)."""
    t = _norm(text).strip(" .!؟?،,؛;…")
    if not t or t in _ACK_ONLY:
        return True
    return len(t.split()) < 2 and len(t) < 7


def classify_turn(text: str) -> Optional[str]:
    """Coarse category of one user turn, or None (pure function; disease concepts are resolved by the caller)."""
    t = _norm(text)
    if is_trivial_turn(t):
        return None
    for key, cues in _CATEGORIES:
        if any(c in t for c in cues):
            return key
    try:
        from backend.app.services.intelligence.psychological_interaction import _BE_HEARD_CUES

        if any(c in t for cues in _BE_HEARD_CUES.values() for c in cues):
            return "feelings"
    except Exception:
        pass
    return None


def _disease_label(db: Session, text: str, lang: str) -> Optional[str]:
    """Verified clinical concept named in the text -> its governed label (None when none / ambiguous)."""
    try:
        from backend.app.services.i5.know02.taxonomy import resolve_verified_concept_authority, verified_label_texts

        auth = resolve_verified_concept_authority(db, text or "", lang)
        if auth is None:
            return None
        for label_lang in (lang, "en"):
            labels = verified_label_texts(db, concept_id=auth.concept_id, language=label_lang)
            if labels:
                return str(labels[0]).strip() or None
        return None
    except Exception:
        return None


def recap_topic(db: Session, user_id: int, language: Optional[str] = "fa", *, privacy: str = "in_app") -> Optional[str]:
    """A short noun phrase for the last meaningful topic, or None (callers then use warm generic copy)."""
    lang = _lang(language)
    try:
        from backend.app.services.i6.consent_service import PERM_READ, has_permission
        from backend.app.services.i7.retention import query_eligible_raw

        if not has_permission(db, user_id, PERM_READ):
            return None
        rows = query_eligible_raw(db, user_id, limit=_LIMIT)
    except Exception:
        return None
    for row in rows or []:
        if int(getattr(row, "user_id", user_id) or user_id) != int(user_id):
            continue
        text = str(getattr(row, "user_message", "") or "")
        if is_trivial_turn(text):
            continue
        label = _disease_label(db, text, lang)
        if label:
            if privacy == "lock_screen":
                return _PHRASE_LOCK["disease"][lang]
            return {"fa": f"بیماری {label}", "en": label, "ar": label}[lang]
        key = classify_turn(text)
        if key is None:
            continue
        if privacy == "lock_screen":
            block = _PHRASE_LOCK.get(key)
            if block is None:
                return None  # feelings / family: say nothing specific on a lock screen
            return block[lang]
        return _PHRASE_IN_APP[key][lang]
    return None

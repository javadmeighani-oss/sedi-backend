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
from backend.app import sedi_copy

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
    # D-103: the newest chats are often about Sedi herself; name that instead of falling back to a stale memory.
    ("reminders", ("یادآور", "یاداور", "یادم بنداز", "نوتیف", "اعلان", "remind", "notification", "تذكير", "اشعار", "إشعار")),
    ("tone", ("لحن", "tone", "نحوه صحبت", "طرز حرف", "لهجة")),
)

# R-014: a disease topic is recapped with its aspect ("پیشگیری از دیابت"), so the opener proves Sedi followed the thread.
_ASPECTS = (
    ("prevention", ("پیشگیری", "prevent", "الوقاية", "وقاية"),
     sedi_copy.by_lang("recap.aspect.prevention")),
    ("diet", ("رژیم", "غذا", "تغذیه", "diet", "food", "حمية", "غذاء", "تغذية"),
     sedi_copy.by_lang("recap.aspect.diet")),
    ("exercise", ("ورزش", "تمرین", "پیاده", "exercise", "workout", "رياضة", "تمرين"),
     sedi_copy.by_lang("recap.aspect.exercise")),
    ("medication", ("دارو", "قرص", "medicine", "medication", "دواء"),
     sedi_copy.by_lang("recap.aspect.medication")),
    ("symptoms", ("علائم", "نشانه", "symptom", "أعراض"),
     sedi_copy.by_lang("recap.aspect.symptoms")),
)


def _disease_phrase(text: str, label: str, lang: str) -> str:
    t = _norm(text)
    for _key, cues, phrases in _ASPECTS:
        if any(c in t for c in cues):
            return phrases[lang].format(l=label)
    return {"fa": f"بیماری {label}", "en": label, "ar": label}[lang]


# Whole-token topics (substring cues such as «مو» would match «موضوع»). Checked BEFORE the broader categories.
_TOKEN_TOPICS = (
    ("hair", frozenset({"مو", "موها", "موهام", "موهای", "موهایم", "موهایت", "موی", "hair"})),
    ("skin", frozenset({"پوست", "پوستم", "جوش", "جوشها", "آکنه", "skin", "acne"})),
    ("weight", frozenset({"وزن", "وزنم", "لاغری", "چاقی", "چاق", "weight"})),
)


def _topic_by_token(text: str) -> Optional[str]:
    import re

    tokens = set(re.split(r"[^\w]+", _norm(text).replace("‌", " "))) - {""}
    for key, words in _TOKEN_TOPICS:
        if tokens & words:
            return key
    return None


_PHRASE_IN_APP = sedi_copy.nested_by_lang("recap.phrase_in_app")
# Lock-screen copy: only coarse, non-revealing topics (feelings / family give no topic at all).
_PHRASE_LOCK = sedi_copy.nested_by_lang("recap.phrase_lock")


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
    by_token = _topic_by_token(t)
    if by_token:
        return by_token
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


def _looks_like_story(text: str) -> bool:
    """D-103: a stored «interest/concern» that is really a sentence the user said («من مادرم این بیماری را داشت. …»)
    must never be spoken back as a topic. A real label is a few words without sentence punctuation."""
    t = " ".join((text or "").split())
    if not t:
        return True
    if len(t.split()) > 4 or len(t) > 40:
        return True
    return any(ch in t for ch in ".!؟?")


def _memory_topic(db: Session, user_id: int, lang: str, privacy: str) -> Optional[str]:
    """R-014: with no usable recent turn, name something Sedi REMEMBERS about the user (second memory), so openers and
    notifications stay personal. Lock screen: a disease stays generic, interests are never named."""
    try:
        from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty
        from backend.app.services.memory.memory_contract import render_stated_value

        by_key = {
            (str(r.domain), str(r.key)): render_stated_value(getattr(r, "value_json", None))
            for r in list_facts_readonly_or_empty(db, user_id)
        }
    except Exception:
        return None
    concern = by_key.get(("medical", "health_concerns"))
    if concern and not _looks_like_story(concern.split("،")[0]):
        if privacy == "lock_screen":
            return _PHRASE_LOCK["disease"][lang]
        first = concern.split("،")[0].strip()
        return {"fa": f"بیماری {first}", "en": first, "ar": first}[lang]
    if by_key.get(("work", "occupation")):
        return _PHRASE_IN_APP["work"][lang]
    interest = by_key.get(("preferences", "interests"))
    if interest and privacy != "lock_screen":
        first_interest = interest.split("،")[0].strip()
        if first_interest and not _looks_like_story(first_interest):
            return first_interest
    return None


def _lexicon_condition(text: str) -> Optional[str]:
    try:
        from backend.app.services.knowledge.stated_facts_extractor_v1 import mentioned_condition

        return mentioned_condition(text)
    except Exception:
        return None


def topic_phrase_from_text(text: str, language: Optional[str] = "fa", *, privacy: str = "in_app") -> Optional[str]:
    """A recap phrase for ONE piece of user text (e.g. the I7 derived continuity snippet), or None. Never echoes the
    user's own words: it maps to a condition+aspect or a coarse topic (R-013)."""
    lang = _lang(language)
    if is_trivial_turn(text):
        return None
    label = _lexicon_condition(text)
    if label:
        return _PHRASE_LOCK["disease"][lang] if privacy == "lock_screen" else _disease_phrase(text, label, lang)
    key = classify_turn(text)
    if key is None:
        return None
    block = (_PHRASE_LOCK if privacy == "lock_screen" else _PHRASE_IN_APP).get(key)
    return block[lang] if block else None


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
    had_recent_turn = False
    for row in rows or []:
        if int(getattr(row, "user_id", user_id) or user_id) != int(user_id):
            continue
        text = str(getattr(row, "user_message", "") or "")
        if is_trivial_turn(text):
            continue
        had_recent_turn = True
        label = _disease_label(db, text, lang) or _lexicon_condition(text)
        if label:
            if privacy == "lock_screen":
                return _PHRASE_LOCK["disease"][lang]
            return _disease_phrase(text, label, lang)
        key = classify_turn(text)
        if key is None:
            continue
        if privacy == "lock_screen":
            block = _PHRASE_LOCK.get(key)
            if block is None:
                return None  # feelings / family: say nothing specific on a lock screen
            return block[lang]
        return _PHRASE_IN_APP[key][lang]
    if had_recent_turn:
        # D-103: the user talked recently but about nothing we can name safely. Warm generic copy beats an old,
        # unrelated memory ("last time we talked about ..." must be about the LAST chat).
        return None
    return _memory_topic(db, user_id, lang, privacy)

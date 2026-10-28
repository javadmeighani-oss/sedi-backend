# backend.app.services.intelligence.specialist_offer
"""R-033 (Javad 2026-10-28): Sedi helps first, and alongside her own guidance she may OFFER to find a suitable specialist
(«اگه دوست داری، یه متخصص مناسب برات پیدا کنم»). When the user simply says «آره / بله / لطفاً», that answer IS the
find-a-specialist request — not an ordinary chat line the directory flow would ignore.

Deterministic, pure, fail-open: the orchestrator calls ``specialist_request_for_reply`` with Sedi's last reply and the
user's short answer; it returns an explicit request text (which the existing care-navigation directory flow already
understands) or ``None``.
"""
from __future__ import annotations

import re
from typing import Optional

_SPECIALIST = (
    "متخصص", "پزشک", "دکتر", "روانشناس", "روان‌شناس", "مشاور",
    "specialist", "doctor", "psychologist", "therapist", "counsellor", "counselor",
    "طبيب", "أخصائي", "اخصائي", "مختص", "معالج",
)
_FIND = re.compile(
    r"(?:پیدا\s*کنم|پیدا\s*کنم؟|پیدا\s*کنیم|بیابم|"
    r"\bfind\b|look\s+for|"
    r"أجد|اجد|أبحث|ابحث)",
    re.I,
)
_YES = frozenset(
    {
        "آره", "اره", "بله", "باشه", "لطفا", "لطفاً", "اوهوم", "آره لطفا", "اره لطفا", "بله لطفا", "بله لطفاً", "آره لطفاً",
        "پیدا کن", "آره پیدا کن", "اره پیدا کن", "بله پیدا کن", "خواهش میکنم", "مرسی آره", "آره ممنون", "اره ممنون", "بله ممنون",
        "yes", "yes please", "yeah", "yep", "sure", "ok", "okay", "please", "please do", "yes find one", "go ahead",
        "نعم", "أجل", "تمام", "حسنا", "حسناً", "نعم من فضلك", "من فضلك",
    }
)
_TRAILING = " .!؟?،,؛;…‌"


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("‌", " ").strip(_TRAILING + " ").split())


def is_specialist_offer(sedi_reply: Optional[str]) -> bool:
    """Sedi's reply ended by offering to find a specialist for the user."""
    text = (sedi_reply or "").strip()
    if not text:
        return False
    # the offer is a question near the END of the reply
    tail = text[-220:]
    if not tail.rstrip().endswith(("؟", "?")):
        return False
    low = tail.lower()
    return bool(_FIND.search(low)) and any(w in low for w in _SPECIALIST)


def is_affirmative(message: Optional[str]) -> bool:
    t = _norm(message or "")
    if not t or len(t.split()) > 5:
        return False
    return t in {_norm(y) for y in _YES} or any(t.startswith(_norm(y) + " ") for y in ("آره", "اره", "بله", "yes", "نعم"))


def _specialty(offer: str) -> str:
    low = (offer or "").lower()
    if any(w in low for w in ("روانشناس", "روان‌شناس", "psycholog", "therapist", "معالج", "نفسي")):
        return "psychologist"
    if any(w in low for w in ("پزشک", "دکتر", "doctor", "طبيب")):
        return "doctor"
    return "specialist"


# Wordings the existing care-navigation directory detector already recognises (checked in the tests).
_REQUEST = {
    "fa": {"psychologist": "یک متخصص روانشناسی برام پیدا کن", "doctor": "یه پزشک متخصص مناسب برام پیدا کن", "specialist": "یه متخصص مناسب برام پیدا کن"},
    "en": {"psychologist": "Please find me a specialist psychologist", "doctor": "Please find me a suitable specialist doctor", "specialist": "Please find me a suitable specialist"},
    "ar": {"psychologist": "ابحث لي عن أخصائي نفسي مختص", "doctor": "ابحث لي عن طبيب مختص مناسب", "specialist": "ابحث لي عن طبيب مختص مناسب"},
}


def specialist_request_for_reply(sedi_reply: Optional[str], user_message: Optional[str], language: str = "fa") -> Optional[str]:
    """The explicit find-a-specialist request when the user just accepted Sedi's offer, else None."""
    try:
        if not (is_specialist_offer(sedi_reply) and is_affirmative(user_message)):
            return None
        lang = (language or "fa").split("-")[0].lower()
        lang = lang if lang in _REQUEST else "en"
        return _REQUEST[lang][_specialty(sedi_reply or "")]
    except Exception:
        return None

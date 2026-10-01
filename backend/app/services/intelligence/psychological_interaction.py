"""CR-02 — Pure request-local interaction-need classification.

Deterministic. No DB, network, LLM, writes, or diagnosis/personality inference.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal, Optional

from backend.app.services.intelligence.contracts import (
    IntentId,
    IntentResult,
    LanguageCode,
    RequestKind,
)


class InteractionNeed(str, Enum):
    BE_HEARD = "be_heard"
    UNDERSTAND = "understand"
    DECIDE = "decide"
    ACT = "act"
    MOTIVATE = "motivate"
    EXPLORE = "explore"
    GENERAL = "general"


SkipRejectOutcome = Literal["skipped", "rejected"]

# Cue lexicons — surface language only; never diagnostic labels.
_BE_HEARD_CUES: dict[str, tuple[str, ...]] = {
    "en": (
        "feel",
        "feeling",
        "felt",
        "upset",
        "sad",
        "lonely",
        "overwhelmed",
        "anxious",
        "worried",
        "stressed",
        "frustrated",
        "just listen",
        "need to talk",
        "vent",
        "heard",
        "listening",
        "hard day",
        "tough day",
    ),
    "fa": (
        "احساس",
        "ناراحت",
        "غمگین",
        "تنها",
        "استرس",
        "نگران",
        "خسته شدم",
        "حالم بد",
        "فقط گوش",
        "حرف بزنم",
        "دلگیر",
        "آشفته",
    ),
    "ar": (
        "أشعر",
        "حزين",
        "قلق",
        "متوتر",
        "وحيد",
        "مرهق",
        "فقط استمع",
        "أريد أن أتحدث",
        "يوم صعب",
    ),
}

_DECIDE_CUES: dict[str, tuple[str, ...]] = {
    "en": (
        "should i",
        "which",
        "or not",
        "decide",
        "decision",
        "better option",
        "pros and cons",
        "tradeoff",
        "trade-off",
        "choose between",
        "what do you recommend",
    ),
    "fa": (
        "کدام",
        "یا نه",
        "تصمیم",
        "بهتره",
        "انتخاب کنم",
        "کدوم رو",
        "مزایا و معایب",
    ),
    "ar": (
        "أيهما",
        "أي خيار",
        "أقرر",
        "قرار",
        "أختار",
        "أيهما أفضل",
    ),
}

_ACT_CUES: dict[str, tuple[str, ...]] = {
    "en": (
        "how do i",
        "how can i",
        "help me start",
        "next step",
        "plan",
        "schedule",
        "action",
        "do today",
        "what should i do",
        "make a plan",
    ),
    "fa": (
        "چطور",
        "چگونه",
        "قدم بعدی",
        "برنامه",
        "شروع کنم",
        "چی کار کنم",
        "اقدام",
    ),
    "ar": (
        "كيف",
        "الخطوة التالية",
        "خطة",
        "ابدأ",
        "ماذا أفعل",
        "فعل",
    ),
}

_MOTIVATE_CUES: dict[str, tuple[str, ...]] = {
    "en": (
        "motivat",
        "stuck",
        "give up",
        "can't keep",
        "cannot keep",
        "adherence",
        "consistency",
        "discourage",
        "no energy",
        "keep going",
        "fall off",
    ),
    "fa": (
        "انگیزه",
        "ناامید",
        "ول کردم",
        "ادامه بدم",
        "سخت است",
        "حوصله ندارم",
        "بی‌انگیزه",
        "بی انگیزه",
    ),
    "ar": (
        "تحفيز",
        "محبط",
        "استسلم",
        "لا أستطيع المواصلة",
        "طاقة",
        "استمرار",
    ),
}

_SKIP_REJECT_PATTERNS: dict[str, tuple[tuple[str, SkipRejectOutcome], ...]] = {
    "en": (
        (r"\blater\b", "skipped"),
        (r"\bnot now\b", "skipped"),
        (r"\banother time\b", "skipped"),
        (r"\bprefer not\b", "rejected"),
        (r"\bi('d| would)? rather not\b", "rejected"),
        (r"\bdon'?t want( to)?\b", "rejected"),
        (r"\bno thanks\b", "rejected"),
        (r"\bskip( that)?\b", "skipped"),
    ),
    "fa": (
        (r"بعدا", "skipped"),
        (r"فعلا\s*نه", "skipped"),
        (r"الان نه", "skipped"),
        (r"نمی\s*خوام", "rejected"),
        (r"نمیخوام", "rejected"),
        (r"دوست ندارم", "rejected"),
        (r"بیخیال", "skipped"),
        (r"رد کن", "rejected"),
    ),
    "ar": (
        (r"لاحقا", "skipped"),
        (r"ليس الآن", "skipped"),
        (r"مو الحين", "skipped"),
        (r"لا أريد", "rejected"),
        (r"ما أبي", "rejected"),
        (r"تفضل لا", "rejected"),
        (r"تخطى", "skipped"),
    ),
}


def _norm(message: str) -> str:
    return " ".join((message or "").strip().lower().split())


def _has_cue(text: str, cues: tuple[str, ...]) -> bool:
    return any(c in text for c in cues)


def classify_interaction_need(
    *,
    message: str,
    intent: IntentResult,
    language: LanguageCode,
) -> InteractionNeed:
    """Classify request-local interaction need from surface cues + intent."""
    text = _norm(message)
    lang = language if language in ("en", "fa", "ar") else "en"

    if _has_cue(text, _BE_HEARD_CUES.get(lang, _BE_HEARD_CUES["en"])):
        return InteractionNeed.BE_HEARD
    if _has_cue(text, _DECIDE_CUES.get(lang, _DECIDE_CUES["en"])):
        return InteractionNeed.DECIDE
    if _has_cue(text, _MOTIVATE_CUES.get(lang, _MOTIVATE_CUES["en"])):
        return InteractionNeed.MOTIVATE
    if _has_cue(text, _ACT_CUES.get(lang, _ACT_CUES["en"])):
        return InteractionNeed.ACT

    # Intent / request-kind fallbacks (safe, non-diagnostic).
    if intent.request_kind is RequestKind.PERSONALIZED_PLAN:
        return InteractionNeed.ACT
    if intent.request_kind is RequestKind.ACTION:
        return InteractionNeed.ACT
    if intent.intent_id in (IntentId.SLEEP, IntentId.NUTRITION, IntentId.ACTIVITY):
        return InteractionNeed.UNDERSTAND
    if intent.intent_id is IntentId.HEALTH:
        return InteractionNeed.UNDERSTAND
    if intent.intent_id is IntentId.GENERAL:
        # Soft exploratory opening when no stronger cue fired.
        if any(tok in text for tok in ("tell me", "curious", "wonder", "explore", "بگو", "کنجکاو", "أخبرني")):
            return InteractionNeed.EXPLORE
        return InteractionNeed.GENERAL
    return InteractionNeed.GENERAL


def detect_discovery_skip_reject(
    message: str, language: LanguageCode
) -> Optional[SkipRejectOutcome]:
    """Detect explicit skip/reject of an optional discovery question."""
    text = _norm(message)
    if not text:
        return None
    lang = language if language in ("en", "fa", "ar") else "en"
    for pattern, outcome in _SKIP_REJECT_PATTERNS.get(lang, _SKIP_REJECT_PATTERNS["en"]):
        if re.search(pattern, text, flags=re.IGNORECASE):
            return outcome
    return None


def looks_substantive_discovery_answer(message: str) -> bool:
    """Conservative: non-empty reply that is not a pure greeting/ack."""
    text = _norm(message)
    if len(text) < 2:
        return False
    trivial = {
        "ok",
        "okay",
        "k",
        "thanks",
        "thank you",
        "hi",
        "hello",
        "hey",
        "سلام",
        "مرسی",
        "ممنون",
        "حسنا",
        "شكرا",
    }
    return text not in trivial


def append_discovery_question(primary_answer: str, localized_question: str) -> str:
    """Primary answer first, then exactly one discovery question."""
    answer = (primary_answer or "").rstrip()
    question = (localized_question or "").strip()
    if not answer:
        return question
    if not question:
        return answer
    return f"{answer}\n\n{question}"

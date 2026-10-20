"""CR-02 — Pure request-local interaction-need classification.

Deterministic. No DB, network, LLM, or writes.
No clinical labeling and no personality inference.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal, Optional, Sequence

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

# Cue lexicons — surface language only; never clinical labels.
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
        "grief",
        "grieving",
        "passed away",
        "lost my",
        "miss my",
        "depress",
        "hopeless",
        "scared",
        "afraid",
        "crying",
        "exhausted",
        "burned out",
        "burnt out",
        "fight with",
        "fought with",
        "argument with",
        "broke up",
        "got fired",
        "so tired of",
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
        "دلتنگ",
        "دلم تنگ",
        "دلم گرفته",
        "غصه",
        "گریه",
        "تنهام",
        "افسرده",
        "می‌ترسم",
        "میترسم",
        "ترسیدم",
        "کلافه",
        "عصبانی",
        "داغونم",
        "از دست دادم",
        "فوت کرد",
        "فوت شد",
        "دعوا",
        "دعوام",
        "اذیتم می",
        "نگرانم",
        "نگران شدم",
        "طلاق",
        "اخراج شدم",
        "وضع مالیم",
        "حالم خوب نیست",
        "خسته‌ام",
        "خسته ام",
        "کم آوردم",
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
        "خائف",
        "أبكي",
        "اشتقت",
        "توفي",
        "توفيت",
        "فقدت",
        "مكتئب",
        "يائس",
        "حزينة",
        "تعبان",
        "تعبت",
        "خلاف مع",
        "تشاجرت",
    ),
}

_DECIDE_CUES: dict[str, tuple[str, ...]] = {
    "en": (
        "which option",
        "which one",
        "or not",
        "decide between",
        "decision between",
        "better option",
        "pros and cons",
        "tradeoff",
        "trade-off",
        "choose between",
        "what do you recommend between",
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


# A message made only of greeting / "how are you" words is social, not a request for a next step
# (the "چطوری" in «سلام صدی، چطوری؟» must not read as the ACT cue «چطور»).
_GREETING_WORDS: dict[str, frozenset[str]] = {
    "en": frozenset({"hi", "hello", "hey", "sedi", "good", "morning", "evening", "afternoon", "night",
                     "how", "are", "you", "doing", "whats", "what's", "up", "yo", "there", "again", "thanks", "thank"}),
    "fa": frozenset({"سلام", "درود", "صدی", "چطوری", "چطوره", "خوبی", "خوبین", "حالت", "احوالت", "چطور", "صبح", "عصر",
                     "شب", "بخیر", "روزت", "روزتون", "ممنون", "مرسی", "هستی", "دوباره", "من", "اومدم", "برگشتم", "عزیزم", "جان"}),
    "ar": frozenset({"مرحبا", "أهلا", "اهلا", "السلام", "عليكم", "صدی", "صدي", "كيف", "حالك", "صباح", "مساء", "الخير", "شكرا"}),
}


def _is_social_greeting(text: str, lang: str) -> bool:
    tokens = [t.strip("،,.!؟?؛;:…-—'\"()") for t in text.split()]
    tokens = [t for t in tokens if t]
    if not tokens or len(tokens) > 8:
        return False
    words = _GREETING_WORDS.get(lang, _GREETING_WORDS["en"])
    return all(t in words for t in tokens)


# Help-seeking vs listen-only surface cues for emotionally loaded messages (BE_HEARD). Used only to decide
# whether governed psychology knowledge may accompany a listen-first reply.
_HELP_REQUEST_CUES: dict[str, tuple[str, ...]] = {
    "en": ("what can i do", "what should i do", "how do i", "how can i", "any tips", "tips", "what helps", "help me", "advice"),
    "fa": ("چیکار کنم", "چکار کنم", "چه کنم", "چی کار کنم", "چه کاری", "راهکار", "راه حل", "راهی دارم", "کمکم کن", "پیشنهاد"),
    "ar": ("ماذا أفعل", "ماذا افعل", "كيف أتعامل", "كيف اتعامل", "كيف أتخلص", "ساعدني", "نصائح", "ما الحل", "ماذا يساعد"),
}
_LISTEN_ONLY_CUES: dict[str, tuple[str, ...]] = {
    "en": ("just listen", "just need to talk", "just want to talk", "don't give advice", "dont give advice", "no advice", "just vent"),
    "fa": ("فقط گوش", "فقط می‌خوام حرف", "فقط میخوام حرف", "نصیحت نکن", "راهکار نمی‌خوام", "راهکار نمیخوام"),
    "ar": ("فقط استمع", "لا أريد نصيحة", "لا اريد نصيحة", "فضفضة", "أريد أن أتحدث فقط"),
}


def asks_for_help_not_just_listening(message: str, language: str) -> bool:
    """True when an emotional message also asks what to do and does not ask to be only listened to."""
    lang = language if language in ("en", "fa", "ar") else "en"
    text = _norm(message)
    if _has_cue(text, _LISTEN_ONLY_CUES[lang]):
        return False
    return _has_cue(text, _HELP_REQUEST_CUES[lang])


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
    if _is_social_greeting(text, lang):
        return InteractionNeed.GENERAL
    if _has_cue(text, _MOTIVATE_CUES.get(lang, _MOTIVATE_CUES["en"])):
        return InteractionNeed.MOTIVATE
    # ACT before DECIDE so "what should I do / next step" prefers action.
    if _has_cue(text, _ACT_CUES.get(lang, _ACT_CUES["en"])):
        return InteractionNeed.ACT
    if _has_cue(text, _DECIDE_CUES.get(lang, _DECIDE_CUES["en"])):
        return InteractionNeed.DECIDE

    # Intent / request-kind fallbacks (safe, non-clinical).
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
    return append_discovery_questions(primary_answer, (localized_question,))


def append_discovery_questions(
    primary_answer: str, localized_questions: Sequence[str]
) -> str:
    """Primary answer first, then up to two concise discovery questions."""
    answer = (primary_answer or "").rstrip()
    questions: list[str] = []
    for raw in localized_questions or ():
        q = (raw or "").strip()
        if q and q not in questions:
            questions.append(q)
        if len(questions) >= 2:
            break
    if not questions:
        return answer
    block = "\n\n".join(questions)
    if not answer:
        return block
    return f"{answer}\n\n{block}"

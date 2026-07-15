"""Section 15-I3 — versioned deterministic intent registry (no DB/LLM/network).

Message text is inspected only in request-local memory. Results contain safe
rule IDs and enums only — never message fragments or PII.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional, Sequence

from backend.app.services.intelligence.contracts import (
    IntentConfidenceBand,
    IntentId,
    IntentResult,
    LanguageCode,
    RequestKind,
)

REGISTRY_VERSION = "sedi.intent.registry.v1"

# Arabic / Persian presentation forms and similar → normalize for matching.
_AR_FA_TRANSLATION = str.maketrans(
    {
        "ك": "ک",
        "ي": "ی",
        "ى": "ی",
        "ة": "ه",
        "ؤ": "و",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٔ": "",
        "ٕ": "",
        "َ": "",
        "ُ": "",
        "ِ": "",
        "ّ": "",
        "ْ": "",
        "ً": "",
        "ٌ": "",
        "ٍ": "",
    }
)


def normalize_match_text(raw: str) -> str:
    """Unicode NFKC + script/case/whitespace/punctuation normalization."""
    text = unicodedata.normalize("NFKC", raw or "")
    text = text.translate(_AR_FA_TRANSLATION)
    # Join ZWNJ/ZWJ so می‌خواهم → میخواهم (personal action matching).
    text = text.replace("\u200c", "").replace("\u200d", "")
    text = text.casefold()
    # Keep letters/numbers; collapse other chars to spaces (conservative tokens).
    out: list[str] = []
    for ch in text:
        if ch.isalnum() or ch.isspace():
            out.append(ch)
        else:
            out.append(" ")
    collapsed = re.sub(r"\s+", " ", "".join(out)).strip()
    return collapsed


def _contains_phrase(normalized: str, phrase: str) -> bool:
    """Conservative phrase match on already-normalized text (word-boundary-ish)."""
    needle = normalize_match_text(phrase)
    if not needle:
        return False
    if " " in needle:
        return f" {needle} " in f" {normalized} "
    # Single token: require token boundary to avoid unrelated substrings.
    return bool(re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", normalized))


def _any_phrase(normalized: str, phrases: Sequence[str]) -> bool:
    return any(_contains_phrase(normalized, p) for p in phrases)


# FA nutrition personalized_plan — sole decision authority (language=fa).
_FA_NUTRITION_CONTEXT: tuple[str, ...] = ("برنامه غذایی", "برنامه تغذیه", "رژیم")
_FA_NEGATED_PLAN: tuple[str, ...] = (
    "نمیخواهم",
    "نمیخوام",
    "نساز",
    "طراحی نکن",
    "تنظیم نکن",
)
_FA_STRONG_CONSTRUCTION: tuple[str, ...] = ("بساز", "طراحی کن", "تنظیم کن")
_FA_STRONG_INFORMATIONAL: tuple[str, ...] = (
    "چیست",
    "چیه",
    "توضیح بده",
    "بدانم",
    "چطور",
    "چگونه",
)
_FA_WANT_PLAN: tuple[str, ...] = ("میخواهم", "میخوام")


def _fa_nutrition_personalized(normalized: str) -> bool:
    """
    Sole FA authority for nutrition/personalized_plan.

    After nutrition context: negation → construction → informational → want → False.
    Pronoun-only cues (برایم/برام) never personalize alone.
    """
    if not _any_phrase(normalized, _FA_NUTRITION_CONTEXT):
        return False
    if _any_phrase(normalized, _FA_NEGATED_PLAN):
        return False
    if _any_phrase(normalized, _FA_STRONG_CONSTRUCTION):
        return True
    if _any_phrase(normalized, _FA_STRONG_INFORMATIONAL):
        return False
    if _any_phrase(normalized, _FA_WANT_PLAN):
        return True
    return False


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    intent_id: IntentId
    request_kind: RequestKind
    confidence_band: IntentConfidenceBand
    priority: int  # lower wins among matches
    phrases_en: tuple[str, ...] = ()
    phrases_fa: tuple[str, ...] = ()
    phrases_ar: tuple[str, ...] = ()
    notification_origin: bool = False


# Priority bands (lower = higher precedence among heuristic matches).
# Notification origin is handled before these lists.
_RULES: tuple[_Rule, ...] = (
    _Rule(
        rule_id="i3.rule.reminder.action.v1",
        intent_id=IntentId.REMINDER,
        request_kind=RequestKind.ACTION,
        confidence_band=IntentConfidenceBand.HIGH,
        priority=10,
        phrases_en=(
            "remind me",
            "set a reminder",
            "create a reminder",
            "change my reminder",
            "reminder for",
        ),
        phrases_fa=("یادآوری کن", "یادآوری بذار", "یادآور بساز", "یاداوری تنظیم"),
        phrases_ar=("ذكرني", "تذكير", "اضف تذكير", "غير التذكير"),
    ),
    _Rule(
        rule_id="i3.rule.symptom.statement.v1",
        intent_id=IntentId.SYMPTOM,
        request_kind=RequestKind.INFORMATIONAL,
        confidence_band=IntentConfidenceBand.HIGH,
        priority=20,
        phrases_en=(
            "i have pain",
            "my head hurts",
            "chest pain",
            "i feel dizzy",
            "i have a fever",
            "nausea",
            "symptom",
        ),
        phrases_fa=("درد دارم", "سردرد", "درد سینه", "تب دارم", "سرگیجه", "علامت بیماری"),
        phrases_ar=("لدي الم", "صداع", "الم في الصدر", "حمى", "دوخة", "اعراض المرض"),
    ),
    _Rule(
        rule_id="i3.rule.nutrition.personalized.v1",
        intent_id=IntentId.NUTRITION,
        request_kind=RequestKind.PERSONALIZED_PLAN,
        confidence_band=IntentConfidenceBand.HIGH,
        priority=30,
        phrases_en=(
            "meal plan",
            "personal meal plan",
            "create a diet plan",
            "personalized nutrition",
            "diet plan for me",
            "nutrition plan for me",
        ),
        # FA personalized_plan is decided solely by `_fa_nutrition_personalized`.
        phrases_fa=(),
        phrases_ar=("خطة وجبات", "نظام غذائي شخصي", "خطة تغذية لي"),
    ),
    _Rule(
        rule_id="i3.rule.nutrition.informational.v1",
        intent_id=IntentId.NUTRITION,
        request_kind=RequestKind.INFORMATIONAL,
        confidence_band=IntentConfidenceBand.MEDIUM,
        priority=40,
        phrases_en=(
            "what foods contain",
            "foods that contain",
            "protein in food",
            "sources of protein",
            "nutrition facts",
            "is this food healthy",
        ),
        phrases_fa=(
            "برنامه غذایی",
            "برنامه تغذیه",
            "چه غذایی",
            "غذاهای حاوی",
            "منبع پروتئین",
            "اطلاعات تغذیه",
            "برنامه غذایی چیست",
            "درباره برنامه غذایی",
            "برنامه غذایی سالم",
            "ویژگی های برنامه غذایی",
        ),
        phrases_ar=(
            "ما الاطعمة",
            "اغذية تحتوي",
            "مصادر البروتين",
            "معلومات غذائية",
            "غذاء صحي",
            "الاغذية الصحية",
            "ما هو الغذاء الصحي",
            "اشرح التغذية",
            "معلومات عن التغذية",
        ),
    ),
    _Rule(
        rule_id="i3.rule.medication.informational.v1",
        intent_id=IntentId.MEDICATION,
        request_kind=RequestKind.INFORMATIONAL,
        confidence_band=IntentConfidenceBand.MEDIUM,
        priority=50,
        phrases_en=(
            "medication",
            "my medicine",
            "take a pill",
            "my pill",
            "pill dose",
            "dose of",
            "pharmacy",
        ),
        phrases_fa=("دارو", "قرص", "داروی من", "دوز دارو"),
        phrases_ar=("دواء", "حبوب", "جرعة", "صيدلية"),
    ),
    _Rule(
        rule_id="i3.rule.vitals.informational.v1",
        intent_id=IntentId.VITALS,
        request_kind=RequestKind.INFORMATIONAL,
        confidence_band=IntentConfidenceBand.MEDIUM,
        priority=55,
        phrases_en=("blood pressure", "heart rate", "oxygen saturation", "vital signs"),
        phrases_fa=("فشار خون", "ضربان قلب", "اکسیژن خون", "علائم حیاتی"),
        phrases_ar=("ضغط الدم", "معدل النبض", "تشبع الاكسجين", "علامات حيوية"),
    ),
    _Rule(
        rule_id="i3.rule.sleep.informational.v1",
        intent_id=IntentId.SLEEP,
        request_kind=RequestKind.INFORMATIONAL,
        confidence_band=IntentConfidenceBand.MEDIUM,
        priority=60,
        phrases_en=("sleep quality", "i slept", "insomnia", "how much sleep"),
        phrases_fa=("کیفیت خواب", "بی‌خوابی", "بی خوابی", "چند ساعت خواب", "ساعت خواب"),
        phrases_ar=("جودة النوم", "نومي", "ارق", "كم انام"),
    ),
    _Rule(
        rule_id="i3.rule.activity.informational.v1",
        intent_id=IntentId.ACTIVITY,
        request_kind=RequestKind.INFORMATIONAL,
        confidence_band=IntentConfidenceBand.MEDIUM,
        priority=65,
        phrases_en=("steps today", "workout", "exercise", "activity level", "walked"),
        phrases_fa=("تعداد قدم", "تمرین", "ورزش", "سطح فعالیت", "پیاده‌روی"),
        phrases_ar=("خطوات اليوم", "تمرين", "رياضة", "مستوى النشاط"),
    ),
    _Rule(
        rule_id="i3.rule.health.informational.v1",
        intent_id=IntentId.HEALTH,
        request_kind=RequestKind.INFORMATIONAL,
        confidence_band=IntentConfidenceBand.LOW,
        priority=80,
        phrases_en=("health tips", "healthy lifestyle", "my health", "wellness"),
        phrases_fa=("سلامت من", "نکته سلامت", "سبک زندگی سالم"),
        phrases_ar=("صحتي", "نصائح صحية", "نمط حياة صحي"),
    ),
    _Rule(
        rule_id="i3.rule.general.fallback.v1",
        intent_id=IntentId.GENERAL,
        request_kind=RequestKind.INFORMATIONAL,
        confidence_band=IntentConfidenceBand.FALLBACK,
        priority=1000,
        phrases_en=(),
        phrases_fa=(),
        phrases_ar=(),
    ),
)


class IntentResolutionError(Exception):
    """Fail-closed intent resolver failure (no raw content)."""


def list_intent_ids() -> tuple[IntentId, ...]:
    return tuple(IntentId)


def list_rule_ids() -> tuple[str, ...]:
    ids = [r.rule_id for r in _RULES]
    ids.append("i3.rule.notification_follow_up.origin.v1")
    return tuple(ids)


def resolve_intent(
    *,
    message: str,
    language: LanguageCode,
    has_verified_notification_origin: bool = False,
) -> IntentResult:
    """
    Deterministic intent resolution.

    Precedence:
    1) verified notification origin → notification_follow_up / follow_up
    2) matching rules by ascending priority then rule_id
    3) general fallback
    """
    if not isinstance(message, str):
        raise IntentResolutionError("invalid_message")
    if language not in ("fa", "ar", "en"):
        raise IntentResolutionError("invalid_language")

    if has_verified_notification_origin:
        return IntentResult(
            registry_version=REGISTRY_VERSION,
            intent_id=IntentId.NOTIFICATION_FOLLOW_UP,
            request_kind=RequestKind.FOLLOW_UP,
            confidence_band=IntentConfidenceBand.HIGH,
            rule_id="i3.rule.notification_follow_up.origin.v1",
        )

    normalized = normalize_match_text(message)
    matches: list[_Rule] = []
    for rule in _RULES:
        if rule.intent_id is IntentId.GENERAL and rule.priority >= 1000:
            continue
        # FA nutrition/personalized_plan: sole authority is the FA helper.
        if (
            rule.rule_id == "i3.rule.nutrition.personalized.v1"
            and language == "fa"
        ):
            matched = _fa_nutrition_personalized(normalized)
        else:
            phrases = (
                rule.phrases_en
                if language == "en"
                else rule.phrases_fa
                if language == "fa"
                else rule.phrases_ar
            )
            # Also try EN heuristics as secondary for shared latin medical terms.
            if language != "en":
                phrases = phrases + rule.phrases_en
            matched = _any_phrase(normalized, phrases)
        if matched:
            matches.append(rule)

    if not matches:
        fallback = _RULES[-1]
        return IntentResult(
            registry_version=REGISTRY_VERSION,
            intent_id=fallback.intent_id,
            request_kind=fallback.request_kind,
            confidence_band=fallback.confidence_band,
            rule_id=fallback.rule_id,
        )

    matches.sort(key=lambda r: (r.priority, r.rule_id))
    winner = matches[0]
    return IntentResult(
        registry_version=REGISTRY_VERSION,
        intent_id=winner.intent_id,
        request_kind=winner.request_kind,
        confidence_band=winner.confidence_band,
        rule_id=winner.rule_id,
    )


def resolve_intent_safe(
    *,
    message: str,
    language: LanguageCode,
    has_verified_notification_origin: bool = False,
) -> IntentResult:
    """Public seam used by orchestrator/tests."""
    return resolve_intent(
        message=message,
        language=language,
        has_verified_notification_origin=has_verified_notification_origin,
    )

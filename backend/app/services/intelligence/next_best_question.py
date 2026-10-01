"""CR-01 — Pure Next Best Question (NBQ) / soft-discovery selector.

Deterministic. No DB, network, LLM, writes, or legacy KC reads.
CR-01 stores metadata only; user-visible discovery belongs to CR-02.
"""

from __future__ import annotations

from typing import Optional, Sequence

from backend.app.services.intelligence.context_types import (
    ContextItem,
    ContextSnapshot,
)
from backend.app.services.intelligence.contracts import (
    DiscoveryDirective,
    IntentId,
    IntentResult,
    LanguageCode,
    ReadinessResult,
    ReadinessStatus,
)

# Intents where soft discovery is never appropriate (safety / specialized paths).
_NBQ_SUPPRESSED_INTENTS: frozenset[IntentId] = frozenset(
    {
        IntentId.SYMPTOM,
        IntentId.MEDICATION,
        IntentId.VITALS,
        IntentId.REMINDER,
        IntentId.NOTIFICATION_FOLLOW_UP,
    }
)

# Ordered soft-discovery candidates per supported intent (stable priority).
# Each entry: (target_key, sensitivity, template_id, priority)
_SOFT_DISCOVERY_CANDIDATES: dict[IntentId, tuple[tuple[str, str, str, int], ...]] = {
    IntentId.SLEEP: (
        ("routines.bedtime", "medium", "nbq.sleep.bedtime.v1", 10),
        ("routines.wake_time", "medium", "nbq.sleep.wake_time.v1", 20),
        ("lifestyle.sleep_quality", "medium", "nbq.sleep.sleep_quality.v1", 30),
    ),
    IntentId.NUTRITION: (
        ("lifestyle.food_habits", "medium", "nbq.nutrition.food_habits.v1", 10),
    ),
    IntentId.ACTIVITY: (
        ("lifestyle.activity_level", "medium", "nbq.activity.activity_level.v1", 10),
        (
            "routines.exercise_schedule",
            "medium",
            "nbq.activity.exercise_schedule.v1",
            20,
        ),
    ),
    IntentId.GENERAL: (
        (
            "preferences.response_length",
            "medium",
            "nbq.general.response_length.v1",
            10,
        ),
    ),
}

_TEMPLATES: dict[str, dict[str, str]] = {
    "nbq.sleep.bedtime.v1": {
        "en": "If you're open to it, what time do you usually go to bed?",
        "fa": "اگر مایلید بگویید، معمولاً چه ساعتی می‌خوابید؟",
        "ar": "إن رغبت، في أي وقت تنام عادة؟",
    },
    "nbq.sleep.wake_time.v1": {
        "en": "Optional: what time do you usually wake up?",
        "fa": "اختیاری: معمولاً چه ساعتی بیدار می‌شوید؟",
        "ar": "اختياري: في أي وقت تستيقظ عادة؟",
    },
    "nbq.sleep.sleep_quality.v1": {
        "en": "How would you describe your sleep lately, if you'd like to share?",
        "fa": "اگر مایلید، کیفیت خواب اخیرتان را چطور توصیف می‌کنید؟",
        "ar": "إن أحببت، كيف تصف جودة نومك مؤخراً؟",
    },
    "nbq.nutrition.food_habits.v1": {
        "en": "If helpful, what do your usual eating habits look like?",
        "fa": "اگر مفید است، عادت‌های غذایی معمولتان چگونه است؟",
        "ar": "إن كان مفيداً، كيف تبدو عاداتك الغذائية المعتادة؟",
    },
    "nbq.activity.activity_level.v1": {
        "en": "Optional: how active are you on a typical day?",
        "fa": "اختیاری: در یک روز معمولی چقدر فعال هستید؟",
        "ar": "اختياري: ما مدى نشاطك في يوم عادي؟",
    },
    "nbq.activity.exercise_schedule.v1": {
        "en": "If you'd like, when do you usually exercise?",
        "fa": "اگر مایلید، معمولاً چه زمانی ورزش می‌کنید؟",
        "ar": "إن رغبت، متى تمارس الرياضة عادة؟",
    },
    "nbq.general.response_length.v1": {
        "en": "Would you prefer brief answers, or a bit more detail?",
        "fa": "ترجیح می‌دهید پاسخ‌ها کوتاه باشد یا کمی مفصل‌تر؟",
        "ar": "هل تفضل إجابات مختصرة أم أكثر تفصيلاً قليلاً؟",
    },
}


def _localized(template_id: str, language: LanguageCode) -> str:
    block = _TEMPLATES[template_id]
    return block.get(language) or block["en"]


def _items_for_key(
    items: Sequence[ContextItem], target_key: str
) -> list[ContextItem]:
    return [i for i in items if i.canonical_key == target_key]


def _key_unavailable_for_discovery(
    items: Sequence[ContextItem], target_key: str
) -> bool:
    """True when the key is present, conflicted, denied, or stale (needs confirm)."""
    matched = _items_for_key(items, target_key)
    if not matched:
        return False
    for item in matched:
        if item.conflicted:
            return True
        if item.consent == "denied":
            return True
        if getattr(item, "freshness", None) == "stale":
            return True
        if item.active:
            return True
    return False


def select_next_best_question(
    *,
    snapshot: ContextSnapshot,
    intent: IntentResult,
    readiness: ReadinessResult,
    language: LanguageCode,
) -> Optional[DiscoveryDirective]:
    """
    Select at most one soft-discovery directive.

    Pure: reads only snapshot / intent / readiness / language.
    Hard I3 clarification always wins — caller must not invoke when
    readiness is not READY (also enforced here).
    """
    if readiness.status is not ReadinessStatus.READY:
        return None
    if intent.intent_id in _NBQ_SUPPRESSED_INTENTS:
        return None

    candidates = _SOFT_DISCOVERY_CANDIDATES.get(intent.intent_id)
    if not candidates:
        return None

    # Deterministic: iterate candidates in declared priority order.
    for target_key, sensitivity, template_id, priority in candidates:
        if _key_unavailable_for_discovery(snapshot.items, target_key):
            continue
        question_id = f"nbq.q.{intent.intent_id.value}.{target_key}.v1"
        return DiscoveryDirective(
            question_id=question_id,
            target_key=target_key,
            localized_question=_localized(template_id, language),
            sensitivity=sensitivity,  # type: ignore[arg-type]
            priority=priority,
        )
    return None

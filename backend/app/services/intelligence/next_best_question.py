"""CR-01 / CR-04B / CR-04F.1 / CR-04F.2 — Pure Next Best Question (NBQ) selector.

Deterministic. No DB, network, LLM, writes, or legacy KC reads.
CR-01 stores metadata only; user-visible discovery belongs to CR-02.
CR-04B adds optional message-scoped contextual candidates that may outrank
legacy NBQ only when relevance evidence is present in the current message.
CR-04F.1 adds request-local coverage-aware Tier-A progressive discovery on GENERAL.
CR-04F.2 adds CONFLICTED/STALE confirmation ahead of missing discovery.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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
from backend.app.services.intelligence.user_understanding_coverage import (
    REGISTERED_TARGETS,
    TIER_A_GENERAL_PRIORITY,
    TIER_A_TARGETS,
    TIER_C_NEVER_MISSING_DRIVEN,
    CoverageState,
    coverage_state_for_key,
    is_safe_missing_for_discovery,
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
# GENERAL uses Tier-A progressive order (CR-04F.1).
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
            "preferences.interests",
            "medium",
            "nbq.general.interests.v1",
            10,
        ),
        (
            "preferences.communication_style",
            "medium",
            "nbq.general.communication_style.v1",
            20,
        ),
        (
            "preferences.listen_before_advice",
            "medium",
            "nbq.general.listen_before_advice.v1",
            30,
        ),
        (
            "preferences.response_length",
            "medium",
            "nbq.general.response_length.v1",
            40,
        ),
    ),
}

_TIER_A_TEMPLATE_BY_KEY: dict[str, tuple[str, str, int]] = {
    "preferences.interests": ("medium", "nbq.general.interests.v1", 10),
    "preferences.communication_style": (
        "medium",
        "nbq.general.communication_style.v1",
        20,
    ),
    "preferences.listen_before_advice": (
        "medium",
        "nbq.general.listen_before_advice.v1",
        30,
    ),
    "preferences.response_length": ("medium", "nbq.general.response_length.v1", 40),
}

# Intent-scoped confirmation keys (sleep/nutrition/activity).
_INTENT_CONFIRM_KEYS: dict[IntentId, frozenset[str]] = {
    IntentId.SLEEP: frozenset(
        {"routines.bedtime", "routines.wake_time", "lifestyle.sleep_quality"}
    ),
    IntentId.NUTRITION: frozenset({"lifestyle.food_habits"}),
    IntentId.ACTIVITY: frozenset(
        {"lifestyle.activity_level", "routines.exercise_schedule"}
    ),
}

# Stable confirmation priority across all confirmable targets (lower = first).
_CONFIRMATION_PRIORITY: tuple[str, ...] = (
    "preferences.interests",
    "preferences.communication_style",
    "preferences.listen_before_advice",
    "preferences.response_length",
    "work.work_schedule",
    "barriers.time_constraints",
    "routines.bedtime",
    "routines.wake_time",
    "lifestyle.sleep_quality",
    "lifestyle.food_habits",
    "lifestyle.activity_level",
    "routines.exercise_schedule",
)

_CONFIRMATION_PRIORITY_INDEX: dict[str, int] = {
    k: i for i, k in enumerate(_CONFIRMATION_PRIORITY)
}

# Bounded localized field labels for confirmation templates.
_FIELD_LABELS: dict[str, dict[str, str]] = {
    "preferences.interests": {
        "en": "interests",
        "fa": "علاقه‌مندی‌ها",
        "ar": "الاهتمامات",
    },
    "preferences.communication_style": {
        "en": "communication style",
        "fa": "سبک گفت‌وگو",
        "ar": "أسلوب التواصل",
    },
    "preferences.listen_before_advice": {
        "en": "listen-first preference",
        "fa": "ترجیح گوش‌دادن پیش از پیشنهاد",
        "ar": "تفضيل الاستماع قبل الاقتراح",
    },
    "preferences.response_length": {
        "en": "response length",
        "fa": "طول پاسخ",
        "ar": "طول الإجابة",
    },
    "routines.bedtime": {"en": "bedtime", "fa": "ساعت خواب", "ar": "وقت النوم"},
    "routines.wake_time": {
        "en": "wake time",
        "fa": "ساعت بیداری",
        "ar": "وقت الاستيقاظ",
    },
    "lifestyle.sleep_quality": {
        "en": "sleep quality",
        "fa": "کیفیت خواب",
        "ar": "جودة النوم",
    },
    "lifestyle.food_habits": {
        "en": "eating habits",
        "fa": "عادت‌های غذایی",
        "ar": "العادات الغذائية",
    },
    "lifestyle.activity_level": {
        "en": "activity level",
        "fa": "سطح فعالیت",
        "ar": "مستوى النشاط",
    },
    "routines.exercise_schedule": {
        "en": "exercise schedule",
        "fa": "برنامه ورزش",
        "ar": "جدول الرياضة",
    },
    "work.work_schedule": {
        "en": "work schedule",
        "fa": "برنامه کاری",
        "ar": "جدول العمل",
    },
    "barriers.time_constraints": {
        "en": "time constraints",
        "fa": "محدودیت زمانی",
        "ar": "قيود الوقت",
    },
}

# CR-04B — contextual candidates. Lower priority number wins among relevant hits.
# These outrank legacy NBQ only when message relevance is true.
_WORK_SCHEDULE_RELEVANCE_CUES: tuple[str, ...] = (
    "night shift",
    "night shifts",
    "shift work",
    "work schedule",
    "work shifts",
    "my shifts",
    "on shift",
    "working nights",
    "شیفت کاری",
    "شیفت شب",
    "شیفت",
    "ساعات کاری",
    "دوام العمل",
    "دوام ليلي",
    "دوام لیلي",
    "ورديات",
)

_TIME_CONSTRAINT_RELEVANCE_CUES: tuple[str, ...] = (
    "don't have enough time",
    "do not have enough time",
    "dont have enough time",
    "not enough time",
    "no time to",
    "lack of time",
    "limited time",
    "too busy to",
    "وقت کم",
    "وقت ندارم",
    "وقت خیلی کم",
    "وقت کافی ندارم",
    "ليس لدي وقت",
    "ليس لدي وقت كاف",
    "ما عندي وقت",
    "لا وقت لدي",
)


@dataclass(frozen=True)
class _ContextualCandidate:
    target_key: str
    sensitivity: str
    template_id: str
    priority: int
    compatible_intents: frozenset[IntentId]
    relevance_cues: tuple[str, ...]


_CONTEXTUAL_CANDIDATES: tuple[_ContextualCandidate, ...] = (
    _ContextualCandidate(
        target_key="work.work_schedule",
        sensitivity="medium",
        template_id="nbq.contextual.work_schedule.v1",
        priority=1,
        compatible_intents=frozenset({IntentId.GENERAL, IntentId.SLEEP}),
        relevance_cues=_WORK_SCHEDULE_RELEVANCE_CUES,
    ),
    _ContextualCandidate(
        target_key="barriers.time_constraints",
        sensitivity="high",
        template_id="nbq.contextual.time_constraints.v1",
        priority=2,
        compatible_intents=frozenset(
            {
                IntentId.GENERAL,
                IntentId.SLEEP,
                IntentId.NUTRITION,
                IntentId.ACTIVITY,
            }
        ),
        relevance_cues=_TIME_CONSTRAINT_RELEVANCE_CUES,
    ),
)

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
    "nbq.general.interests.v1": {
        "en": (
            "Optional: what would you most like Sedi to help you with "
            "going forward?"
        ),
        "fa": "اختیاری: دوست دارید سِدی بیشتر در چه زمینه‌ای کمکتان کند؟",
        "ar": "اختياري: بماذا تود أن يساعدك سِدي أكثر من الآن فصاعداً؟",
    },
    "nbq.general.communication_style.v1": {
        "en": (
            "If you're open to it, do you prefer a direct style, a supportive "
            "conversational style, or something in between?"
        ),
        "fa": (
            "اگر مایلید بگویید، سبک مستقیم را ترجیح می‌دهید، گفت‌وگوی "
            "حمایت‌گرانه، یا چیزی بین این دو؟"
        ),
        "ar": (
            "إن رغبت، هل تفضل أسلوباً مباشراً، أم أسلوباً حوارياً داعماً، "
            "أم شيئاً بينهما؟"
        ),
    },
    "nbq.general.listen_before_advice.v1": {
        "en": (
            "When something is bothering you, do you usually prefer that I "
            "listen first before suggesting solutions?"
        ),
        "fa": (
            "وقتی چیزی ناراحتتان می‌کند، معمولاً ترجیح می‌دهید اول گوش کنم "
            "و بعد پیشنهاد بدهم؟"
        ),
        "ar": (
            "عندما يزعجك أمر ما، هل تفضل عادة أن أستمع أولاً قبل اقتراح الحلول؟"
        ),
    },
    "nbq.general.response_length.v1": {
        "en": "Would you prefer brief answers, or a bit more detail?",
        "fa": "ترجیح می‌دهید پاسخ‌ها کوتاه باشد یا کمی مفصل‌تر؟",
        "ar": "هل تفضل إجابات مختصرة أم أكثر تفصيلاً قليلاً؟",
    },
    "nbq.contextual.work_schedule.v1": {
        "en": "If you're open to it, what does your work schedule usually look like?",
        "fa": "اگر مایلید بگویید، برنامه کاری‌تان معمولاً چگونه است؟",
        "ar": "إن رغبت، كيف يبدو جدول عملك عادة؟",
    },
    "nbq.contextual.time_constraints.v1": {
        "en": "Optional: how much time do you usually have for this?",
        "fa": "اختیاری: معمولاً برای این کار چقدر وقت دارید؟",
        "ar": "اختياري: كم من الوقت يتوفر لديك عادة لهذا؟",
    },
    # CR-04F.2 confirmation templates ({field} substituted at render time).
    "nbq.confirm.stale.v1": {
        "en": "I may have an older value for your {field}. What should I use now?",
        "fa": (
            "ممکن است مقدار قدیمی‌تری برای {field} شما داشته باشم. "
            "الان چه چیزی را استفاده کنم؟"
        ),
        "ar": "قد يكون لدي قيمة أقدم لـ {field} لديك. ماذا يجب أن أستخدم الآن؟",
    },
    "nbq.confirm.conflict.v1": {
        "en": (
            "I have conflicting information about your {field}. "
            "What should I use going forward?"
        ),
        "fa": (
            "اطلاعات متناقضی دربارهٔ {field} شما دارم. "
            "از این به بعد چه چیزی را استفاده کنم؟"
        ),
        "ar": (
            "لدي معلومات متعارضة حول {field} لديك. "
            "ماذا يجب أن أستخدم من الآن فصاعداً؟"
        ),
    },
}


def _localized(template_id: str, language: LanguageCode) -> str:
    block = _TEMPLATES[template_id]
    return block.get(language) or block["en"]


def _field_label(target_key: str, language: LanguageCode) -> str:
    block = _FIELD_LABELS.get(target_key) or {}
    return block.get(language) or block.get("en") or target_key.split(".", 1)[-1]


def _localized_confirmation(
    kind: str, target_key: str, language: LanguageCode
) -> str:
    template_id = (
        "nbq.confirm.conflict.v1" if kind == "conflict" else "nbq.confirm.stale.v1"
    )
    return _localized(template_id, language).format(
        field=_field_label(target_key, language)
    )


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


def _coverage_blocks_discovery(snapshot: ContextSnapshot, target_key: str) -> bool:
    """CR-04F.1: ask only MISSING; skip KNOWN/DENIED/CONFLICTED/STALE."""
    state = coverage_state_for_key(snapshot, target_key)
    if state is CoverageState.NOT_APPLICABLE:
        # Unregistered soft keys fall back to legacy presence gate.
        return _key_unavailable_for_discovery(snapshot.items, target_key)
    return state is not CoverageState.MISSING


def _norm_message(message: str) -> str:
    text = (message or "").strip().lower()
    text = text.replace("\u200c", "").replace("\u200d", "")
    return text


def _cue_present(text: str, cue: str) -> bool:
    needle = _norm_message(cue)
    if not needle:
        return False
    if " " in needle:
        return bool(
            re.search(
                rf"(?<!\w){re.escape(needle)}(?!\w)",
                text,
                flags=re.UNICODE,
            )
        )
    return bool(
        re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", text, flags=re.UNICODE)
    )


def _message_relevant(message: str, cues: tuple[str, ...]) -> bool:
    text = _norm_message(message)
    if not text:
        return False
    ordered = sorted((c for c in cues if c), key=len, reverse=True)
    return any(_cue_present(text, c) for c in ordered)


def _confirmation_eligible(
    *,
    target_key: str,
    intent: IntentResult,
    message: str,
) -> bool:
    """Reuse existing intent/context rules for conflict/stale confirmation."""
    if target_key in TIER_C_NEVER_MISSING_DRIVEN:
        return False
    if target_key in TIER_A_TARGETS:
        return intent.intent_id is IntentId.GENERAL

    for cand in _CONTEXTUAL_CANDIDATES:
        if cand.target_key != target_key:
            continue
        if intent.intent_id not in cand.compatible_intents:
            return False
        return _message_relevant(message, cand.relevance_cues)

    allowed = _INTENT_CONFIRM_KEYS.get(intent.intent_id)
    if allowed is not None and target_key in allowed:
        return True
    return False


def _select_confirmation_directive(
    *,
    snapshot: ContextSnapshot,
    intent: IntentResult,
    language: LanguageCode,
    message: str,
    state: CoverageState,
    kind: str,
) -> Optional[DiscoveryDirective]:
    """At most one eligible confirmation for CONFLICTED or STALE."""
    hits: list[str] = []
    for target_key in _CONFIRMATION_PRIORITY:
        if coverage_state_for_key(snapshot, target_key) is not state:
            continue
        if not _confirmation_eligible(
            target_key=target_key, intent=intent, message=message
        ):
            continue
        hits.append(target_key)
    if not hits:
        for target_key in sorted(REGISTERED_TARGETS):
            if target_key in _CONFIRMATION_PRIORITY_INDEX:
                continue
            if coverage_state_for_key(snapshot, target_key) is not state:
                continue
            if not _confirmation_eligible(
                target_key=target_key, intent=intent, message=message
            ):
                continue
            hits.append(target_key)
    if not hits:
        return None
    winner = hits[0]
    sensitivity = "high" if winner == "barriers.time_constraints" else "medium"
    priority = _CONFIRMATION_PRIORITY_INDEX.get(winner, 100)
    question_id = f"nbq.q.confirm.{kind}.{winner}.v1"
    return DiscoveryDirective(
        question_id=question_id,
        target_key=winner,
        localized_question=_localized_confirmation(kind, winner, language),
        sensitivity=sensitivity,  # type: ignore[arg-type]
        priority=priority,
    )


def _select_contextual_directive(
    *,
    snapshot: ContextSnapshot,
    intent: IntentResult,
    language: LanguageCode,
    message: str,
) -> Optional[DiscoveryDirective]:
    """Return at most one contextual directive when message relevance is true."""
    hits: list[_ContextualCandidate] = []
    for cand in _CONTEXTUAL_CANDIDATES:
        if intent.intent_id not in cand.compatible_intents:
            continue
        if not _message_relevant(message, cand.relevance_cues):
            continue
        if _coverage_blocks_discovery(snapshot, cand.target_key):
            continue
        hits.append(cand)
    if not hits:
        return None
    hits.sort(key=lambda c: (c.priority, c.target_key))
    winner = hits[0]
    question_id = f"nbq.q.{intent.intent_id.value}.{winner.target_key}.v1"
    return DiscoveryDirective(
        question_id=question_id,
        target_key=winner.target_key,
        localized_question=_localized(winner.template_id, language),
        sensitivity=winner.sensitivity,  # type: ignore[arg-type]
        priority=winner.priority,
    )


def _select_tier_a_directive(
    *,
    snapshot: ContextSnapshot,
    intent: IntentResult,
    language: LanguageCode,
) -> Optional[DiscoveryDirective]:
    """CR-04F.1 — at most one safe missing Tier-A question (GENERAL only)."""
    if intent.intent_id is not IntentId.GENERAL:
        return None
    for target_key in TIER_A_GENERAL_PRIORITY:
        if not is_safe_missing_for_discovery(snapshot, target_key):
            continue
        meta = _TIER_A_TEMPLATE_BY_KEY.get(target_key)
        if meta is None:
            continue
        sensitivity, template_id, priority = meta
        question_id = f"nbq.q.{intent.intent_id.value}.{target_key}.v1"
        return DiscoveryDirective(
            question_id=question_id,
            target_key=target_key,
            localized_question=_localized(template_id, language),
            sensitivity=sensitivity,  # type: ignore[arg-type]
            priority=priority,
        )
    return None


def _select_intent_soft_directive(
    *,
    snapshot: ContextSnapshot,
    intent: IntentResult,
    language: LanguageCode,
) -> Optional[DiscoveryDirective]:
    """Intent-specific soft candidates (sleep/nutrition/activity). GENERAL uses Tier-A."""
    if intent.intent_id is IntentId.GENERAL:
        # GENERAL soft list is Tier-A; already handled by _select_tier_a_directive.
        return None
    candidates = _SOFT_DISCOVERY_CANDIDATES.get(intent.intent_id)
    if not candidates:
        return None
    for target_key, sensitivity, template_id, priority in candidates:
        if _coverage_blocks_discovery(snapshot, target_key):
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


def select_next_best_question(
    *,
    snapshot: ContextSnapshot,
    intent: IntentResult,
    readiness: ReadinessResult,
    language: LanguageCode,
    message: str = "",
) -> Optional[DiscoveryDirective]:
    """
    Select at most one soft-discovery / confirmation directive.

    Pure: reads only snapshot / intent / readiness / language / optional message.
    Hard I3 clarification always wins — caller must not invoke when
    readiness is not READY (also enforced here).

    Selection order (CR-04F.2):
      A) eligible CONFLICTED confirmation
      B) eligible STALE confirmation
      C) existing CR-04F.1 selection:
         1) relevant contextual candidate
         2) safe missing Tier-A (GENERAL)
         3) intent-specific soft candidate
         4) none
    """
    if readiness.status is not ReadinessStatus.READY:
        return None
    if intent.intent_id in _NBQ_SUPPRESSED_INTENTS:
        return None

    # A) CONFLICTED confirmation outranks missing discovery.
    conflict = _select_confirmation_directive(
        snapshot=snapshot,
        intent=intent,
        language=language,
        message=message,
        state=CoverageState.CONFLICTED,
        kind="conflict",
    )
    if conflict is not None:
        return conflict

    # B) STALE confirmation outranks missing discovery.
    stale = _select_confirmation_directive(
        snapshot=snapshot,
        intent=intent,
        language=language,
        message=message,
        state=CoverageState.STALE,
        kind="stale",
    )
    if stale is not None:
        return stale

    # C) existing CR-04F.1 selection unchanged.
    contextual = _select_contextual_directive(
        snapshot=snapshot,
        intent=intent,
        language=language,
        message=message,
    )
    if contextual is not None:
        return contextual

    tier_a = _select_tier_a_directive(
        snapshot=snapshot, intent=intent, language=language
    )
    if tier_a is not None:
        return tier_a

    return _select_intent_soft_directive(
        snapshot=snapshot, intent=intent, language=language
    )

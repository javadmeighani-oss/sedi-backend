"""Section 15-I3 — Missing-information / readiness engine (snapshot-only).

No DB Session, no UCS, no RAG, no QuestionEngine, no LLM.
Compares intent requirements only against the I2 ContextSnapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from backend.app.services.intelligence.context_types import (
    ContextItem,
    ContextSnapshot,
)
from backend.app.services.intelligence.contracts import (
    ClarificationResult,
    FactRequirementOutcome,
    FactRequirementStatus,
    IntentId,
    IntentResult,
    LanguageCode,
    ReadinessResult,
    ReadinessStatus,
    RequestKind,
)

# Stable confirmed-none keys (must appear explicitly in snapshot).
CONFIRMED_NONE_CONDITIONS = "health.condition.confirmed_none"
CONFIRMED_NONE_MEDICATIONS = "health.medication.confirmed_none"
CONFIRMED_NONE_RESTRICTIONS = "lifestyle.restriction.confirmed_none"
CONFIRMED_NONE_ALLERGIES = "health.allergy.confirmed_none"


class MissingInformationError(Exception):
    """Fail-closed readiness failure (no raw content)."""


@dataclass(frozen=True)
class FactRequirement:
    requirement_id: str
    canonical_key: str  # exact key OR prefix ending with ".*" OR confirmed-none key
    priority: int
    match_mode: str  # exact | prefix | confirmed_none_or_prefix
    requires_confirmation: bool = False
    supported: bool = True


def _nutrition_personalized_requirements() -> tuple[FactRequirement, ...]:
    return (
        FactRequirement("nut.goal", "lifestyle.goal.*", 10, "prefix"),
        FactRequirement("nut.birth_year", "profile.birth_year", 20, "exact"),
        FactRequirement("nut.sex", "profile.sex", 30, "exact"),
        FactRequirement("nut.height", "profile.height_cm", 40, "exact"),
        FactRequirement("nut.weight", "profile.weight_kg", 50, "exact"),
        FactRequirement(
            "nut.activity", "profile.activity_level", 60, "exact", supported=False
        ),
        FactRequirement(
            "nut.allergies",
            "health.allergy.*",
            70,
            "confirmed_none_or_prefix",
            supported=False,
        ),
        FactRequirement(
            "nut.conditions",
            "health.condition.*",
            80,
            "confirmed_none_or_prefix",
            requires_confirmation=True,
        ),
        FactRequirement(
            "nut.medications",
            "health.medication.*",
            90,
            "confirmed_none_or_prefix",
            requires_confirmation=True,
        ),
        FactRequirement(
            "nut.restrictions",
            "lifestyle.restriction.*",
            100,
            "confirmed_none_or_prefix",
        ),
        FactRequirement(
            "nut.meal_prefs", "nutrition.meal_preferences", 110, "exact", supported=False
        ),
        FactRequirement(
            "nut.meal_schedule", "nutrition.meal_schedule", 120, "exact", supported=False
        ),
        FactRequirement(
            "nut.budget", "nutrition.budget", 130, "exact", supported=False
        ),
        FactRequirement(
            "nut.food_prep",
            "nutrition.food_preparation",
            140,
            "exact",
            supported=False,
        ),
    )


def requirements_for(intent: IntentResult) -> tuple[FactRequirement, ...]:
    if (
        intent.intent_id is IntentId.NUTRITION
        and intent.request_kind is RequestKind.PERSONALIZED_PLAN
    ):
        return _nutrition_personalized_requirements()
    # Informational / other intents: no missing-info interrogation by default.
    return ()


def _confirmed_none_key_for_prefix(prefix: str) -> Optional[str]:
    if prefix.startswith("health.condition"):
        return CONFIRMED_NONE_CONDITIONS
    if prefix.startswith("health.medication"):
        return CONFIRMED_NONE_MEDICATIONS
    if prefix.startswith("lifestyle.restriction"):
        return CONFIRMED_NONE_RESTRICTIONS
    if prefix.startswith("health.allergy"):
        return CONFIRMED_NONE_ALLERGIES
    return None


def _items_for_requirement(
    items: Sequence[ContextItem], req: FactRequirement
) -> list[ContextItem]:
    key = req.canonical_key
    if req.match_mode == "exact":
        return [i for i in items if i.canonical_key == key]
    if req.match_mode == "prefix":
        prefix = key[:-2] if key.endswith(".*") else key
        return [
            i
            for i in items
            if i.canonical_key.startswith(prefix)
            and not i.canonical_key.endswith(".confirmed_none")
        ]
    if req.match_mode == "confirmed_none_or_prefix":
        prefix = key[:-2] if key.endswith(".*") else key
        none_key = _confirmed_none_key_for_prefix(prefix)
        matched = [
            i
            for i in items
            if i.canonical_key.startswith(prefix)
            or (none_key is not None and i.canonical_key == none_key)
        ]
        return matched
    return []


def _is_present_candidate(item: ContextItem, *, require_confirmation: bool) -> bool:
    if item.conflicted or item.consent == "denied" or not item.active:
        return False
    if require_confirmation and getattr(item, "freshness", None) == "stale":
        return False
    return True


def _is_confirmed(item: ContextItem) -> bool:
    return item.consent == "explicit"


def _is_valid_satisfier(item: ContextItem, *, require_confirmation: bool) -> bool:
    if not _is_present_candidate(item, require_confirmation=require_confirmation):
        return False
    if require_confirmation:
        return _is_confirmed(item)
    # Profile core height/weight may be legacy_scope and still satisfy.
    if item.canonical_key in ("profile.height_cm", "profile.weight_kg"):
        return True
    if item.canonical_key in (
        "profile.birth_year",
        "profile.sex",
    ):
        return True
    # Collection members: active + not denied + not conflicted is enough presence.
    return True


def _evaluate_one(
    items: Sequence[ContextItem], req: FactRequirement
) -> FactRequirementOutcome:
    if not req.supported:
        if req.match_mode == "confirmed_none_or_prefix":
            prefix = (
                req.canonical_key[:-2]
                if req.canonical_key.endswith(".*")
                else req.canonical_key
            )
            none_key = _confirmed_none_key_for_prefix(prefix)
            if none_key is not None:
                for item in items:
                    if item.canonical_key == none_key and _is_valid_satisfier(
                        item, require_confirmation=False
                    ):
                        return FactRequirementOutcome(
                            requirement_id=req.requirement_id,
                            canonical_key=req.canonical_key.rstrip(".*"),
                            status=FactRequirementStatus.PRESENT,
                            priority=req.priority,
                        )
        return FactRequirementOutcome(
            requirement_id=req.requirement_id,
            canonical_key=req.canonical_key.rstrip(".*"),
            status=FactRequirementStatus.UNAVAILABLE,
            priority=req.priority,
        )

    matched = _items_for_requirement(items, req)
    if not matched:
        return FactRequirementOutcome(
            requirement_id=req.requirement_id,
            canonical_key=req.canonical_key.rstrip(".*"),
            status=FactRequirementStatus.MISSING,
            priority=req.priority,
        )

    # Confirmed-none alone satisfies collection/prefix-or-none requirements.
    none_key = None
    if req.match_mode == "confirmed_none_or_prefix":
        prefix = req.canonical_key[:-2] if req.canonical_key.endswith(".*") else req.canonical_key
        none_key = _confirmed_none_key_for_prefix(prefix)
        for item in matched:
            if none_key and item.canonical_key == none_key and _is_valid_satisfier(item, require_confirmation=False):
                return FactRequirementOutcome(
                    requirement_id=req.requirement_id,
                    canonical_key=req.canonical_key.rstrip(".*"),
                    status=FactRequirementStatus.PRESENT,
                    priority=req.priority,
                )

    non_none = [
        i for i in matched if not (none_key and i.canonical_key == none_key)
    ]
    valid = [
        i
        for i in non_none
        if _is_valid_satisfier(i, require_confirmation=req.requires_confirmation)
    ]
    if valid:
        return FactRequirementOutcome(
            requirement_id=req.requirement_id,
            canonical_key=req.canonical_key.rstrip(".*"),
            status=FactRequirementStatus.PRESENT,
            priority=req.priority,
        )

    # No valid satisfier — stricter blockers before confirmation.
    if any(i.conflicted for i in non_none):
        status = FactRequirementStatus.CONFLICTED
    elif any(i.consent == "denied" for i in non_none):
        status = FactRequirementStatus.DENIED
    elif any(getattr(i, "freshness", None) == "stale" for i in non_none):
        # Only when no valid present evidence; unknown freshness is not stale.
        status = FactRequirementStatus.STALE
    elif req.requires_confirmation and any(
        _is_present_candidate(i, require_confirmation=True) for i in non_none
    ):
        status = FactRequirementStatus.NEEDS_CONFIRMATION
    else:
        status = FactRequirementStatus.MISSING
    return FactRequirementOutcome(
        requirement_id=req.requirement_id,
        canonical_key=req.canonical_key.rstrip(".*"),
        status=status,
        priority=req.priority,
    )


_STATUS_RANK = {
    FactRequirementStatus.CONFLICTED: 10,
    FactRequirementStatus.DENIED: 20,
    FactRequirementStatus.STALE: 30,
    FactRequirementStatus.NEEDS_CONFIRMATION: 40,
    FactRequirementStatus.MISSING: 50,
    FactRequirementStatus.UNAVAILABLE: 60,
}

_READINESS_FOR_FACT = {
    FactRequirementStatus.CONFLICTED: ReadinessStatus.BLOCKED_CONFLICT,
    FactRequirementStatus.DENIED: ReadinessStatus.BLOCKED_DENIED,
    FactRequirementStatus.STALE: ReadinessStatus.BLOCKED_STALE,
    FactRequirementStatus.NEEDS_CONFIRMATION: ReadinessStatus.NEEDS_CONFIRMATION,
    FactRequirementStatus.MISSING: ReadinessStatus.NEEDS_CLARIFICATION,
    FactRequirementStatus.UNAVAILABLE: ReadinessStatus.UNAVAILABLE,
}


# Fixed localized templates — never interpolate fact values.
_TEMPLATES: dict[str, dict[str, str]] = {
    "tpl.goal.v1": {
        "en": "What is your main nutrition goal right now?",
        "fa": "هدف اصلیت از تغذیه الان چیست؟",
        "ar": "ما هدفك الأساسي من التغذية الآن؟",
    },
    "tpl.birth_year.v1": {
        "en": "What year were you born?",
        "fa": "در چه سالی به دنیا آمده‌اید؟",
        "ar": "في أي سنة وُلدت؟",
    },
    "tpl.sex.v1": {
        "en": "Which sex should we use for personalized health calculations?",
        "fa": "برای محاسبه‌های شخصی‌سازی‌شده، جنسیت را چطور ثبت کنیم؟",
        "ar": "ما الجنس الذي ينبغي استخدامه للحسابات الشخصية؟",
    },
    "tpl.height.v1": {
        "en": "What is your current height in centimeters?",
        "fa": "قد فعلی‌تان چند سانتی‌متر است؟",
        "ar": "ما طولك الحالي بالسنتيمتر؟",
    },
    "tpl.weight.v1": {
        "en": "What is your current weight in kilograms?",
        "fa": "وزن فعلی‌تان چند کیلوگرم است؟",
        "ar": "ما وزنك الحالي بالكيلوغرام؟",
    },
    "tpl.activity.v1": {
        "en": "How active are you on a typical day?",
        "fa": "در یک روز معمول چقدر فعال هستید؟",
        "ar": "ما مستوى نشاطك في يوم عادي؟",
    },
    "tpl.allergies.v1": {
        "en": "Do you have any food allergies or intolerances?",
        "fa": "آیا آلرژی یا عدم تحمل غذایی دارید؟",
        "ar": "هل لديك أي حساسية أو عدم تحمل غذائي؟",
    },
    "tpl.conditions.v1": {
        "en": "Do you currently have any medical conditions we should consider?",
        "fa": "آیا بیماری پزشکی فعالی دارید که باید در نظر بگیریم؟",
        "ar": "هل لديك حالات طبية حالية ينبغي مراعاتها؟",
    },
    "tpl.medications.v1": {
        "en": "Are you currently taking any medications?",
        "fa": "آیا در حال حاضر دارویی مصرف می‌کنید؟",
        "ar": "هل تتناول أي أدوية حالياً؟",
    },
    "tpl.restrictions.v1": {
        "en": "Do you follow any dietary or cultural food restrictions?",
        "fa": "آیا محدودیت غذایی یا فرهنگی دارید؟",
        "ar": "هل لديك قيود غذائية أو ثقافية؟",
    },
    "tpl.meal_prefs.v1": {
        "en": "What meal preferences should we respect?",
        "fa": "ترجیحات وعده‌های غذایی‌تان چیست؟",
        "ar": "ما تفضيلات وجباتك؟",
    },
    "tpl.meal_schedule.v1": {
        "en": "What is your usual meal schedule?",
        "fa": "برنامه معمول وعده‌های غذایی‌تان چیست؟",
        "ar": "ما جدول وجباتك المعتاد؟",
    },
    "tpl.budget.v1": {
        "en": "What food budget range should we keep in mind?",
        "fa": "محدوده بودجه غذایی‌تان تقریباً چقدر است؟",
        "ar": "ما نطاق ميزانية الطعام المناسب لك؟",
    },
    "tpl.food_prep.v1": {
        "en": "How much time and equipment do you have for food preparation?",
        "fa": "برای آماده‌سازی غذا چقدر زمان و امکانات دارید؟",
        "ar": "كم لديك من الوقت والإمكانات لتحضير الطعام؟",
    },
    "tpl.conflict.v1": {
        "en": "I found conflicting information. Please enter the current value again.",
        "fa": "اطلاعات ناسازگار پیدا شد. لطفاً مقدار فعلی را دوباره وارد کنید.",
        "ar": "وجدت معلومات متعارضة. يرجى إدخال القيمة الحالية مرة أخرى.",
    },
    "tpl.confirm.v1": {
        "en": "Please confirm whether this information is still current.",
        "fa": "لطفاً تأیید کنید که این اطلاعات هنوز معتبر است.",
        "ar": "يرجى تأكيد ما إذا كانت هذه المعلومات لا تزال صحيحة.",
    },
    "tpl.denied.v1": {
        "en": "I need permission to use this information before continuing.",
        "fa": "برای ادامه، به اجازه استفاده از این اطلاعات نیاز دارم.",
        "ar": "أحتاج إذناً لاستخدام هذه المعلومات قبل المتابعة.",
    },
    "tpl.unavailable.v1": {
        "en": "This information is not yet available from an authorized source.",
        "fa": "این اطلاعات هنوز از منبع مجاز در دسترس نیست.",
        "ar": "هذه المعلومات غير متاحة بعد من مصدر مُصرَّح به.",
    },
}

_REQ_TO_TEMPLATE = {
    "nut.goal": "tpl.goal.v1",
    "nut.birth_year": "tpl.birth_year.v1",
    "nut.sex": "tpl.sex.v1",
    "nut.height": "tpl.height.v1",
    "nut.weight": "tpl.weight.v1",
    "nut.activity": "tpl.activity.v1",
    "nut.allergies": "tpl.allergies.v1",
    "nut.conditions": "tpl.conditions.v1",
    "nut.medications": "tpl.medications.v1",
    "nut.restrictions": "tpl.restrictions.v1",
    "nut.meal_prefs": "tpl.meal_prefs.v1",
    "nut.meal_schedule": "tpl.meal_schedule.v1",
    "nut.budget": "tpl.budget.v1",
    "nut.food_prep": "tpl.food_prep.v1",
}


def _localized(template_id: str, language: LanguageCode) -> str:
    block = _TEMPLATES[template_id]
    return block.get(language) or block["en"]


def _build_clarification(
    outcome: FactRequirementOutcome,
    *,
    language: LanguageCode,
) -> ClarificationResult:
    if outcome.status is FactRequirementStatus.CONFLICTED:
        template_id = "tpl.conflict.v1"
    elif outcome.status is FactRequirementStatus.DENIED:
        template_id = "tpl.denied.v1"
    elif outcome.status is FactRequirementStatus.UNAVAILABLE:
        template_id = "tpl.unavailable.v1"
    elif outcome.status is FactRequirementStatus.NEEDS_CONFIRMATION:
        template_id = "tpl.confirm.v1"
    else:
        template_id = _REQ_TO_TEMPLATE.get(outcome.requirement_id, "tpl.unavailable.v1")
    question_id = f"i3.q.{outcome.requirement_id}.v1"
    return ClarificationResult(
        question_id=question_id,
        target_key=outcome.canonical_key,
        template_id=template_id,
        localized_message=_localized(template_id, language),
    )


def evaluate_readiness(
    *,
    snapshot: ContextSnapshot,
    intent: IntentResult,
    authenticated_user_id: int,
    language: LanguageCode,
) -> ReadinessResult:
    """Evaluate readiness against the authorized snapshot only."""
    if snapshot is None:
        raise MissingInformationError("missing_snapshot")
    if not isinstance(authenticated_user_id, int) or authenticated_user_id <= 0:
        raise MissingInformationError("invalid_owner")
    if snapshot.owner_user_id != authenticated_user_id:
        raise MissingInformationError("cross_user_snapshot")

    reqs = requirements_for(intent)
    if not reqs:
        return ReadinessResult(
            status=ReadinessStatus.READY,
            intent_id=intent.intent_id,
            request_kind=intent.request_kind,
            outcomes=(),
            missing_fact_keys=(),
            clarification=None,
        )

    outcomes = tuple(_evaluate_one(snapshot.items, req) for req in reqs)
    blockers = [
        o
        for o in outcomes
        if o.status is not FactRequirementStatus.PRESENT
    ]
    if not blockers:
        return ReadinessResult(
            status=ReadinessStatus.READY,
            intent_id=intent.intent_id,
            request_kind=intent.request_kind,
            outcomes=outcomes,
            missing_fact_keys=(),
            clarification=None,
        )

    # Prefer actionable clarifications over pure unavailable when choosing one.
    blockers_sorted = sorted(
        blockers,
        key=lambda o: (
            _STATUS_RANK.get(o.status, 99),
            o.priority,
            o.requirement_id,
        ),
    )
    chosen = blockers_sorted[0]
    readiness = _READINESS_FOR_FACT[chosen.status]
    clarification = _build_clarification(chosen, language=language)
    missing_keys = tuple(
        o.canonical_key
        for o in sorted(blockers, key=lambda x: (x.priority, x.requirement_id))
        if o.status
        in (
            FactRequirementStatus.MISSING,
            FactRequirementStatus.NEEDS_CONFIRMATION,
            FactRequirementStatus.CONFLICTED,
            FactRequirementStatus.DENIED,
            FactRequirementStatus.STALE,
            FactRequirementStatus.UNAVAILABLE,
        )
    )
    return ReadinessResult(
        status=readiness,
        intent_id=intent.intent_id,
        request_kind=intent.request_kind,
        outcomes=outcomes,
        missing_fact_keys=missing_keys,
        clarification=clarification,
    )

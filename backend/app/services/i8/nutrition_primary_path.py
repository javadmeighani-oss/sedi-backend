"""Canonical V1 primary-user nutrition operational path.

Chat / product callers use this facade → I8 unified_core (persist).
Does NOT invent medical authority. Does NOT create a parallel nutrition store.
Legacy ``plan_nutrition`` remains ephemeral-only for backward unit contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app.services.i8.contracts import I8OperationalActionResult
from backend.app.services.i8.unified_core import generate_operational_action

CANONICAL_AUTHORITY = "I8_OPERATIONAL_NUTRITION"
KNOWLEDGE_AUTHORITY = "I5_GOVERNED_KNOWLEDGE"
USER_DATA_AUTHORITY = "GATE2_I6_PRODUCT_DATA"
PERSONALIZATION_AUTHORITY = "I7_BOUNDED_PERSONALIZATION"
DELIVERY_AUTHORITY = "I10_COACHING_DELIVERY"
CLINICAL_AUTHORITY = "I4_CLINICAL_SAFETY"

FAIL_SAFE_STATUSES = frozenset(
    {
        "MISSING_ELIGIBLE_KNOWLEDGE",
        "STALE_OR_INELIGIBLE_KNOWLEDGE",
        "UNSUPPORTED_CLINICAL_APPLICABILITY",
        "CONSENT_REQUIRED",
        "TIMEZONE_REQUIRED",
        "TIMEZONE_INVALID",
        "AUTH_IDENTITY_MISMATCH",
        "SUBJECT_ACCESS_DENIED",
        "UNSAFE_REQUEST_BLOCKED",
        "THERAPEUTIC_FAIL_CLOSED",
        "ALLERGY_CONSTRAINT_BLOCKED",
        "UNVERIFIED_ALLERGY_SIGNAL",
    }
)

_USER_MESSAGES = {
    "en": {
        "ACTION_PERSISTED": "Here is a grounded nutrition suggestion based on your stored preferences and governed health knowledge.",
        "ACTION_READY": "Here is a grounded nutrition suggestion based on your stored preferences and governed health knowledge.",
        "MISSING_ELIGIBLE_KNOWLEDGE": "I do not have enough governed nutrition knowledge to make a reliable suggestion right now.",
        "STALE_OR_INELIGIBLE_KNOWLEDGE": "I do not have enough governed nutrition knowledge to make a reliable suggestion right now.",
        "UNSUPPORTED_CLINICAL_APPLICABILITY": "I cannot provide clinical or therapeutic diet advice. Please consult a qualified clinician.",
        "UNSAFE_REQUEST_BLOCKED": "Sedi will not diagnose, replace a physician, or modify medication.",
        "THERAPEUTIC_FAIL_CLOSED": "Sedi will not diagnose, replace a physician, or modify medication.",
        "CONSENT_REQUIRED": "Memory consent is required before personalized nutrition help.",
        "TIMEZONE_REQUIRED": "A valid timezone on your profile is required before scheduling nutrition actions.",
        "default": "I cannot create a verified nutrition action from the available context.",
    },
    "fa": {
        "ACTION_PERSISTED": "بر اساس ترجیحات ذخیره‌شده و دانش تغذیه‌ای تحت حاکمیت، یک پیشنهاد عملی آماده است.",
        "ACTION_READY": "بر اساس ترجیحات ذخیره‌شده و دانش تغذیه‌ای تحت حاکمیت، یک پیشنهاد عملی آماده است.",
        "MISSING_ELIGIBLE_KNOWLEDGE": "در حال حاضر دانش تغذیه‌ای تحت حاکمیت کافی برای پیشنهاد قابل اتکا ندارم.",
        "STALE_OR_INELIGIBLE_KNOWLEDGE": "در حال حاضر دانش تغذیه‌ای تحت حاکمیت کافی برای پیشنهاد قابل اتکا ندارم.",
        "UNSUPPORTED_CLINICAL_APPLICABILITY": "نمی‌توانم رژیم درمانی یا توصیه بالینی بدهم. لطفاً با متخصص مشورت کنید.",
        "UNSAFE_REQUEST_BLOCKED": "سِدی تشخیص نمی‌دهد، جایگزین پزشک نمی‌شود و دارو را تغییر نمی‌دهد.",
        "THERAPEUTIC_FAIL_CLOSED": "سِدی تشخیص نمی‌دهد، جایگزین پزشک نمی‌شود و دارو را تغییر نمی‌دهد.",
        "CONSENT_REQUIRED": "برای کمک تغذیه‌ای شخصی، اجازه حافظه لازم است.",
        "TIMEZONE_REQUIRED": "برای زمان‌بندی اقدام تغذیه‌ای، منطقه زمانی معتبر در پروفایل لازم است.",
        "default": "با زمینه موجود نمی‌توانم یک اقدام تغذیه‌ای تأییدشده بسازم.",
    },
}


@dataclass(frozen=True)
class NutritionPrimaryResult:
    status: str
    domain: str
    action_id: Optional[int]
    plan_id: Optional[int]
    grounded: bool
    fail_safe: bool
    user_message: str
    summary: str
    knowledge_refs: list[dict[str, Any]] = field(default_factory=list)
    authority: str = CANONICAL_AUTHORITY
    clinical: bool = False
    persistence: str = "NONE"
    core: Optional[I8OperationalActionResult] = None


def _message_for(status: str, language: str) -> str:
    lang = language if language in _USER_MESSAGES else "en"
    table = _USER_MESSAGES[lang]
    return table.get(status, table["default"])


def execute_primary_nutrition_action(
    db: Session,
    *,
    user_id: int,
    actor_user_id: int,
    request: str,
    language: str = "en",
    persist: bool = True,
    generation_mode: str = "reactive",
    plan_idempotency_key: Optional[str] = None,
    action_idempotency_key: Optional[str] = None,
    health_subject_id: Optional[int] = None,
) -> NutritionPrimaryResult:
    """Canonical V1 nutrition action — I8 owns semantics; I5 grounds knowledge."""
    core = generate_operational_action(
        db,
        user_id=user_id,
        actor_user_id=actor_user_id,
        request=request,
        domain="nutrition",
        persist=persist,
        generation_mode=generation_mode,
        plan_idempotency_key=plan_idempotency_key,
        action_idempotency_key=action_idempotency_key,
        health_subject_id=health_subject_id,
    )
    status = core.status
    # Map unified statuses that plan_nutrition historically remapped for ephemeral UX.
    if status == "MISSING_ELIGIBLE_KNOWLEDGE":
        mapped = "MISSING_ELIGIBLE_KNOWLEDGE"
    elif status == "UNSUPPORTED_CLINICAL_APPLICABILITY":
        mapped = "UNSUPPORTED_CLINICAL_APPLICABILITY"
    else:
        mapped = status

    grounded = mapped in {"ACTION_PERSISTED", "ACTION_READY", "GROUNDED_EPHEMERAL"}
    fail_safe = (not grounded) or mapped in FAIL_SAFE_STATUSES
    persistence = "I8_OPERATIONAL" if (persist and core.action_id is not None) else "NONE"
    summary = core.summary or core.rationale or mapped
    user_message = _message_for(mapped, language)
    if grounded and summary and summary not in user_message:
        user_message = f"{user_message}\n{summary}".strip()

    return NutritionPrimaryResult(
        status=mapped,
        domain=core.domain or "nutrition",
        action_id=core.action_id,
        plan_id=core.plan_id,
        grounded=grounded,
        fail_safe=fail_safe and not grounded,
        user_message=user_message,
        summary=summary,
        knowledge_refs=list(core.knowledge_refs or []),
        persistence=persistence,
        clinical=False,
        core=core,
    )


def is_nutrition_operational_intent(intent_id: Any, request_kind: Any = None) -> bool:
    """True when Chat/I3 resolved a nutrition intent that must not LLM-invent plans."""
    try:
        value = getattr(intent_id, "value", intent_id)
        return str(value).casefold() == "nutrition"
    except Exception:
        return False

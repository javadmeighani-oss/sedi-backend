"""Canonical V1 primary-user exercise/activity operational path.

Chat / product callers use this facade → I8 unified_core (persist).
I3 intent is ACTIVITY; I8 domain is exercise; I10 family is EXERCISE_PLAN_FOLLOW_UP.
Does NOT invent clinical exercise prescriptions. Does NOT create a parallel exercise store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app.services.i8.contracts import I8OperationalActionResult
from backend.app.services.i8.unified_core import generate_operational_action

CANONICAL_AUTHORITY = "I8_OPERATIONAL_EXERCISE"
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
        "RESTRICTION_BLOCKED",
    }
)

_USER_MESSAGES = {
    "en": {
        "ACTION_PERSISTED": "Here is a grounded activity suggestion based on your stored preferences and governed health knowledge.",
        "ACTION_READY": "Here is a grounded activity suggestion based on your stored preferences and governed health knowledge.",
        "MISSING_ELIGIBLE_KNOWLEDGE": "I do not have enough governed activity knowledge to make a reliable suggestion right now.",
        "STALE_OR_INELIGIBLE_KNOWLEDGE": "I do not have enough governed activity knowledge to make a reliable suggestion right now.",
        "UNSUPPORTED_CLINICAL_APPLICABILITY": "I cannot provide clinical exercise clearance or rehabilitation prescriptions. Please consult a qualified clinician.",
        "UNSAFE_REQUEST_BLOCKED": "Sedi will not diagnose, replace a physician, or modify medication.",
        "THERAPEUTIC_FAIL_CLOSED": "Sedi will not diagnose, replace a physician, or modify medication.",
        "CONSENT_REQUIRED": "Memory consent is required before personalized activity help.",
        "TIMEZONE_REQUIRED": "To set your workout times and reminders correctly, tell me your timezone, for example \"Tehran time\".",
        "default": "I cannot create a verified activity action from the available context.",
    },
    "fa": {
        "ACTION_PERSISTED": "بر اساس چیزهایی که از تو می‌دونم و دانش معتبر فعالیت بدنی، یه پیشنهاد عملی برات آماده کردم.",
        "ACTION_READY": "بر اساس چیزهایی که از تو می‌دونم و دانش معتبر فعالیت بدنی، یه پیشنهاد عملی برات آماده کردم.",
        "MISSING_ELIGIBLE_KNOWLEDGE": "الان دانش معتبر کافی برای یه پیشنهاد مطمئن ندارم و نمی‌خوام چیزی بگم که مطمئن نیستم. اگه خواستی این رو با تیم درمانت یا یه مربی متخصص هم در میون بذار.",
        "STALE_OR_INELIGIBLE_KNOWLEDGE": "الان دانش معتبر کافی برای یه پیشنهاد مطمئن ندارم و نمی‌خوام چیزی بگم که مطمئن نیستم. اگه خواستی این رو با تیم درمانت یا یه مربی متخصص هم در میون بذار.",
        "UNSUPPORTED_CLINICAL_APPLICABILITY": "مجوز ورزشی بالینی یا نسخه‌ی توانبخشی دادن کار من نیست، ولی کنارتم تا یه برنامه‌ی حرکتی ملایم و هماهنگ با تیم درمانت بچینیم. برای بخش درمانی حتماً با پزشک یا فیزیوتراپیست‌ات هم مشورت کن.",
        "UNSAFE_REQUEST_BLOCKED": "من تشخیص نمی‌دم، جای پزشک نمی‌شینم و دارو رو هم تغییر نمی‌دم؛ ولی اینجام که کنارت باشم و کمکت کنم سؤال‌هات رو برای پزشکت آماده کنی.",
        "THERAPEUTIC_FAIL_CLOSED": "من تشخیص نمی‌دم، جای پزشک نمی‌شینم و دارو رو هم تغییر نمی‌دم؛ ولی اینجام که کنارت باشم و کمکت کنم سؤال‌هات رو برای پزشکت آماده کنی.",
        "CONSENT_REQUIRED": "برای اینکه بتونم برات برنامه‌ی ورزشی شخصی بچینم، باید اجازه بدی اطلاعاتت رو به خاطر بسپارم.",
        "TIMEZONE_REQUIRED": "برای اینکه ساعت تمرین‌ها و یادآورها رو درست بذارم، بگو تو چه منطقه‌ی زمانی‌ای هستی؛ مثلاً بنویس «وقت تهران».",
        "default": "الان نتونستم یه برنامه‌ی ورزشی مطمئن بسازم؛ یه کم بیشتر درباره‌ات بگو تا دوباره امتحان کنم.",
    },
}


@dataclass(frozen=True)
class ExercisePrimaryResult:
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


def execute_primary_exercise_action(
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
    target_local_date=None,
    display_meta: Optional[dict] = None,
) -> ExercisePrimaryResult:
    """Canonical V1 exercise action — I8 owns semantics; I5 grounds knowledge."""
    if (
        persist
        and generation_mode == "reactive"
        and plan_idempotency_key is None
        and action_idempotency_key is None
        and target_local_date is None
    ):
        # Stage 06 / B1.5-b: chat-origin personalized 7-day plan from the I8 catalog (proactive/keyed callers
        # keep the grounded single-action path); falls back to it whenever the composer declines.
        from backend.app.services.i8.plan_composer import try_compose_for_chat
        from backend.app.services.i8.plan_notes import build_plan_trailer

        composed = try_compose_for_chat(
            db,
            user_id=user_id,
            actor_user_id=actor_user_id,
            request=request,
            domain="exercise",
            language=language,
            health_subject_id=health_subject_id,
        )
        if composed is not None:
            return ExercisePrimaryResult(
                status="ACTION_PERSISTED",
                domain="exercise",
                action_id=composed.action_id,
                plan_id=composed.plan_id,
                grounded=True,
                fail_safe=False,
                user_message=f"{composed.user_message}\n\n{build_plan_trailer(db, user_id, language, 'exercise')}",
                summary=composed.user_message,
                knowledge_refs=list(composed.knowledge_refs),
                persistence="I8_OPERATIONAL",
                clinical=False,
                core=None,
            )
    core = generate_operational_action(
        db,
        user_id=user_id,
        actor_user_id=actor_user_id,
        request=request,
        domain="exercise",
        persist=persist,
        generation_mode=generation_mode,
        plan_idempotency_key=plan_idempotency_key,
        action_idempotency_key=action_idempotency_key,
        health_subject_id=health_subject_id,
        target_local_date=target_local_date,
        display_meta=display_meta,
    )
    mapped = core.status
    grounded = mapped in {"ACTION_PERSISTED", "ACTION_READY", "GROUNDED_EPHEMERAL"}
    fail_safe = (not grounded) or mapped in FAIL_SAFE_STATUSES
    persistence = "I8_OPERATIONAL" if (persist and core.action_id is not None) else "NONE"
    summary = core.summary or core.rationale or mapped
    user_message = _message_for(mapped, language)
    if grounded and summary and summary not in user_message:
        user_message = f"{user_message}\n{summary}".strip()
    if grounded:
        from backend.app.services.i8.plan_notes import build_plan_trailer

        user_message = f"{user_message}\n\n{build_plan_trailer(db, user_id, language, 'exercise')}"

    return ExercisePrimaryResult(
        status=mapped,
        domain=core.domain or "exercise",
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


def is_activity_operational_intent(intent_id: Any, request_kind: Any = None) -> bool:
    """True when Chat/I3 resolved ACTIVITY — must not LLM-invent exercise plans."""
    try:
        value = getattr(intent_id, "value", intent_id)
        return str(value).casefold() == "activity"
    except Exception:
        return False

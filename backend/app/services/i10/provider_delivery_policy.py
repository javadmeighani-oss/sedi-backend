"""I10 sole provider-delivery freshness authority (B4-A4).

Notification existence != provider-delivery eligibility != FCM transport TTL
!= I7 retention lifetime. I10 SEND at enqueue is not eternal push permission.

I10 is the sole interruption/provider-delivery authority. This module does not
reinterpret I1–I9 factual, clinical, or event meaning. Explicit upstream
``expires_at`` is preserved exactly and is never extended by an I10 default.

A4 Smart Notifications UX product lock (document only; no frontend in B4-A4):
- visually attractive, warm/calm Sedi identity, interactive rather than a static list
- priority-aware without alarming users unnecessarily
- clear unread/read state; smooth card/detail interaction
- immediate feedback affordance; clear Continue-with-Sedi path into A3
- RTL-correct for FA/AR; native LTR for EN
- Android-appropriate touch targets; accessible contrast/text hierarchy
- no raw backend enum/channel text as final UX when a friendly localized label exists
- feedback chrome in FA/EN/AR: Was this useful? Like/Dislike, dislike reason sheet
  (Too frequent / Irrelevant / Unclear / Skip reason), Continue with Sedi, Mark as read
- backend title/body already rendered in the user's language; A4 chrome localizes
  from Sedi locale and MUST NOT retranslate backend clinical/notification content
- canonical feedback codes remain stable across languages
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Union

import pytz
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.gate4.notification_contract import DEFAULT_DAILY_NOTIFICATION_TIME
from backend.app.services.gate4.policy_prefs_bridge import (
    DEFAULT_TIMEZONE,
    get_local_now,
    resolve_validated_user_timezone,
)
from backend.app.services.gate4.scheduler_timing import (
    GATE4_DAILY_TOLERANCE_MINUTES,
    resolve_user_daily_notification_time_for_scheduler,
    resolve_user_timezone_for_scheduler,
)
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.policy_types import I10SemanticFamily

PRESENCE_REENGAGEMENT_TTL_HOURS = 4
ENGAGEMENT_NUDGE_TTL_HOURS = 3
CONTEXTUAL_TTL_HOURS = 24

_I10_OWNED_FIXED_HOURS: dict[str, int] = {
    I10SemanticFamily.PRESENCE_REENGAGEMENT.value: PRESENCE_REENGAGEMENT_TTL_HOURS,
    I10SemanticFamily.ENGAGEMENT_NUDGE.value: ENGAGEMENT_NUDGE_TTL_HOURS,
    I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP.value: CONTEXTUAL_TTL_HOURS,
    I10SemanticFamily.LIFESTYLE_ROUTINE_COACHING.value: CONTEXTUAL_TTL_HOURS,
    I10SemanticFamily.NUTRITION_PLAN_FOLLOW_UP.value: CONTEXTUAL_TTL_HOURS,
    I10SemanticFamily.EXERCISE_PLAN_FOLLOW_UP.value: CONTEXTUAL_TTL_HOURS,
}

_I10_OWNED_MORNING = I10SemanticFamily.MORNING_CHECK_IN.value
_I10_OWNED_DAILY = I10SemanticFamily.DAILY_WELLNESS_DIGEST.value

I8_EVENT_FAMILIES: frozenset[str] = frozenset(
    {
        I10SemanticFamily.MEDICATION_DUE.value,
        I10SemanticFamily.MEDICATION_FOLLOW_UP.value,
        I10SemanticFamily.DOCTOR_APPOINTMENT_REMINDER.value,
        I10SemanticFamily.LAB_APPOINTMENT_REMINDER.value,
        I10SemanticFamily.MEDICAL_EVENT_REMINDER.value,
    }
)

I9_DEVICE_FAMILIES: frozenset[str] = frozenset(
    {
        I10SemanticFamily.DEVICE_STATUS.value,
        I10SemanticFamily.HR_DAILY_STABILITY.value,
        I10SemanticFamily.HR_INSTABILITY.value,
    }
)

I4_SAFETY_FAMILIES: frozenset[str] = frozenset(
    {
        I10SemanticFamily.SAFETY_ESCALATION.value,
        I10SemanticFamily.CARE_SAFETY_ESCALATION.value,
    }
)

UPSTREAM_REQUIRED_FAMILIES: frozenset[str] = (
    I8_EVENT_FAMILIES | I9_DEVICE_FAMILIES | I4_SAFETY_FAMILIES
)


class ProviderFreshnessOutcome(str, Enum):
    ALLOW = "ALLOW"
    EXPIRE = "EXPIRE"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ProviderFreshnessDecision:
    outcome: ProviderFreshnessOutcome
    reason_code: str
    expires_at: Optional[datetime]
    remaining_seconds: Optional[int]
    effective_fcm_ttl: Optional[int]
    i10_decision_id: Optional[int] = None
    original_i10_decision: Optional[str] = None
    invented_validity: bool = False


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _family_value(family: Union[I10SemanticFamily, str, None]) -> str:
    if family is None:
        return ""
    if isinstance(family, I10SemanticFamily):
        return family.value
    return str(family).strip()


def i10_owns_default_lifetime(family: Union[I10SemanticFamily, str, None]) -> bool:
    key = _family_value(family)
    return key in _I10_OWNED_FIXED_HOURS or key in (_I10_OWNED_MORNING, _I10_OWNED_DAILY)


def _morning_window_bounds_utc(
    db: Session,
    *,
    user_id: int,
    now_utc: datetime,
) -> tuple[datetime, datetime]:
    """Reuse Gate4 scheduler daily timing + tolerance. No second morning window."""
    now_utc = _as_utc(now_utc) or datetime.now(timezone.utc)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        tz_name = DEFAULT_TIMEZONE
        daily_time = DEFAULT_DAILY_NOTIFICATION_TIME
    else:
        tz_name = resolve_user_timezone_for_scheduler(db, user)
        daily_time = resolve_user_daily_notification_time_for_scheduler(db, user)
    try:
        user_tz = pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        user_tz = pytz.timezone(DEFAULT_TIMEZONE)
        daily_time = daily_time or "08:00"
    local_now = get_local_now(now_utc, tz_name)
    hour, minute = map(int, daily_time.split(":"))
    local_target = user_tz.localize(
        datetime(local_now.year, local_now.month, local_now.day, hour, minute, 0)
    )
    window_start = local_target - timedelta(minutes=GATE4_DAILY_TOLERANCE_MINUTES)
    # is_daily_notification_time uses abs(delta) < tolerance (exclusive of +tolerance).
    window_end = local_target + timedelta(minutes=GATE4_DAILY_TOLERANCE_MINUTES)
    return window_start.astimezone(timezone.utc), window_end.astimezone(timezone.utc)


def _daily_local_day_end_utc(
    db: Session,
    *,
    user_id: int,
    now_utc: datetime,
) -> datetime:
    """End of the same user-local calendar day via the canonical timezone resolver."""
    now_utc = _as_utc(now_utc) or datetime.now(timezone.utc)
    tz_name = resolve_validated_user_timezone(db, user_id)
    try:
        user_tz = pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        user_tz = pytz.timezone(DEFAULT_TIMEZONE)
    local_now = get_local_now(now_utc, tz_name)
    next_day = local_now.date() + timedelta(days=1)
    next_midnight = user_tz.localize(datetime(next_day.year, next_day.month, next_day.day, 0, 0, 0))
    return next_midnight.astimezone(timezone.utc)


def compute_i10_owned_expires_at(
    db: Session,
    *,
    family: Union[I10SemanticFamily, str, None],
    user_id: int,
    lifetime_start: datetime,
    now_utc: Optional[datetime] = None,
) -> Optional[datetime]:
    """Compute I10-owned default expiry. Never used for I8/I9/I4 families."""
    key = _family_value(family)
    start = _as_utc(lifetime_start)
    now = _as_utc(now_utc) or start or datetime.now(timezone.utc)
    if start is None:
        start = now
    if key in _I10_OWNED_FIXED_HOURS:
        return start + timedelta(hours=_I10_OWNED_FIXED_HOURS[key])
    if key == _I10_OWNED_MORNING:
        _window_start, window_end = _morning_window_bounds_utc(
            db, user_id=user_id, now_utc=start
        )
        return window_end
    if key == _I10_OWNED_DAILY:
        return _daily_local_day_end_utc(db, user_id=user_id, now_utc=start)
    return None


def apply_i10_provider_lifetime(
    db: Session,
    candidate: I10NotificationCandidate,
    *,
    now_utc: Optional[datetime] = None,
) -> I10NotificationCandidate:
    """Stamp I10-owned default lifetime before canonical policy / ledger / persist.

    Explicit candidate.expires_at is preserved exactly and never extended.
    Upstream-required families are not invented here.
    """
    if candidate.expires_at is not None:
        return candidate
    if not i10_owns_default_lifetime(candidate.semantic_family):
        return candidate
    now = _as_utc(now_utc) or datetime.now(timezone.utc)
    lifetime_start = _as_utc(candidate.valid_from) or now
    expires_at = compute_i10_owned_expires_at(
        db,
        family=candidate.semantic_family,
        user_id=candidate.recipient_user_id,
        lifetime_start=lifetime_start,
        now_utc=now,
    )
    if expires_at is None:
        return candidate
    valid_from = candidate.valid_from
    if valid_from is None:
        if _family_value(candidate.semantic_family) == _I10_OWNED_MORNING:
            window_start, _window_end = _morning_window_bounds_utc(
                db, user_id=candidate.recipient_user_id, now_utc=lifetime_start
            )
            valid_from = window_start
        else:
            valid_from = lifetime_start
    return replace(candidate, valid_from=valid_from, expires_at=expires_at)


def compute_effective_fcm_ttl(
    *,
    remaining_provider_lifetime_seconds: Optional[int],
    transport_ttl_seconds: Optional[int],
) -> Optional[int]:
    if remaining_provider_lifetime_seconds is None:
        return transport_ttl_seconds
    if remaining_provider_lifetime_seconds <= 0:
        return 0
    remaining = int(remaining_provider_lifetime_seconds)
    if transport_ttl_seconds is None:
        return remaining
    try:
        existing = int(transport_ttl_seconds)
    except (TypeError, ValueError):
        return remaining
    if existing <= 0:
        return remaining
    return min(existing, remaining)


def _missing_source_reason(family: str) -> str:
    if family in I8_EVENT_FAMILIES:
        return "MISSING_I8_SOURCE_EXPIRY"
    if family in I9_DEVICE_FAMILIES:
        return "MISSING_I9_SOURCE_VALIDITY"
    if family in I4_SAFETY_FAMILIES:
        return "MISSING_I4_SAFETY_EXPIRY"
    return "MISSING_PROVIDER_EXPIRY_AUTHORITY"


def evaluate_provider_freshness(
    db: Session,
    *,
    family: Union[I10SemanticFamily, str, None],
    user_id: int,
    expires_at: Optional[datetime],
    lifetime_start: Optional[datetime] = None,
    now_utc: Optional[datetime] = None,
    transport_ttl_seconds: Optional[int] = None,
    i10_decision_id: Optional[int] = None,
    original_i10_decision: Optional[str] = None,
    allow_compute_i10_owned_from_start: bool = True,
) -> ProviderFreshnessDecision:
    """Revalidate provider freshness. Critical priority cannot bypass this."""
    now = _as_utc(now_utc) or datetime.now(timezone.utc)
    family_key = _family_value(family)
    explicit = _as_utc(expires_at)
    computed: Optional[datetime] = None
    invented = False

    if explicit is None and allow_compute_i10_owned_from_start and i10_owns_default_lifetime(family_key):
        start = _as_utc(lifetime_start) or now
        computed = compute_i10_owned_expires_at(
            db,
            family=family_key,
            user_id=user_id,
            lifetime_start=start,
            now_utc=now,
        )
        # Compute-only at provider time; do not persist invented decision expiry.
        invented = False

    provider_expires = explicit or computed
    if provider_expires is None:
        return ProviderFreshnessDecision(
            outcome=ProviderFreshnessOutcome.BLOCK,
            reason_code=_missing_source_reason(family_key),
            expires_at=None,
            remaining_seconds=None,
            effective_fcm_ttl=None,
            i10_decision_id=i10_decision_id,
            original_i10_decision=original_i10_decision,
            invented_validity=False,
        )

    remaining = int((provider_expires - now).total_seconds())
    if remaining <= 0:
        return ProviderFreshnessDecision(
            outcome=ProviderFreshnessOutcome.EXPIRE,
            reason_code="PROVIDER_LIFETIME_ELAPSED",
            expires_at=provider_expires,
            remaining_seconds=remaining,
            effective_fcm_ttl=0,
            i10_decision_id=i10_decision_id,
            original_i10_decision=original_i10_decision,
            invented_validity=invented,
        )

    return ProviderFreshnessDecision(
        outcome=ProviderFreshnessOutcome.ALLOW,
        reason_code="PROVIDER_FRESH",
        expires_at=provider_expires,
        remaining_seconds=remaining,
        effective_fcm_ttl=compute_effective_fcm_ttl(
            remaining_provider_lifetime_seconds=remaining,
            transport_ttl_seconds=transport_ttl_seconds,
        ),
        i10_decision_id=i10_decision_id,
        original_i10_decision=original_i10_decision,
        invented_validity=invented,
    )


def resolve_linked_i10_decision(
    db: Session,
    notification: models.Notification,
) -> Optional[models.I10NotificationDecision]:
    decision_id = getattr(notification, "i10_policy_decision_id", None)
    if decision_id is not None:
        row = (
            db.query(models.I10NotificationDecision)
            .filter(models.I10NotificationDecision.id == int(decision_id))
            .first()
        )
        if row is not None:
            return row
    notification_id = getattr(notification, "id", None)
    if notification_id is None:
        return None
    return (
        db.query(models.I10NotificationDecision)
        .filter(models.I10NotificationDecision.notification_id == int(notification_id))
        .order_by(models.I10NotificationDecision.id.desc())
        .first()
    )


def notification_is_i10_linked(
    notification: models.Notification,
    decision: Optional[models.I10NotificationDecision],
) -> bool:
    if decision is not None:
        return True
    if getattr(notification, "i10_policy_decision_id", None) is not None:
        return True
    return False


def evaluate_notification_provider_freshness(
    db: Session,
    notification: models.Notification,
    *,
    now_utc: Optional[datetime] = None,
) -> ProviderFreshnessDecision:
    decision = resolve_linked_i10_decision(db, notification)
    if not notification_is_i10_linked(notification, decision):
        ttl = getattr(notification, "ttl_seconds", None)
        return ProviderFreshnessDecision(
            outcome=ProviderFreshnessOutcome.ALLOW,
            reason_code="LEGACY_UNLINKED_NO_I10_LIFETIME",
            expires_at=None,
            remaining_seconds=None,
            effective_fcm_ttl=ttl if ttl is not None else None,
            i10_decision_id=None,
            original_i10_decision=None,
            invented_validity=False,
        )
    if decision is None:
        return ProviderFreshnessDecision(
            outcome=ProviderFreshnessOutcome.BLOCK,
            reason_code="MISSING_I10_DECISION",
            expires_at=None,
            remaining_seconds=None,
            effective_fcm_ttl=None,
            i10_decision_id=getattr(notification, "i10_policy_decision_id", None),
            original_i10_decision=None,
            invented_validity=False,
        )
    family = decision.semantic_family or getattr(notification, "semantic_family", None)
    lifetime_start = _as_utc(decision.valid_from) or _as_utc(decision.created_at)
    return evaluate_provider_freshness(
        db,
        family=family,
        user_id=int(decision.recipient_user_id or notification.user_id),
        expires_at=decision.expires_at,
        lifetime_start=lifetime_start,
        now_utc=now_utc,
        transport_ttl_seconds=getattr(notification, "ttl_seconds", None),
        i10_decision_id=int(decision.id),
        original_i10_decision=decision.decision,
        allow_compute_i10_owned_from_start=True,
    )


def persist_provider_expired(
    notification: models.Notification,
    *,
    reason_code: str = "PROVIDER_LIFETIME_ELAPSED",
) -> None:
    """Terminal provider-expired state. Does not rewrite the I10 decision."""
    notification.status = "expired"
    notification.is_sent = False
    notification.sent_at = None
    notification.last_error = f"provider_lifetime_elapsed:{reason_code}"[:500]


def attach_transient_fcm_ttl(
    notification: models.Notification,
    effective_ttl: Optional[int],
) -> None:
    """Transient effective TTL for this send only. Does not persist ttl_seconds."""
    setattr(notification, "_effective_fcm_ttl", effective_ttl)


def read_transient_fcm_ttl(notification: models.Notification) -> Optional[int]:
    return getattr(notification, "_effective_fcm_ttl", None)

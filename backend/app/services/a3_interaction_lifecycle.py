"""A3 Heart interaction lifecycle resolver — integrated with existing session/chat authority.

States: FIRST_CONTACT | SAME_DAY_RETURN | NEW_DAY_RETURN | NOTIFICATION_CONTINUATION
Timezone authority: UserProfileCore.timezone (I8 strict). No Asia/Tehran guess for day identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

import pytz
from sqlalchemy.orm import Session

from backend.app import models

INTERACTION_POLICY_VERSION = "a3_interaction_lifecycle_v1"

FIRST_CONTACT = "FIRST_CONTACT"
SAME_DAY_RETURN = "SAME_DAY_RETURN"
NEW_DAY_RETURN = "NEW_DAY_RETURN"
NOTIFICATION_CONTINUATION = "NOTIFICATION_CONTINUATION"


class InteractionLifecycleState(str, Enum):
    FIRST_CONTACT = FIRST_CONTACT
    SAME_DAY_RETURN = SAME_DAY_RETURN
    NEW_DAY_RETURN = NEW_DAY_RETURN
    NOTIFICATION_CONTINUATION = NOTIFICATION_CONTINUATION


@dataclass(frozen=True)
class InteractionLifecycleSnapshot:
    state: str
    interaction_policy_version: str
    timezone_name: Optional[str]
    timezone_authority_gap: bool
    today_local_date: Optional[str]
    last_meaningful_interaction_local_date: Optional[str]
    intro_completed: bool
    known_profile_keys: tuple[str, ...]
    instruction: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "interaction_policy_version": self.interaction_policy_version,
            "timezone_name": self.timezone_name,
            "timezone_authority_gap": self.timezone_authority_gap,
            "today_local_date": self.today_local_date,
            "last_meaningful_interaction_local_date": self.last_meaningful_interaction_local_date,
            "intro_completed": self.intro_completed,
            "known_profile_keys": list(self.known_profile_keys),
            "instruction": self.instruction,
        }


def _resolve_profile_timezone(db: Session, user_id: int) -> Optional[str]:
    """Authoritative user-local TZ only: UserProfileCore.timezone (no soft fallback)."""
    profile = (
        db.query(models.UserProfileCore)
        .filter(models.UserProfileCore.user_id == int(user_id))
        .first()
    )
    if profile is None or not profile.timezone or not str(profile.timezone).strip():
        return None
    tz_name = str(profile.timezone).strip()
    try:
        pytz.timezone(tz_name)
    except Exception:
        return None
    return tz_name


def _to_local_date(dt: datetime, tz_name: str) -> date:
    aware = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return aware.astimezone(pytz.timezone(tz_name)).date()


def _last_memory_at(db: Session, user_id: int) -> Optional[datetime]:
    row = (
        db.query(models.Memory.created_at)
        .filter(models.Memory.user_id == int(user_id))
        .order_by(models.Memory.created_at.desc())
        .first()
    )
    return row[0] if row else None


def _known_profile_keys(user: models.User, pack: Any = None) -> tuple[str, ...]:
    keys: list[str] = []
    name = (getattr(pack, "preferred_name", None) if pack is not None else None) or getattr(
        user, "name", None
    )
    if name and str(name).strip():
        keys.append("preferred_name")
    lang = (getattr(pack, "language", None) if pack is not None else None) or getattr(
        user, "preferred_language", None
    )
    if lang and str(lang).strip():
        keys.append("preferred_language")
    if pack is not None:
        if getattr(pack, "birth_year", None) is not None:
            keys.append("birth_year")
        if getattr(pack, "sex", None) and str(pack.sex).strip():
            keys.append("sex")
        if getattr(pack, "addressing_preference", None) and str(pack.addressing_preference).strip():
            keys.append("addressing_preference")
        if getattr(pack, "timezone", None) and str(pack.timezone).strip():
            keys.append("timezone")
    return tuple(keys)


def _instruction_for(
    state: str,
    *,
    known_keys: tuple[str, ...],
    preferred_name: Optional[str],
) -> str:
    name_bit = f" Preferred name is known ({preferred_name})." if preferred_name else ""
    known_bit = (
        f" Do not re-ask already known profile fields: {', '.join(known_keys)}."
        if known_keys
        else ""
    )
    if state == NOTIFICATION_CONTINUATION:
        return (
            "Lifecycle=NOTIFICATION_CONTINUATION. Continue from the provided safe "
            "notification topic/context. Do not replace it with a generic greeting "
            "or re-introduction."
            + known_bit
        )
    if state == FIRST_CONTACT:
        return (
            "Lifecycle=FIRST_CONTACT. Give a warm concise introduction as Sedi."
            + name_bit
            + known_bit
            + " Invite natural interaction. Do not mechanically repeat onboarding questions."
        )
    if state == NEW_DAY_RETURN:
        return (
            "Lifecycle=NEW_DAY_RETURN. User is interacting on a new local calendar day. "
            "Recognize continuity when useful; consider relevant pending actions if present. "
            "Do not re-introduce yourself. Do not force daily small talk."
            + known_bit
        )
    # SAME_DAY_RETURN or conservative fallback
    return (
        "Lifecycle=SAME_DAY_RETURN. Continue naturally from recent context. "
        "Do not re-introduce yourself or repeat first-contact onboarding."
        + known_bit
    )


def resolve_interaction_lifecycle(
    db: Session,
    user: models.User,
    *,
    source_notification_id: Optional[int] = None,
    notification_context: Optional[dict] = None,
    now_utc: Optional[datetime] = None,
    user_context_pack: Any = None,
) -> InteractionLifecycleSnapshot:
    """Classify current interaction lifecycle. Fail-closed on timezone gap for NEW_DAY."""
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    known = _known_profile_keys(user, user_context_pack)
    preferred_name = None
    if user_context_pack is not None and getattr(user_context_pack, "preferred_name", None):
        preferred_name = str(user_context_pack.preferred_name).strip() or None
    if not preferred_name and getattr(user, "name", None):
        preferred_name = str(user.name).strip() or None

    intro_completed = user.sedi_intro_completed_at is not None

    tz_name = _resolve_profile_timezone(db, int(user.id))
    tz_gap = tz_name is None
    today_local: Optional[str] = None
    last_local: Optional[str] = None
    last_at = _last_memory_at(db, int(user.id))

    if tz_name is not None:
        today_d = _to_local_date(now, tz_name)
        today_local = today_d.isoformat()
        if last_at is not None:
            last_local = _to_local_date(last_at, tz_name).isoformat()

    # Precedence: notification continuation > first contact > local-day return
    if source_notification_id is not None or notification_context:
        state = NOTIFICATION_CONTINUATION
    elif not intro_completed:
        state = FIRST_CONTACT
    elif tz_gap:
        # Conservative returning — do not invent NEW_DAY without TZ authority
        state = SAME_DAY_RETURN
    elif last_local is None:
        state = SAME_DAY_RETURN
    elif last_local != today_local:
        state = NEW_DAY_RETURN
    else:
        state = SAME_DAY_RETURN

    return InteractionLifecycleSnapshot(
        state=state,
        interaction_policy_version=INTERACTION_POLICY_VERSION,
        timezone_name=tz_name,
        timezone_authority_gap=tz_gap,
        today_local_date=today_local,
        last_meaningful_interaction_local_date=last_local,
        intro_completed=intro_completed,
        known_profile_keys=known,
        instruction=_instruction_for(state, known_keys=known, preferred_name=preferred_name),
    )


def format_lifecycle_context_block(snapshot: InteractionLifecycleSnapshot) -> str:
    """Compact system-only lifecycle block for ConversationBrain."""
    lines = [
        "[INTERACTION_LIFECYCLE]",
        f"state={snapshot.state}",
        f"interaction_policy_version={snapshot.interaction_policy_version}",
    ]
    if snapshot.timezone_name:
        lines.append(f"timezone={snapshot.timezone_name}")
    if snapshot.timezone_authority_gap:
        lines.append("timezone_authority_gap=YES")
    if snapshot.today_local_date:
        lines.append(f"today_local_date={snapshot.today_local_date}")
    if snapshot.last_meaningful_interaction_local_date:
        lines.append(
            "last_meaningful_interaction_local_date="
            + snapshot.last_meaningful_interaction_local_date
        )
    if snapshot.known_profile_keys:
        lines.append("known_profile_keys=" + ",".join(snapshot.known_profile_keys))
    lines.append(snapshot.instruction)
    return "\n".join(lines)

"""R-074 step 5a - the ONE typed read contract for "who is this user right now" (layer 5, MCP-style nervous system).

Before this module every consumer (notifications, profile overview, session open, chat adapters) read the
``UserContextPack`` itself and re-interpreted the fields (language normalisation, name trimming, age from a Jalali or
Gregorian birth year, length caps). ``UserState`` is the deterministic, read-only, frozen view they now share:

- built only from the pack that ``UserContextService`` (the single owner, consent-gated I6/I7 reads) already produced;
- no new store, no schema, no write path; fail-open (``get_user_state`` returns None on any problem);
- one place for the normalisations, so chat, notifications, profile and hub can never disagree.

New code that needs the user's state uses ``get_user_state`` / ``user_state_from_pack`` (a guard test lists the readers).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

MAX_GOALS = 5
MAX_LIFESTYLE_CHARS = 200
MAX_DAILY_SUMMARY_CHARS = 150
_LANGS = ("fa", "ar", "en")


@dataclass(frozen=True)
class UserState:
    user_id: int
    preferred_name: Optional[str] = None
    language: Optional[str] = None  # normalised: "fa" | "ar" | "en" | None (unknown)
    language_raw: Optional[str] = None  # as stored (stripped), for consumers that echo it
    timezone: Optional[str] = None
    sex: Optional[str] = None  # lower-cased as stored
    birth_year: Optional[int] = None
    age: Optional[int] = None  # None unless 3..110
    goals: tuple[str, ...] = ()
    lifestyle_text: str = ""
    daily_summary: str = ""
    engagement_level: Optional[str] = None


def age_from_birth_year(year: Any, *, now: Optional[datetime] = None) -> Optional[int]:
    """Birth year in Jalali (< 1700) or Gregorian -> age, only when plausible (3..110)."""
    try:
        y = int(year)
    except (TypeError, ValueError):
        return None
    if y < 1700:  # Jalali year
        y += 621
    age = (now or datetime.now(timezone.utc)).year - y
    return age if 3 <= age <= 110 else None


def normalize_language(value: Any) -> Optional[str]:
    raw = str(value or "").strip().lower()
    for lang in _LANGS:
        if raw.startswith(lang):
            return lang
    return None


def _clean(value: Any) -> Optional[str]:
    s = str(value or "").strip()
    return s or None


def user_state_from_pack(pack: Any, *, now: Optional[datetime] = None) -> Optional[UserState]:
    """The shared normalisation of a ``UserContextPack`` (None when there is no pack)."""
    if pack is None:
        return None
    goals_obj = getattr(pack, "goals", None)
    raw_goals = list(goals_obj.items) if goals_obj and isinstance(getattr(goals_obj, "items", None), list) else []
    goals = tuple(str(x).strip() for x in raw_goals if x)[:MAX_GOALS]
    lifestyle = getattr(pack, "lifestyle", None)
    lifestyle_text = ""
    if lifestyle and getattr(lifestyle, "text", None) and str(lifestyle.text).strip():
        lifestyle_text = str(lifestyle.text).strip()[:MAX_LIFESTYLE_CHARS]
    daily = getattr(pack, "daily_memory_summary", None)
    daily_summary = str(daily).strip()[:MAX_DAILY_SUMMARY_CHARS] if daily and str(daily).strip() else ""
    birth_year = getattr(pack, "birth_year", None)
    try:
        by = int(birth_year) if birth_year is not None else None
    except (TypeError, ValueError):
        by = None
    return UserState(
        user_id=int(getattr(pack, "user_id", 0) or 0),
        preferred_name=_clean(getattr(pack, "preferred_name", None)),
        language=normalize_language(getattr(pack, "language", None)),
        language_raw=_clean(getattr(pack, "language", None)),
        timezone=_clean(getattr(pack, "timezone", None)),
        sex=(str(getattr(pack, "sex", "") or "").strip().lower() or None),
        birth_year=by,
        age=age_from_birth_year(birth_year, now=now),
        goals=goals,
        lifestyle_text=lifestyle_text,
        daily_summary=daily_summary,
        engagement_level=_clean(getattr(pack, "engagement_level", None)),
    )


def get_user_state(db: Any, user_id: int) -> Optional[UserState]:
    """Load the user's pack through its single owner and return the shared view; fail-open (None)."""
    try:
        from backend.app.services.user_context import UserContextService

        return user_state_from_pack(UserContextService(db).get_user_context(user_id))
    except Exception:  # noqa: BLE001 - every consumer already degrades without state
        return None

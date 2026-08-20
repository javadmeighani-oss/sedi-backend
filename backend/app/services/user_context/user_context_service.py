# backend.app.services.user_context.user_context_service
"""
Read-only UserContextService: aggregates user identity, preferences, lifestyle, memory summary (Stage 23 Step 1).
No DB migrations; backward-compatible. Defensive imports and queries.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .context_models import (
    QuietHours,
    UserContextPack,
    UserGoals,
    UserLifestyleSummary,
)

logger = logging.getLogger(__name__)
_LOG_PREFIX = "[UserContext]"


def _safe_json(s: Optional[str]) -> Any:
    if not s or not s.strip():
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None


def _get_models():
    """Resolve models module (backend.app or app)."""
    try:
        from backend.app import models
        return models
    except ImportError:
        from app import models
        return models


def _get_memory_fact_value(db: Session, user_id: int, domain: str, key: str) -> Optional[Any]:
    """Canonical I6 read (PERM_READ + active + not invalidated + not expired)."""
    try:
        from backend.app.services.i6.memory_writes import get_readable_fact_or_none

        row = get_readable_fact_or_none(db, user_id, domain, key)
        if row and row.value_json:
            return _safe_json(row.value_json)
    except Exception as e:
        logger.debug("%s UserMemoryFact lookup %s/%s failed: %s", _LOG_PREFIX, domain, key, e)
    return None


def _hhmm(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    hour = getattr(value, "hour", None)
    minute = getattr(value, "minute", None)
    if hour is None or minute is None:
        return None
    return f"{int(hour):02d}:{int(minute):02d}"


def _get_quiet_hours_from_facts(db: Session, user_id: int) -> QuietHours:
    """NotificationPrefs / UserProfileCore are canonical; governed I6 is compatibility only."""
    try:
        models = _get_models()
        NotificationPrefs = getattr(models, "NotificationPrefs", None)
        if NotificationPrefs is not None:
            prefs = db.query(NotificationPrefs).filter(NotificationPrefs.user_id == user_id).first()
            if prefs is not None and getattr(prefs, "quiet_hours_enabled", False):
                start = _hhmm(getattr(prefs, "quiet_start", None))
                end = _hhmm(getattr(prefs, "quiet_end", None))
                if start is not None or end is not None:
                    return QuietHours(start=start, end=end)
        UserProfileCore = getattr(models, "UserProfileCore", None)
        if UserProfileCore is not None:
            core = db.query(UserProfileCore).filter(UserProfileCore.user_id == user_id).first()
            if core is not None:
                start = _hhmm(getattr(core, "quiet_start", None))
                end = _hhmm(getattr(core, "quiet_end", None))
                if start is not None or end is not None:
                    return QuietHours(start=start, end=end)
    except Exception as e:
        logger.debug("%s canonical quiet-hours lookup failed: %s", _LOG_PREFIX, e)
    qh = _get_memory_fact_value(db, user_id, "preferences", "quiet_hours")
    if isinstance(qh, dict):
        start = qh.get("start") if isinstance(qh.get("start"), str) else None
        end = qh.get("end") if isinstance(qh.get("end"), str) else None
        if start is not None or end is not None:
            return QuietHours(start=start, end=end)
    return QuietHours()


def _get_daily_memory_summary_text(db: Session, user_id: int) -> Optional[str]:
    """Latest canonical UserPeriodSummary DAILY narrative; legacy DMS is non-canonical."""
    try:
        from backend.app.services.i7.hierarchy import get_canonical_daily

        row = get_canonical_daily(db, user_id)
        if row and getattr(row, "narrative_summary", None) and str(row.narrative_summary).strip():
            return str(row.narrative_summary).strip()
    except Exception as e:
        logger.debug("%s UserPeriodSummary DAILY lookup failed: %s", _LOG_PREFIX, e)
    return None


def _get_lifestyle_summary(db: Session, user_id: int, language: Optional[str]) -> UserLifestyleSummary:
    """Call lifestyle summary service if available; return minimal UserLifestyleSummary."""
    text: Optional[str] = None
    extracted_facts: Dict[str, Any] = {}
    try:
        try:
            from backend.app.services.lifestyle.summary_service import generate_summary
        except ImportError:
            from app.services.lifestyle.summary_service import generate_summary
        lang = language or "en"
        data = generate_summary(db, user_id, language=lang)
        if isinstance(data, dict) and data.get("sections"):
            parts: List[str] = []
            for sec in data["sections"]:
                if isinstance(sec, dict):
                    body = sec.get("body") or ""
                    items = sec.get("items")
                    if body and isinstance(body, str):
                        parts.append(body.strip())
                    if items:
                        for it in items[:5]:
                            if isinstance(it, str):
                                parts.append(it[:120])
            if parts:
                text = "\n".join(parts)[:2000]
    except Exception as e:
        logger.debug("%s Lifestyle summary failed (non-critical): %s", _LOG_PREFIX, e)
    return UserLifestyleSummary(text=text or None, extracted_facts=extracted_facts)


def _get_verified_facts(db: Session, user_id: int) -> Dict[str, Any]:
    """Load Gate 1 profile facts for context (structured identity facts only)."""
    try:
        from backend.app.services.user_profile_fact_service import list_profile_facts

        items = list_profile_facts(db, user_id)
        out: Dict[str, Any] = {}
        for item in items[:10]:
            ft = item.get("fact_type")
            val = item.get("value")
            if ft and val is not None:
                out[str(ft)] = val
        return out
    except Exception as e:
        logger.debug("%s profile facts lookup failed: %s", _LOG_PREFIX, e)
    return {}


class UserContextService:
    """Read-only aggregation of user context: identity, preferences, lifestyle, memory."""

    def __init__(self, db: Session):
        self.db = db

    def get_user_context(self, user_id: int) -> UserContextPack:
        """Build UserContextPack from User, UserProfileKnowledge, UserFact, UserMemoryFact, DailyMemorySummary, lifestyle."""
        preferred_name: Optional[str] = None
        language: Optional[str] = None
        timezone: Optional[str] = None
        goals: Optional[UserGoals] = None
        engagement_level: Optional[str] = None
        source_meta: Dict[str, Any] = {}

        # A) preferred_name / language / timezone: UserProfileKnowledge or UserFact / UserMemoryFact
        try:
            models = _get_models()
            UserProfileKnowledge = getattr(models, "UserProfileKnowledge", None)
            if UserProfileKnowledge is None:
                pass
            else:
                profile = (
                    self.db.query(UserProfileKnowledge)
                    .filter(UserProfileKnowledge.user_id == user_id)
                    .first()
                )
                if profile:
                    if getattr(profile, "display_name", None) and str(profile.display_name).strip():
                        preferred_name = str(profile.display_name).strip()
                    if getattr(profile, "language", None) and str(profile.language).strip():
                        language = str(profile.language).strip()
                    if getattr(profile, "goals_json", None) and str(profile.goals_json).strip():
                        parsed = _safe_json(profile.goals_json)
                        if isinstance(parsed, list):
                            goals = UserGoals(items=[str(x) for x in parsed if x])
                        elif isinstance(parsed, str):
                            goals = UserGoals(items=[parsed])
                    source_meta["profile_knowledge"] = True
        except Exception as e:
            logger.debug("%s UserProfileKnowledge load failed: %s", _LOG_PREFIX, e)

        if language is None:
            try:
                models = _get_models()
                User = getattr(models, "User", None)
                if User is not None:
                    user = self.db.query(User).filter(User.id == user_id).first()
                    if user and getattr(user, "preferred_language", None):
                        language = str(user.preferred_language).strip()
            except Exception as e:
                logger.debug("%s User.preferred_language fallback failed: %s", _LOG_PREFIX, e)

        if preferred_name is None:
            try:
                models = _get_models()
                User = getattr(models, "User", None)
                if User is not None:
                    user = self.db.query(User).filter(User.id == user_id).first()
                    if user and getattr(user, "name", None) and str(user.name).strip():
                        preferred_name = str(user.name).strip()
                        source_meta["user_name"] = True
            except Exception as e:
                logger.debug("%s User.name fallback failed: %s", _LOG_PREFIX, e)

        birth_year: Optional[int] = None
        sex: Optional[str] = None
        addressing_preference: Optional[str] = None
        height_cm: Optional[int] = None
        weight_kg: Optional[float] = None
        try:
            models = _get_models()
            UserProfileCore = getattr(models, "UserProfileCore", None)
            if UserProfileCore is not None:
                core = (
                    self.db.query(UserProfileCore)
                    .filter(UserProfileCore.user_id == user_id)
                    .first()
                )
                if core:
                    birth_year = getattr(core, "birth_year", None)
                    if getattr(core, "sex", None) and str(core.sex).strip():
                        sex = str(core.sex).strip()
                    if getattr(core, "addressing_preference", None) and str(core.addressing_preference).strip():
                        addressing_preference = str(core.addressing_preference).strip()
                    if getattr(core, "timezone", None) and str(core.timezone).strip():
                        timezone = str(core.timezone).strip()
                    if language is None and getattr(core, "language", None) and str(core.language).strip():
                        language = str(core.language).strip()
                    # Same loaded UserProfileCore row — no extra query (Section 15-I3).
                    raw_height = getattr(core, "height_cm", None)
                    if raw_height is not None:
                        try:
                            height_cm = int(raw_height)
                        except (TypeError, ValueError):
                            height_cm = None
                    raw_weight = getattr(core, "weight_kg", None)
                    if raw_weight is not None:
                        try:
                            weight_kg = float(raw_weight)
                        except (TypeError, ValueError):
                            weight_kg = None
                    source_meta["profile_core"] = True
        except Exception as e:
            logger.debug("%s UserProfileCore load failed: %s", _LOG_PREFIX, e)

        if timezone is None:
            tz_val = _get_memory_fact_value(self.db, user_id, "preferences", "timezone")
            if isinstance(tz_val, dict) and tz_val.get("tz"):
                timezone = str(tz_val["tz"]).strip()
            elif isinstance(tz_val, str):
                timezone = tz_val.strip()

        if engagement_level is None:
            try:
                models = _get_models()
                NotificationPrefs = getattr(models, "NotificationPrefs", None)
                if NotificationPrefs is not None:
                    prefs = (
                        self.db.query(NotificationPrefs)
                        .filter(NotificationPrefs.user_id == user_id)
                        .first()
                    )
                    if prefs is not None:
                        level = getattr(prefs, "engagement_level", None)
                        engagement_level = {0: "low", 1: "normal", 2: "high"}.get(level)
            except Exception as e:
                logger.debug("%s NotificationPrefs engagement lookup failed: %s", _LOG_PREFIX, e)

        quiet_hours = _get_quiet_hours_from_facts(self.db, user_id)
        daily_memory_summary = _get_daily_memory_summary_text(self.db, user_id)
        lifestyle = _get_lifestyle_summary(self.db, user_id, language)
        verified_facts = _get_verified_facts(self.db, user_id)

        if not source_meta:
            source_meta["facts_source"] = "none"
        elif source_meta.get("profile_knowledge") and source_meta.get("memory_facts"):
            source_meta["facts_source"] = "user_profile_knowledge|user_memory_facts"
        elif source_meta.get("profile_knowledge"):
            source_meta["facts_source"] = "user_profile_knowledge"
        elif source_meta.get("memory_facts"):
            source_meta["facts_source"] = "user_memory_facts"
        else:
            source_meta["facts_source"] = "profile_knowledge|user_memory_facts"

        return UserContextPack(
            user_id=user_id,
            preferred_name=preferred_name,
            language=language,
            timezone=timezone,
            quiet_hours=quiet_hours,
            engagement_level=engagement_level,
            goals=goals,
            lifestyle=lifestyle,
            daily_memory_summary=daily_memory_summary,
            verified_facts=verified_facts,
            source_meta=source_meta,
            birth_year=birth_year,
            sex=sex,
            addressing_preference=addressing_preference,
            height_cm=height_cm,
            weight_kg=weight_kg,
        )

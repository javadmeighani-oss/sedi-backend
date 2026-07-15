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
    """Get value from UserMemoryFact if model exists; return None on missing/error."""
    try:
        models = _get_models()
        UserMemoryFact = getattr(models, "UserMemoryFact", None)
        if UserMemoryFact is None:
            return None
        row = (
            db.query(UserMemoryFact)
            .filter(
                UserMemoryFact.user_id == user_id,
                UserMemoryFact.domain == domain,
                UserMemoryFact.key == key,
            )
            .first()
        )
        if row and row.value_json:
            return _safe_json(row.value_json)
    except Exception as e:
        logger.debug("%s UserMemoryFact lookup %s/%s failed: %s", _LOG_PREFIX, domain, key, e)
    return None


def _get_quiet_hours_from_facts(db: Session, user_id: int) -> QuietHours:
    """Prefer UserMemoryFact preferences.quiet_hours (JSON {start, end}); else quiet_start/quiet_end keys."""
    qh = _get_memory_fact_value(db, user_id, "preferences", "quiet_hours")
    if isinstance(qh, dict):
        start = qh.get("start") if isinstance(qh.get("start"), str) else None
        end = qh.get("end") if isinstance(qh.get("end"), str) else None
        if start is not None or end is not None:
            return QuietHours(start=start, end=end)
    start = _get_memory_fact_value(db, user_id, "preferences", "quiet_start")
    end = _get_memory_fact_value(db, user_id, "preferences", "quiet_end")
    if isinstance(start, str) or isinstance(end, str):
        return QuietHours(
            start=start if isinstance(start, str) else None,
            end=end if isinstance(end, str) else None,
        )
    return QuietHours()


def _get_daily_memory_summary_text(db: Session, user_id: int) -> Optional[str]:
    """Latest DailyMemorySummary by created_at; return summary text or None."""
    try:
        models = _get_models()
        DailyMemorySummary = getattr(models, "DailyMemorySummary", None)
        if DailyMemorySummary is None:
            return None
        row = (
            db.query(DailyMemorySummary)
            .filter(DailyMemorySummary.user_id == user_id)
            .order_by(DailyMemorySummary.created_at.desc())
            .first()
        )
        if row and getattr(row, "summary", None) and str(row.summary).strip():
            return str(row.summary).strip()
    except Exception as e:
        logger.debug("%s DailyMemorySummary lookup failed: %s", _LOG_PREFIX, e)
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

        if preferred_name is None or language is None or timezone is None:
            try:
                models = _get_models()
                UserMemoryFact = getattr(models, "UserMemoryFact", None)
                if UserMemoryFact is not None:
                    facts = (
                        self.db.query(UserMemoryFact)
                        .filter(UserMemoryFact.user_id == user_id)
                        .all()
                    )
                    for f in facts:
                        if f.domain == "preferences" or f.key in ("preferred_name", "language", "timezone", "engagement_level"):
                            val = _safe_json(f.value_json)
                            if f.key == "preferred_name" and preferred_name is None and isinstance(val, str):
                                preferred_name = val.strip()
                            elif f.key == "language" and language is None and isinstance(val, str):
                                language = val.strip()
                            elif f.key == "timezone" and timezone is None:
                                if isinstance(val, dict) and val.get("tz"):
                                    timezone = str(val["tz"]).strip()
                                elif isinstance(val, str):
                                    timezone = val.strip()
                            elif f.key == "engagement_level" and engagement_level is None and isinstance(val, str):
                                engagement_level = val.strip()
                    if UserMemoryFact is not None and facts:
                        source_meta["memory_facts"] = True
            except Exception as e:
                logger.debug("%s UserMemoryFact fallback failed: %s", _LOG_PREFIX, e)

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
            engagement_level = _get_memory_fact_value(self.db, user_id, "preferences", "engagement_level")
            if not isinstance(engagement_level, str):
                engagement_level = None

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

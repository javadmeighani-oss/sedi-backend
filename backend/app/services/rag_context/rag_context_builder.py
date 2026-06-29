# backend.app.services.rag_context.rag_context_builder
"""
Stage 23 Step 5: Build facts-anchored RagContextPack from UserContextPack + medical conditions.
Fail-open; defensive imports for optional tables.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app.services.user_context import UserContextService
from backend.app.services.rag_context.rag_context_pack import RagContextPack

logger = logging.getLogger(__name__)
_LOG_PREFIX = "[RagContext]"

LIFESTYLE_MAX_CHARS = 300
DAILY_SUMMARY_MAX_CHARS = 200
GOALS_MAX_ITEMS = 5


def _get_medical_conditions_for_user(db: Session, user_id: int) -> List[str]:
    """Read condition names from UserCondition + MedicalCondition if models exist. Else return []."""
    try:
        from backend.app import models
        UserCondition = getattr(models, "UserCondition", None)
        MedicalCondition = getattr(models, "MedicalCondition", None)
        if UserCondition is None or MedicalCondition is None:
            return []
        rows = (
            db.query(MedicalCondition.name)
            .join(UserCondition, UserCondition.condition_id == MedicalCondition.id)
            .filter(UserCondition.user_id == user_id)
            .distinct()
            .all()
        )
        return [r[0] for r in rows if r and r[0]]
    except Exception as e:
        logger.debug("%s medical_conditions load failed: %s", _LOG_PREFIX, e)
        return []


MEDICATIONS_CONTEXT_MAX = 10


def _get_user_medications_for_context(db: Session, user_id: int) -> List[str]:
    """Summarize user medications for RAG (name, dosage, times). Fail-open."""
    try:
        from backend.app import models
        from backend.app.services.user_medication_service import format_time_of_day

        UserMedication = getattr(models, "UserMedication", None)
        Medication = getattr(models, "Medication", None)
        if UserMedication is None or Medication is None:
            return []
        rows = (
            db.query(models.UserMedication, models.Medication)
            .join(models.Medication, models.UserMedication.medication_id == models.Medication.id)
            .filter(models.UserMedication.user_id == user_id)
            .limit(MEDICATIONS_CONTEXT_MAX)
            .all()
        )
        out: List[str] = []
        for um, med in rows:
            parts = [med.name]
            if um.user_dosage and str(um.user_dosage).strip():
                parts.append(str(um.user_dosage).strip())
            schedules = (
                db.query(models.UserMedicationSchedule)
                .filter(models.UserMedicationSchedule.user_medication_id == um.id)
                .all()
            )
            if schedules:
                times = sorted(format_time_of_day(s.time_of_day) for s in schedules)
                parts.append("at " + ", ".join(times))
            out.append(" ".join(parts))
        return out
    except Exception as e:
        logger.debug("%s user_medications load failed: %s", _LOG_PREFIX, e)
        return []


def build_rag_context_pack(
    db: Session,
    user_id: int,
    fallback_language: Optional[str] = None,
) -> RagContextPack:
    """
    Build a facts-anchored RAG context pack from UserContextPack and optional medical data.
    Fail-open: on any failure returns a minimal pack with language resolved to fallback or "en".
    """
    try:
        from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
    except ImportError:
        try:
            from app.core.conversation.persona_policy_v1 import PersonaPolicyV1
        except ImportError:
            return RagContextPack(
                user_id=user_id,
                language="en",
                meta={"sources": [], "error": "import"},
            )

    pack = None
    try:
        pack = UserContextService(db).get_user_context(user_id)
    except Exception as e:
        logger.debug("%s UserContext fetch failed: %s", _LOG_PREFIX, e)

    language = "en"
    preferred_name: Optional[str] = None
    stable_facts: Dict[str, Any] = {}
    lifestyle_summary: Optional[str] = None
    daily_summary: Optional[str] = None
    goals: List[str] = []
    meta: Dict[str, Any] = {"sources": []}

    if pack:
        # Prefer pack.language when present; respect user context for deterministic tests
        raw_lang = getattr(pack, "language", None)
        language = PersonaPolicyV1.resolve_language(
            raw_lang if (raw_lang and str(raw_lang).strip()) else fallback_language
        )
        preferred_name = (getattr(pack, "preferred_name", None) or "").strip() or None
        qh = getattr(pack, "quiet_hours", None)
        if qh:
            stable_facts["quiet_hours"] = {
                "start": getattr(qh, "start", None),
                "end": getattr(qh, "end", None),
            }
        tz = getattr(pack, "timezone", None)
        if tz and str(tz).strip():
            stable_facts["timezone"] = str(tz).strip()
        eng = getattr(pack, "engagement_level", None)
        if eng and str(eng).strip():
            stable_facts["engagement_level"] = str(eng).strip()
        by = getattr(pack, "birth_year", None)
        if by is not None:
            stable_facts["birth_year"] = by
        sx = getattr(pack, "sex", None)
        if sx and str(sx).strip():
            stable_facts["sex"] = str(sx).strip()
        ap = getattr(pack, "addressing_preference", None)
        if ap and str(ap).strip():
            stable_facts["addressing_preference"] = str(ap).strip()
        verified = getattr(pack, "verified_facts", None)
        if isinstance(verified, dict) and verified:
            stable_facts["verified"] = verified
        meta["sources"].append("user_context")

        lifestyle = getattr(pack, "lifestyle", None)
        if lifestyle and getattr(lifestyle, "text", None) and str(lifestyle.text).strip():
            lifestyle_summary = str(lifestyle.text).strip()[:LIFESTYLE_MAX_CHARS]
        daily = getattr(pack, "daily_memory_summary", None)
        if daily and str(daily).strip():
            daily_summary = str(daily).strip()[:DAILY_SUMMARY_MAX_CHARS]
        g = getattr(pack, "goals", None)
        if g and getattr(g, "items", None):
            goals = [str(x).strip() for x in g.items if x][:GOALS_MAX_ITEMS]
    else:
        language = PersonaPolicyV1.resolve_language(fallback_language)

    medical_conditions: List[str] = []
    try:
        medical_conditions = _get_medical_conditions_for_user(db, user_id)
        if medical_conditions:
            meta["sources"].append("user_conditions")
    except Exception as e:
        logger.debug("%s medical_conditions failed: %s", _LOG_PREFIX, e)

    medications_summary: List[str] = []
    try:
        medications_summary = _get_user_medications_for_context(db, user_id)
        if medications_summary:
            stable_facts["medications"] = medications_summary
            meta["sources"].append("user_medications")
    except Exception as e:
        logger.debug("%s user_medications failed: %s", _LOG_PREFIX, e)

    return RagContextPack(
        user_id=user_id,
        language=language,
        preferred_name=preferred_name,
        stable_facts=stable_facts,
        lifestyle_summary=lifestyle_summary,
        daily_summary=daily_summary,
        medical_conditions=medical_conditions,
        goals=goals,
        meta=meta,
    )


RAG_CONTEXT_MAX_CHARS = 1200


def serialize_rag_pack_for_context(pack: RagContextPack, max_chars: int = RAG_CONTEXT_MAX_CHARS) -> str:
    """
    Serialize RagContextPack to a short summary for [RAG_CONTEXT] block.
    General info only; not diagnosis. Cap at max_chars.
    """
    lines: List[str] = []
    if pack.preferred_name:
        lines.append(f"User preferred name: {pack.preferred_name}")
    if pack.stable_facts:
        parts = []
        for k, v in list(pack.stable_facts.items())[:5]:
            if v is not None:
                parts.append(f"{k}={v}")
        if parts:
            lines.append("Stable facts: " + "; ".join(parts))
    if pack.goals:
        lines.append("Goals: " + ", ".join(pack.goals[:5]))
    if pack.lifestyle_summary:
        lines.append("Lifestyle: " + pack.lifestyle_summary[:200])
    if pack.daily_summary:
        lines.append("Recent: " + pack.daily_summary[:150])
    if pack.medical_conditions:
        lines.append("Known conditions (general info only): " + ", ".join(pack.medical_conditions[:10]))
    meds = (pack.stable_facts or {}).get("medications") if pack.stable_facts else None
    if isinstance(meds, list) and meds:
        lines.append("Medications: " + "; ".join(str(m) for m in meds[:MEDICATIONS_CONTEXT_MAX]))
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 3] + "..."
    return text

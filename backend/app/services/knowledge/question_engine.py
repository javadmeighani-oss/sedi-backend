# app/services/knowledge/question_engine.py
"""Question Engine V1: deterministic next-question selection for proactive data collection."""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.knowledge.service import ensure_profile_core

logger = logging.getLogger(__name__)

# Confirmation question text by fact_key. {value} replaced with candidate value.
CONFIRM_QUESTIONS: Dict[str, str] = {
    "sleep_quality": "درست متوجه شدم خواب‌تون دیشب خوب نبود؟",
    "stress_level": "درست متوجه شدم این روزها استرس‌تون بالاست؟",
    "stress_level_low": "درست متوجه شدم این روزها آرومید؟",
    "daily_walk_minutes": "درست متوجه شدم روزانه حدود {value} دقیقه پیاده‌روی می‌کنید؟",
    "medications": "درست متوجه شدم داروی «{value}» مصرف می‌کنید؟",
}

CONFIRM_QUESTION_FALLBACK = "درست متوجه شدم؟"

# Profile core fields in priority order
PROFILE_FIELDS = ["birth_year", "sex", "height_cm", "weight_kg", "language", "quiet_hours"]

# Care fact types in priority order (medications = medications OR medications_list)
CARE_FACT_TYPES = ["medications", "medications_list", "activity_level", "stress_level", "sleep_quality"]

# Question definitions: question_id -> { field_key, text, options, reason }
QUESTIONS: Dict[str, Dict[str, Any]] = {
    "kc_q_birth_year_v1": {
        "field_key": "birth_year",
        "text": "چه سالی به دنیا آمدی؟ تا برات مراقبت بهتری داشته باشم.",
        "options": [],
        "reason": "برای شخصی‌سازی مراقبت بر اساس سن.",
    },
    "kc_q_sex_v1": {
        "field_key": "sex",
        "text": "جنسیتت چیه؟ تا بهتر بتونم راهنماییت کنم.",
        "options": ["مرد", "زن", "سایر"],
        "reason": "برای اینکه مراقبت دقیق‌تر باشد.",
    },
    "kc_q_height_v1": {
        "field_key": "height_cm",
        "text": "قدت چند سانتی‌متره؟",
        "options": [],
        "reason": "برای محاسبه‌های سلامتی.",
    },
    "kc_q_weight_v1": {
        "field_key": "weight_kg",
        "text": "وزنت تقریباً چند کیلوگرمه؟",
        "options": [],
        "reason": "برای مراقبت بهتر.",
    },
    "kc_q_language_v1": {
        "field_key": "language",
        "text": "کدوم زبان رو ترجیح میدی؟",
        "options": ["فارسی", "انگلیسی", "عربی"],
        "reason": "تا با هم راحت‌تر صحبت کنیم.",
    },
    "kc_q_quiet_hours_v1": {
        "field_key": "quiet_hours",
        "text": "چه ساعتی میخوای استراحت کنی تا مزاحمت نشم؟ (مثلاً ۲۲ تا ۶)",
        "options": [],
        "reason": "تا در ساعات استراحات پیام نفرستم.",
    },
    "kc_q_medications_v1": {
        "field_key": "medications_list",
        "text": "الان دارویی مصرف می‌کنی؟",
        "options": ["نه، هیچی", "بله، یکی دو تا", "بله، چندتا", "سایر"],
        "reason": "برای یادآوری و مراقبت.",
    },
    "kc_q_activity_level_v1": {
        "field_key": "activity_level",
        "text": "روزانه چقدر تحرک داری؟",
        "options": ["کم (نشسته بیشتر)", "متوسط (پیاده‌روی)", "زیاد (ورزش منظم)", "سایر"],
        "reason": "برای پیشنهادهای بهتر.",
    },
    "kc_q_stress_level_v1": {
        "field_key": "stress_level",
        "text": "این روزها استرس داری؟",
        "options": ["کم", "متوسط", "زیاد", "سایر"],
        "reason": "تا بیشتر مراقبت کنم.",
    },
    "kc_q_sleep_quality_v1": {
        "field_key": "sleep_quality",
        "text": "خوابت چطوره؟",
        "options": ["خوبه", "متوسط", "بد", "سایر"],
        "reason": "برای اینکه مراقبت دقیق‌تر باشد.",
    },
}


def _has_fact(db: Session, user_id: int, fact_type: str) -> bool:
    """Check if user has active kc_user_fact for given fact_type."""
    row = (
        db.query(models.KcUserFact)
        .filter(
            models.KcUserFact.user_id == user_id,
            models.KcUserFact.fact_type == fact_type,
            models.KcUserFact.valid_to.is_(None),
        )
        .first()
    )
    return row is not None


def _has_sleep_window(db: Session, user_id: int) -> bool:
    return _has_fact(db, user_id, "sleep_window")


def _get_pending_confirmation_candidate(db: Session, user_id: int) -> Optional[models.KcFactCandidate]:
    """Return earliest pending candidate with needs_confirmation in metadata."""
    rows = (
        db.query(models.KcFactCandidate)
        .filter(
            models.KcFactCandidate.user_id == user_id,
            models.KcFactCandidate.status == "pending",
            models.KcFactCandidate.metadata_json.isnot(None),
        )
        .order_by(models.KcFactCandidate.created_at.asc())
        .all()
    )
    for row in rows:
        try:
            meta = json.loads(row.metadata_json or "{}")
            if meta.get("needs_confirmation"):
                return row
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _format_confirm_question(cand: models.KcFactCandidate) -> str:
    """Build Persian confirmation question from candidate."""
    try:
        val = json.loads(cand.value_json)
        val_str = str(val) if val is not None else ""
    except (json.JSONDecodeError, TypeError):
        val_str = ""
    key = cand.fact_type
    if key == "stress_level" and val_str == "low":
        key = "stress_level_low"
    tpl = CONFIRM_QUESTIONS.get(key, CONFIRM_QUESTIONS.get(cand.fact_type, CONFIRM_QUESTION_FALLBACK))
    return tpl.format(value=val_str) if "{value}" in tpl else tpl


def _get_next_question_data(db: Session, user_id: int) -> Optional[Dict[str, Any]]:
    """
    Return next question payload or None. V1 deterministic priority:
    A) Ensure profile_core exists
    A1) Pending needs_confirmation candidates -> confirm_candidate first
    B) Missing profile fields -> birth_year, sex, height_cm, weight_kg, language, quiet_hours
    C) sleep_window exists but sleep_quality missing -> sleep_quality first
    D) Missing care facts -> medications, medications_list, activity_level, stress_level, sleep_quality
    """
    profile = ensure_profile_core(db, user_id)

    # A1) Pending confirmation candidates first
    cand = _get_pending_confirmation_candidate(db, user_id)
    if cand:
        text = _format_confirm_question(cand)
        return {
            "user_id": user_id,
            "question_id": "kc_q_confirm_candidate_v1",
            "question_type": "confirm_candidate",
            "field_key": cand.fact_type,
            "candidate_id": cand.id,
            "text": text,
            "options": ["بله، درسته", "نه"],
            "reason": "تایید اطلاعات استخراج‌شده از گفتگو.",
        }

    # B) Missing profile fields
    for f in PROFILE_FIELDS:
        val = None
        if f == "quiet_hours":
            val = profile.quiet_start or profile.quiet_end
        else:
            val = getattr(profile, f, None)
        if val is None or (isinstance(val, str) and not val.strip()):
            qid = f"kc_q_{f}_v1"
            if qid in QUESTIONS:
                q = QUESTIONS[qid].copy()
                return {
                    "user_id": user_id,
                    "question_id": qid,
                    "field_key": q["field_key"],
                    "text": q["text"],
                    "options": q.get("options") or [],
                    "reason": q.get("reason", ""),
                }

    # C) sleep_window exists but sleep_quality missing
    if _has_sleep_window(db, user_id) and not _has_fact(db, user_id, "sleep_quality"):
        q = QUESTIONS["kc_q_sleep_quality_v1"].copy()
        return {
            "user_id": user_id,
            "question_id": "kc_q_sleep_quality_v1",
            "field_key": q["field_key"],
            "text": q["text"],
            "options": q.get("options") or [],
            "reason": q.get("reason", ""),
        }

    # D) Missing care facts
    for ft in CARE_FACT_TYPES:
        if ft in ("medications", "medications_list"):
            if _has_fact(db, user_id, "medications") or _has_fact(db, user_id, "medications_list"):
                continue
        if _has_fact(db, user_id, ft):
            continue
        qid_map = {
            "medications": "kc_q_medications_v1",
            "medications_list": "kc_q_medications_v1",
            "activity_level": "kc_q_activity_level_v1",
            "stress_level": "kc_q_stress_level_v1",
            "sleep_quality": "kc_q_sleep_quality_v1",
        }
        qid = qid_map.get(ft, f"kc_q_{ft}_v1")
        if qid in QUESTIONS:
            q = QUESTIONS[qid].copy()
            return {
                "user_id": user_id,
                "question_id": qid,
                "field_key": q["field_key"],
                "text": q["text"],
                "options": q.get("options") or [],
                "reason": q.get("reason", ""),
            }

    return None


def get_next_question(db: Session, user_id: int) -> Optional[Dict[str, Any]]:
    """Get next question for user. Returns dict or None. Logs only user_id, question_id, field_key."""
    data = _get_next_question_data(db, user_id)
    if data:
        logger.info("kc_next_question user_id=%s question_id=%s field_key=%s", user_id, data.get("question_id"), data.get("field_key"))
    return data

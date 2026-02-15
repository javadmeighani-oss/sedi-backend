# app/services/knowledge/service.py
"""Knowledge Capture V1 service: create candidate, accept, reject, list facts, apply answer."""
import json
import logging
import re
from datetime import datetime, time
from typing import Any, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app import models

logger = logging.getLogger(__name__)

SOURCES = ("chat", "form", "import")
PROFILE_COLUMNS = {"birth_year", "sex", "height_cm", "weight_kg", "language", "quiet_start", "quiet_end", "quiet_hours"}
STATUSES = ("pending", "accepted", "rejected")
VERIFIED_BY = ("user", "system", "clinician")


def _sanitize_evidence(s: Optional[str], max_len: int = 500) -> Optional[str]:
    """Truncate evidence for storage; avoid PII in logs."""
    if not s or not isinstance(s, str):
        return None
    return s.strip()[:max_len] or None


def create_candidate(
    db: Session,
    user_id: int,
    source: str,
    fact_type: str,
    value_json: str,
    confidence: float,
    evidence: Optional[str] = None,
) -> models.KcFactCandidate:
    """Create a pending fact candidate. source in (chat, form, import)."""
    src = (source or "chat").strip().lower()
    if src not in SOURCES:
        src = "chat"
    if not 0 <= confidence <= 1:
        confidence = max(0, min(1, confidence))
    ev = _sanitize_evidence(evidence)
    row = models.KcFactCandidate(
        user_id=user_id,
        source=src,
        fact_type=(fact_type or "").strip() or "unknown",
        value_json=value_json or "{}",
        confidence=float(confidence),
        evidence=ev,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("kc_candidate_created id=%s user_id=%s fact_type=%s source=%s", row.id, user_id, row.fact_type, src)
    return row


def accept_candidate(
    db: Session,
    candidate_id: int,
    verified_by: str = "system",
) -> Optional[models.KcUserFact]:
    """
    Accept a pending candidate: insert into kc_user_facts, close previous valid_to
    for same (user_id, fact_type). Returns new KcUserFact or None if not found/invalid.
    """
    cand = db.query(models.KcFactCandidate).filter(models.KcFactCandidate.id == candidate_id).first()
    if not cand:
        return None
    if cand.status != "pending":
        logger.info("kc_accept_skipped id=%s status=%s", candidate_id, cand.status)
        return None
    vby = (verified_by or "system").strip().lower()
    if vby not in VERIFIED_BY:
        vby = "system"
    now = datetime.utcnow()
    # Close any open fact for same user + fact_type
    prev = (
        db.query(models.KcUserFact)
        .filter(
            models.KcUserFact.user_id == cand.user_id,
            models.KcUserFact.fact_type == cand.fact_type,
            models.KcUserFact.valid_to.is_(None),
        )
        .all()
    )
    for p in prev:
        p.valid_to = now
        p.updated_at = now
    fact = models.KcUserFact(
        user_id=cand.user_id,
        fact_type=cand.fact_type,
        value_json=cand.value_json,
        verified_by=vby,
        valid_from=now,
        valid_to=None,
    )
    db.add(fact)
    cand.status = "accepted"
    db.commit()
    db.refresh(fact)
    logger.info(
        "kc_candidate_accepted id=%s user_id=%s fact_type=%s kc_user_fact_id=%s",
        candidate_id, cand.user_id, cand.fact_type, fact.id,
    )
    return fact


def reject_candidate(db: Session, candidate_id: int) -> bool:
    """Reject a pending candidate. Returns True if updated."""
    cand = db.query(models.KcFactCandidate).filter(models.KcFactCandidate.id == candidate_id).first()
    if not cand or cand.status != "pending":
        return False
    cand.status = "rejected"
    db.commit()
    logger.info("kc_candidate_rejected id=%s user_id=%s", candidate_id, cand.user_id)
    return True


def list_user_facts(
    db: Session,
    user_id: int,
) -> List[models.KcUserFact]:
    """List all kc_user_facts for a user, ordered by valid_from desc."""
    rows = (
        db.query(models.KcUserFact)
        .filter(models.KcUserFact.user_id == user_id)
        .order_by(models.KcUserFact.valid_from.desc())
        .all()
    )
    return list(rows)


def _value_to_json(value: Any) -> str:
    """Ensure value is stored as JSON string. Scalars wrapped as JSON."""
    if value is None:
        return "null"
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except (TypeError, ValueError):
            pass
        return json.dumps(value)
    return json.dumps(value)


def _parse_quiet_hours(value: str) -> Tuple[Optional[time], Optional[time]]:
    """Parse '22-6' or '22:00-06:00' into (start_time, end_time)."""
    if not value or not isinstance(value, str):
        return None, None
    s = value.strip().replace(" ", "")
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*[-–]\s*(\d{1,2})(?::(\d{2}))?", s)
    if not m:
        return None, None
    try:
        sh, sm, eh, em = int(m.group(1)), int(m.group(2) or 0), int(m.group(3)), int(m.group(4) or 0)
        return time(sh, sm), time(eh, em)
    except (ValueError, TypeError):
        return None, None


def ensure_profile_core(db: Session, user_id: int) -> models.UserProfileCore:
    """Ensure user_profile_core row exists; create empty row if missing."""
    row = db.query(models.UserProfileCore).filter(models.UserProfileCore.user_id == user_id).first()
    if row:
        return row
    row = models.UserProfileCore(user_id=user_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("kc_profile_core_created user_id=%s", user_id)
    return row


def apply_answer(
    db: Session,
    user_id: int,
    field_key: str,
    value: Any,
) -> dict:
    """
    Apply user answer: update profile_core or create+accept fact.
    Returns {"applied": "profile"|"fact", "fact_id"?: int}.
    """
    field_key = (field_key or "").strip()
    if not field_key:
        raise ValueError("field_key required")

    if field_key in PROFILE_COLUMNS:
        profile = ensure_profile_core(db, user_id)
        if field_key == "birth_year":
            profile.birth_year = int(value) if value is not None and str(value).strip() else None
        elif field_key == "sex":
            profile.sex = str(value).strip() if value is not None and str(value).strip() else None
        elif field_key == "height_cm":
            profile.height_cm = int(float(value)) if value is not None and str(value).strip() else None
        elif field_key == "weight_kg":
            profile.weight_kg = float(value) if value is not None and str(value).strip() else None
        elif field_key == "language":
            profile.language = str(value).strip() if value is not None else None
        elif field_key == "quiet_hours":
            qs, qe = _parse_quiet_hours(str(value) if value else "")
            if qs is not None:
                profile.quiet_start = qs
            if qe is not None:
                profile.quiet_end = qe
        elif field_key in ("quiet_start", "quiet_end"):
            if value and isinstance(value, str) and ":" in value:
                parts = value.strip().split(":")
                if len(parts) >= 2:
                    h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
                    t = time(h, m)
                    if field_key == "quiet_start":
                        profile.quiet_start = t
                    else:
                        profile.quiet_end = t
        profile.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(profile)
        logger.info("kc_apply_answer user_id=%s field_key=%s applied=profile", user_id, field_key)
        return {"applied": "profile"}

    # Else: create candidate + accept into kc_user_facts
    fact_type = field_key
    value_json = _value_to_json(value)
    cand = create_candidate(
        db=db,
        user_id=user_id,
        source="form",
        fact_type=fact_type,
        value_json=value_json,
        confidence=1.0,
        evidence=None,
    )
    fact = accept_candidate(db=db, candidate_id=cand.id, verified_by="user")
    logger.info("kc_apply_answer user_id=%s field_key=%s applied=fact fact_id=%s", user_id, field_key, fact.id if fact else None)
    return {"applied": "fact", "fact_id": fact.id if fact else None}

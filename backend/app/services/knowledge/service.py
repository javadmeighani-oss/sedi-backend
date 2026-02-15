# app/services/knowledge/service.py
"""Knowledge Capture V1 service: create candidate, accept, reject, list facts."""
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.app import models

logger = logging.getLogger(__name__)

SOURCES = ("chat", "form", "import")
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

# app/services/knowledge/conversation_extraction_service.py
"""Orchestration: extract from message, create/accept candidates by confidence."""
import json
import logging
import os
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app.services.knowledge.conversation_extractor_v1 import (
    ExtractedCandidate,
    extract_candidates,
)
from backend.app.services.knowledge.service import create_candidate, accept_candidate

logger = logging.getLogger(__name__)


def _get_auto_accept_threshold() -> float:
    return float(os.environ.get("KC_AUTO_ACCEPT_THRESHOLD", "0.85"))


def _get_confirm_threshold() -> float:
    return float(os.environ.get("KC_CONFIRM_THRESHOLD", "0.60"))


def process_message(
    db: Session,
    user_id: int,
    text: str,
    language: str,
    source_message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract candidates from text, create/accept per thresholds.
    Returns: {extracted_count, created_candidates_count, auto_accepted_count, ignored_count}
    """
    auto_threshold = _get_auto_accept_threshold()
    confirm_threshold = _get_confirm_threshold()

    extracted = extract_candidates(text=text, language=language)
    extracted_count = len(extracted)

    created_candidates_count = 0
    auto_accepted_count = 0
    ignored_count = 0

    for c in extracted:
        value_json = json.dumps(c.fact_value, ensure_ascii=False)
        ev = (c.evidence or "")[:500]

        if c.confidence >= auto_threshold:
            meta = {
                "source_message_id": source_message_id,
                "auto_accepted": True,
                "pattern_id": c.pattern_id,
            }
            cand = create_candidate(
                db=db,
                user_id=user_id,
                source="chat_extraction_v1",
                fact_type=c.fact_key,
                value_json=value_json,
                confidence=c.confidence,
                evidence=ev,
                metadata_json=json.dumps(meta, ensure_ascii=False),
            )
            created_candidates_count += 1
            fact = accept_candidate(db=db, candidate_id=cand.id, verified_by="system")
            if fact:
                auto_accepted_count += 1
            logger.info(
                "[KC-EXTRACT] user_id=%s key=%s conf=%.2f action=accepted",
                user_id, c.fact_key, c.confidence,
            )
        elif c.confidence >= confirm_threshold:
            meta = {
                "needs_confirmation": True,
                "source_message_id": source_message_id,
                "pattern_id": c.pattern_id,
            }
            create_candidate(
                db=db,
                user_id=user_id,
                source="chat_extraction_v1",
                fact_type=c.fact_key,
                value_json=value_json,
                confidence=c.confidence,
                evidence=ev,
                metadata_json=json.dumps(meta, ensure_ascii=False),
            )
            created_candidates_count += 1
            logger.info(
                "[KC-EXTRACT] user_id=%s key=%s conf=%.2f action=candidate",
                user_id, c.fact_key, c.confidence,
            )
        else:
            ignored_count += 1
            logger.info(
                "[KC-EXTRACT] user_id=%s key=%s conf=%.2f action=ignored",
                user_id, c.fact_key, c.confidence,
            )

    return {
        "extracted_count": extracted_count,
        "created_candidates_count": created_candidates_count,
        "auto_accepted_count": auto_accepted_count,
        "ignored_count": ignored_count,
    }

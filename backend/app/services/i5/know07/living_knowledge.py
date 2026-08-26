"""Living-knowledge events → eligibility / SCIS invalidation (bounded reuse)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    FreshnessState,
    KnowledgeUnitRuntimeEligibility,
    PublicationState,
)
from backend.app.services.i5.know05.rag_coherence import invalidate_rag_for_knowledge_unit
from backend.app.services.i5.know07 import LIVING_KNOWLEDGE_EVENTS


@dataclass(frozen=True)
class LivingKnowledgeAction:
    event: str
    affects_eligibility: bool
    affects_current_version: bool
    invalidates_scis_index: bool
    target_publication_state: Optional[str] = None
    target_freshness_state: Optional[str] = None
    set_retraction_reason: Optional[str] = None


_EVENT_ACTIONS: dict[str, LivingKnowledgeAction] = {
    "NEW_PUBLICATION": LivingKnowledgeAction(
        "NEW_PUBLICATION", True, True, False, target_freshness_state=FreshnessState.CURRENT.value
    ),
    "GUIDELINE_EDITION": LivingKnowledgeAction(
        "GUIDELINE_EDITION", True, True, True, target_freshness_state=FreshnessState.STALE.value
    ),
    "CORRECTION": LivingKnowledgeAction(
        "CORRECTION", True, True, True, target_freshness_state=FreshnessState.STALE.value
    ),
    "EXPRESSION_OF_CONCERN": LivingKnowledgeAction(
        "EXPRESSION_OF_CONCERN", True, False, True
    ),
    "RETRACTION": LivingKnowledgeAction(
        "RETRACTION",
        True,
        True,
        True,
        target_publication_state=PublicationState.WITHDRAWN.value,
        set_retraction_reason="RETRACTION",
    ),
    "DRUG_APPROVAL_SAFETY_CHANGE": LivingKnowledgeAction(
        "DRUG_APPROVAL_SAFETY_CHANGE", True, True, True, target_freshness_state=FreshnessState.STALE.value
    ),
    "TRIAL_STATUS_CHANGE": LivingKnowledgeAction(
        "TRIAL_STATUS_CHANGE", True, True, True, target_freshness_state=FreshnessState.STALE.value
    ),
    "GUIDELINE_SUPERSESSION": LivingKnowledgeAction(
        "GUIDELINE_SUPERSESSION",
        True,
        True,
        True,
        target_publication_state=PublicationState.SUPERSEDED.value,
        target_freshness_state=FreshnessState.STALE.value,
    ),
}


def resolve_living_knowledge_action(event: str) -> LivingKnowledgeAction:
    token = str(event or "").strip().upper()
    if token not in LIVING_KNOWLEDGE_EVENTS:
        raise ValueError(f"UNKNOWN_LIVING_KNOWLEDGE_EVENT:{token}")
    return _EVENT_ACTIONS[token]


def apply_living_knowledge_event_to_ku(
    db: Session,
    *,
    knowledge_unit_id: int,
    event: str,
    commit: bool = False,
) -> dict[str, Any]:
    """Bounded mutation of KU currency + optional KCE invalidation (no schema change)."""
    action = resolve_living_knowledge_action(event)
    ku = db.query(models.KnowledgeUnit).filter_by(id=int(knowledge_unit_id)).one()
    if action.target_publication_state:
        ku.publication_state = action.target_publication_state
    if action.target_freshness_state:
        ku.freshness_state = action.target_freshness_state
    if action.set_retraction_reason:
        ku.retraction_reason = action.set_retraction_reason
        ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.REVOKED.value
    elif action.affects_eligibility and action.invalidates_scis_index:
        # Fail-closed: leave eligibility recomputation to gate; force non-eligible when superseded/stale.
        if ku.publication_state == PublicationState.SUPERSEDED.value or ku.freshness_state != FreshnessState.CURRENT.value:
            ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value

    invalidated = 0
    if action.invalidates_scis_index:
        invalidated = invalidate_rag_for_knowledge_unit(
            db, knowledge_unit_id=int(knowledge_unit_id), reason=action.event
        )
    if commit:
        db.commit()
    else:
        db.flush()
    return {
        "event": action.event,
        "knowledge_unit_id": int(knowledge_unit_id),
        "affects_eligibility": action.affects_eligibility,
        "affects_current_version": action.affects_current_version,
        "kce_invalidated": invalidated,
        "publication_state": ku.publication_state,
        "freshness_state": ku.freshness_state,
        "runtime_eligibility": ku.runtime_eligibility,
        "retraction_reason": ku.retraction_reason,
    }

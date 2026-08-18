"""Shared governed KU finalize + idempotent lexical-only index path (I5-S49)."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import ConflictState, KnowledgeUnitRuntimeEligibility
from backend.app.services.i5.governed_low_risk_eligibility import (
    finalize_governed_runtime_eligibility,
    normalize_eligibility_domain,
)


def provenance_source_identity_matches(
    *,
    authoritative_source_profile_id: int,
    incoming_source_profile_id: int,
) -> bool:
    return int(authoritative_source_profile_id) == int(incoming_source_profile_id)


def ku_blocks_governed_reevaluation(ku: Any) -> bool:
    if getattr(ku, "retraction_reason", None):
        return True
    conflict = str(getattr(ku, "conflict_state", "") or "")
    return bool(conflict and conflict != ConflictState.NONE.value)


def _current_eligibility(ku: Any) -> KnowledgeUnitRuntimeEligibility:
    value = str(getattr(ku, "runtime_eligibility", "") or KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value)
    try:
        return KnowledgeUnitRuntimeEligibility(value)
    except ValueError:
        return KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE


def apply_governed_finalize_and_lexical_index(
    db: Session,
    ku: models.KnowledgeUnit,
    *,
    source_key: str,
    source_profile_id: int,
    raw_evidence_id: Optional[int] = None,
    authoritative_provenance: Optional[models.KnowledgeProvenance] = None,
    incoming_source_profile_id: Optional[int] = None,
) -> KnowledgeUnitRuntimeEligibility:
    """Governed re-evaluation and lexical-only indexing for new and existing KU rows."""
    incoming_id = int(incoming_source_profile_id if incoming_source_profile_id is not None else source_profile_id)
    auth_id = int(source_profile_id)
    if authoritative_provenance is not None:
        auth_id = int(authoritative_provenance.source_profile_id)
        if not provenance_source_identity_matches(
            authoritative_source_profile_id=auth_id,
            incoming_source_profile_id=incoming_id,
        ):
            return _current_eligibility(ku)

    if ku_blocks_governed_reevaluation(ku):
        return _current_eligibility(ku)

    if not bool(getattr(ku, "provenance_complete", False)):
        ku.provenance_complete = True

    resolved_key = source_key
    gsp = db.query(models.GovernedSourceProfile).filter_by(id=auth_id).one_or_none()
    if gsp is not None and gsp.canonical_key:
        resolved_key = str(gsp.canonical_key)

    elig = finalize_governed_runtime_eligibility(
        ku,
        source_key=resolved_key,
        domain=normalize_eligibility_domain(getattr(ku, "domain", None)),
    )
    ku.runtime_eligibility = elig.value
    db.flush()

    if elig == KnowledgeUnitRuntimeEligibility.ELIGIBLE:
        from backend.app.services.scis.serving_bridge import index_eligible_knowledge_unit_if_ready

        resolved_raw_id = raw_evidence_id
        if resolved_raw_id is None and authoritative_provenance is not None:
            resolved_raw_id = getattr(authoritative_provenance, "raw_evidence_id", None)
        index_eligible_knowledge_unit_if_ready(
            db,
            ku,
            source_profile_id=auth_id,
            raw_evidence_id=int(resolved_raw_id) if resolved_raw_id is not None else None,
        )
    return elig

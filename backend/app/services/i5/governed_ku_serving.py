"""Shared governed KU finalize + idempotent lexical-only index path (I5-S49)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import ConflictState, KnowledgeUnitRuntimeEligibility
from backend.app.services.i5.governed_low_risk_eligibility import (
    can_apply_governed_low_risk,
    connector_blocks_governed_low_risk,
    finalize_governed_runtime_eligibility,
    normalize_eligibility_domain,
)
from backend.app.services.scis.lexical_indexing import LEXICAL_ONLY_MODEL_ID


@dataclass(frozen=True)
class UnchangedSourceReevaluationResult:
    examined: int = 0
    newly_eligible: int = 0
    already_eligible: int = 0
    newly_indexed: int = 0
    skipped_fail_closed: int = 0


def merge_unchanged_source_reevaluation_results(
    *results: UnchangedSourceReevaluationResult,
) -> UnchangedSourceReevaluationResult:
    examined = 0
    newly_eligible = 0
    already_eligible = 0
    newly_indexed = 0
    skipped_fail_closed = 0
    for result in results:
        examined += int(result.examined)
        newly_eligible += int(result.newly_eligible)
        already_eligible += int(result.already_eligible)
        newly_indexed += int(result.newly_indexed)
        skipped_fail_closed += int(result.skipped_fail_closed)
    return UnchangedSourceReevaluationResult(
        examined=examined,
        newly_eligible=newly_eligible,
        already_eligible=already_eligible,
        newly_indexed=newly_indexed,
        skipped_fail_closed=skipped_fail_closed,
    )


def knowledge_mutation_from_unchanged_source(result: UnchangedSourceReevaluationResult) -> bool:
    return int(result.newly_eligible) > 0 or int(result.newly_indexed) > 0


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


def _lexical_kce_count(db: Session, knowledge_unit_id: int) -> int:
    return (
        db.query(models.KnowledgeChunkEmbedding)
        .filter(
            models.KnowledgeChunkEmbedding.knowledge_unit_id == int(knowledge_unit_id),
            models.KnowledgeChunkEmbedding.model_identifier == LEXICAL_ONLY_MODEL_ID,
        )
        .count()
    )


def _source_profile_allows_unchanged_reevaluation(gsp: Optional[models.GovernedSourceProfile]) -> bool:
    if gsp is None:
        return False
    source_key = str(gsp.canonical_key or "")
    if not source_key:
        return False
    if connector_blocks_governed_low_risk(source_key):
        return False
    from backend.app.services.i5.trusted_source_manifest import governed_low_risk_eligible

    if not governed_low_risk_eligible(source_key):
        return False
    status = str(gsp.operational_status or "").upper()
    if status in {"DISABLED", "BLOCKED"}:
        return False
    return True


def reevaluate_existing_kus_for_unchanged_source(
    db: Session,
    *,
    source_profile_id: int,
) -> UnchangedSourceReevaluationResult:
    """Re-evaluate existing same-source KUs on HTTP 304 / NO_MATERIAL_CHANGE (no new evidence)."""
    examined = 0
    newly_eligible = 0
    already_eligible = 0
    newly_indexed = 0
    skipped_fail_closed = 0

    gsp = db.query(models.GovernedSourceProfile).filter_by(id=int(source_profile_id)).one_or_none()
    if not _source_profile_allows_unchanged_reevaluation(gsp):
        return UnchangedSourceReevaluationResult()

    source_key = str(gsp.canonical_key)
    provenance_rows = (
        db.query(models.KnowledgeProvenance)
        .filter(models.KnowledgeProvenance.source_profile_id == int(source_profile_id))
        .all()
    )

    for prov in provenance_rows:
        examined += 1
        if not provenance_source_identity_matches(
            authoritative_source_profile_id=int(prov.source_profile_id),
            incoming_source_profile_id=int(source_profile_id),
        ):
            skipped_fail_closed += 1
            continue

        ku = db.query(models.KnowledgeUnit).filter_by(id=int(prov.knowledge_unit_id)).one_or_none()
        if ku is None:
            skipped_fail_closed += 1
            continue
        if ku_blocks_governed_reevaluation(ku):
            skipped_fail_closed += 1
            continue
        if not bool(getattr(ku, "provenance_complete", False)):
            skipped_fail_closed += 1
            continue
        if not can_apply_governed_low_risk(
            source_key=source_key,
            domain=normalize_eligibility_domain(getattr(ku, "domain", None)),
            connector_key=source_key,
            provenance_complete=True,
        ):
            skipped_fail_closed += 1
            continue

        prior_elig = _current_eligibility(ku)
        if prior_elig == KnowledgeUnitRuntimeEligibility.ELIGIBLE:
            already_eligible += 1
        kce_before = _lexical_kce_count(db, int(ku.id))

        after_elig = apply_governed_finalize_and_lexical_index(
            db,
            ku,
            source_key=source_key,
            source_profile_id=int(source_profile_id),
            raw_evidence_id=getattr(prov, "raw_evidence_id", None),
            authoritative_provenance=prov,
            incoming_source_profile_id=int(source_profile_id),
        )

        if prior_elig != KnowledgeUnitRuntimeEligibility.ELIGIBLE:
            if after_elig == KnowledgeUnitRuntimeEligibility.ELIGIBLE:
                newly_eligible += 1
            else:
                skipped_fail_closed += 1

        if _lexical_kce_count(db, int(ku.id)) > kce_before:
            newly_indexed += 1

    return UnchangedSourceReevaluationResult(
        examined=examined,
        newly_eligible=newly_eligible,
        already_eligible=already_eligible,
        newly_indexed=newly_indexed,
        skipped_fail_closed=skipped_fail_closed,
    )

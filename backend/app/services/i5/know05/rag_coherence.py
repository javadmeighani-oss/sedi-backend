"""NF18 — DB↔SCIS/RAG coherence: all zero-states computed from canonical DB (no false zeroes)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.db03.authority_markers import (
    RAG_EMBEDDINGS_INTRODUCED,
    SCIS_01_PGVECTOR_PRODUCTION_APPLIED,
)
from backend.app.services.i5.enums import RightDecision
from backend.app.services.i5.know01.rights_engine import evaluate_automation_rights


RIGHTS_ALLOWED = "RIGHTS_ALLOWED"
RIGHTS_BLOCKED = "RIGHTS_BLOCKED"
RIGHTS_UNKNOWN = "RIGHTS_UNKNOWN"

_BLOCKING_PUB_STATES = frozenset({"SUPERSEDED", "WITHDRAWN"})
_BLOCKING_RIGHTS = frozenset(
    {
        RightDecision.UNKNOWN.value,
        RightDecision.DENIED.value,
        RightDecision.REVIEW_REQUIRED.value,
    }
)


@dataclass
class RagCoherenceReport:
    orphan_rag_record: int
    rag_record_without_db_authority: int
    rag_record_without_provenance: int
    retracted_rag_runtime_eligible: int
    superseded_rag_runtime_eligible: int
    rights_blocked_rag_eligible: int
    rag_eligible_without_runtime_eligible_db: int
    rag_db_identity_mismatch: int
    db_eligible_count: int
    rag_eligible_count: int
    rag_indexed_count: str | int
    rag_stale_count: int
    rag_invalidated_count: int
    rag_activated: bool
    production_rag_applied: bool
    computation_basis: str = "DB_DERIVED"

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    def assert_zero_states(self) -> None:
        for k in (
            "orphan_rag_record",
            "rag_record_without_db_authority",
            "rag_record_without_provenance",
            "retracted_rag_runtime_eligible",
            "superseded_rag_runtime_eligible",
            "rights_blocked_rag_eligible",
            "rag_eligible_without_runtime_eligible_db",
            "rag_db_identity_mismatch",
        ):
            if int(getattr(self, k)) != 0:
                raise AssertionError(f"RAG_ZERO_STATE_VIOLATION:{k}={getattr(self, k)}")


def resolve_ku_rights_state(db: Session, *, knowledge_unit_id: int) -> str:
    """Resolve rights via KnowledgeProvenance → GovernedSourceProfile (+ registry extension)."""
    prov = db.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=knowledge_unit_id).first()
    if prov is None:
        return RIGHTS_UNKNOWN
    gsp = db.query(models.GovernedSourceProfile).filter_by(id=prov.source_profile_id).first()
    if gsp is None:
        return RIGHTS_UNKNOWN
    if str(getattr(gsp, "runtime_eligibility", "") or "").upper() in {"NOT_ELIGIBLE", "SUSPENDED", "REVOKED"}:
        return RIGHTS_BLOCKED
    ext = (
        db.query(models.I5SourceRegistryExtension).filter_by(source_profile_id=gsp.id).first()
        if hasattr(models, "I5SourceRegistryExtension")
        else None
    )
    if ext is None:
        # No extension: fail closed for RAG automation unless GSP is explicitly ELIGIBLE
        if str(getattr(gsp, "runtime_eligibility", "") or "").upper() == "ELIGIBLE":
            return RIGHTS_ALLOWED
        return RIGHTS_UNKNOWN

    decision = evaluate_automation_rights(
        access_right=getattr(ext, "access_right", RightDecision.UNKNOWN.value),
        automation_right=getattr(ext, "automation_right", RightDecision.UNKNOWN.value),
        tdm_right=getattr(ext, "tdm_right", RightDecision.UNKNOWN.value),
        transform_right=getattr(ext, "transform_right", RightDecision.UNKNOWN.value),
        retain_raw_right=getattr(ext, "retain_raw_right", RightDecision.UNKNOWN.value),
        retain_derived_right=getattr(ext, "retain_derived_right", RightDecision.UNKNOWN.value),
        redistribution_right=getattr(ext, "redistribution_right", RightDecision.UNKNOWN.value),
        robots_state=getattr(ext, "robots_state", "UNKNOWN") or "UNKNOWN",
        processing_permission_mode=getattr(ext, "processing_permission_mode", None),
    )
    if not decision.allowed:
        if any(v in _BLOCKING_RIGHTS for v in decision.dimensions.values()):
            # UNKNOWN on critical dims → UNKNOWN classification; DENIED → BLOCKED
            if any(
                decision.dimensions.get(k) == RightDecision.UNKNOWN.value
                for k in ("access_right", "automation_right", "tdm_right", "transform_right")
            ):
                return RIGHTS_UNKNOWN
            return RIGHTS_BLOCKED
        return RIGHTS_BLOCKED
    return RIGHTS_ALLOWED


def ku_is_superseded_or_withdrawn(ku: models.KnowledgeUnit) -> bool:
    pub = str(getattr(ku, "publication_state", "") or "").upper()
    return pub in _BLOCKING_PUB_STATES


def ku_is_retracted(ku: models.KnowledgeUnit) -> bool:
    return bool(getattr(ku, "retraction_reason", None))


def ku_rag_eligible_from_db(db: Session, ku: models.KnowledgeUnit) -> bool:
    """Fail-closed RAG eligibility from canonical KU + provenance + rights + publication."""
    if str(getattr(ku, "runtime_eligibility", "") or "").upper() != "ELIGIBLE":
        return False
    if ku_is_retracted(ku) or ku_is_superseded_or_withdrawn(ku):
        return False
    if not bool(getattr(ku, "provenance_complete", False)):
        return False
    prov = db.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=ku.id).first()
    if prov is None:
        return False
    rights = resolve_ku_rights_state(db, knowledge_unit_id=ku.id)
    if rights != RIGHTS_ALLOWED:
        return False
    return True


def invalidate_rag_for_knowledge_unit(db: Session, *, knowledge_unit_id: int, reason: str) -> int:
    """Stamp retracted_at on KCE rows for a KU."""
    q = db.query(models.KnowledgeChunkEmbedding).filter_by(knowledge_unit_id=knowledge_unit_id)
    n = 0
    now = datetime.utcnow()
    for row in q.all():
        if row.retracted_at is None:
            row.retracted_at = now
            if hasattr(row, "index_generation") and row.index_generation is not None:
                row.index_generation = int(row.index_generation) + 1
            n += 1
    db.flush()
    return n


def audit_rag_coherence(db: Session) -> RagCoherenceReport:
    """Compute all coherence counters from actual DB relationships — never hardcode zeroes."""
    rag_activated = bool(RAG_EMBEDDINGS_INTRODUCED)
    prod_applied = bool(SCIS_01_PGVECTOR_PRODUCTION_APPLIED)

    kce_rows = list(db.query(models.KnowledgeChunkEmbedding).all()) if hasattr(models, "KnowledgeChunkEmbedding") else []

    orphan = 0
    no_auth = 0
    no_prov = 0
    retracted_eligible = 0
    superseded_eligible = 0
    rights_blocked_eligible = 0
    rag_without_runtime = 0
    identity_mismatch = 0
    indexed = 0
    stale = 0
    invalidated = 0

    for row in kce_rows:
        indexed += 1
        ku_id = getattr(row, "knowledge_unit_id", None)
        if ku_id is None:
            orphan += 1
            no_auth += 1
            continue
        ku = db.query(models.KnowledgeUnit).filter_by(id=ku_id).first()
        if ku is None:
            orphan += 1
            no_auth += 1
            continue

        row_iv = getattr(row, "immutable_version_id", None)
        ku_iv = getattr(ku, "immutable_version_id", None)
        if row_iv and ku_iv and str(row_iv) != str(ku_iv):
            identity_mismatch += 1

        prov = db.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=ku_id).first()
        if prov is None:
            no_prov += 1

        elig = str(getattr(ku, "runtime_eligibility", "") or "").upper()
        retracted_at = getattr(row, "retracted_at", None)

        if retracted_at is not None:
            invalidated += 1
            if elig == "ELIGIBLE":
                stale += 1

        # Retracted KU still runtime-eligible (and index not stamped) is a violation
        if ku_is_retracted(ku) and elig == "ELIGIBLE" and retracted_at is None:
            retracted_eligible += 1

        # Superseded/withdrawn KU still runtime-eligible
        if ku_is_superseded_or_withdrawn(ku) and elig == "ELIGIBLE":
            superseded_eligible += 1

        # Rights-blocked but treated as RAG-eligible (active index + ELIGIBLE KU)
        rights = resolve_ku_rights_state(db, knowledge_unit_id=ku_id)
        if rights in {RIGHTS_BLOCKED, RIGHTS_UNKNOWN} and elig == "ELIGIBLE" and retracted_at is None:
            rights_blocked_eligible += 1

        # Active index claim without DB runtime eligibility
        if retracted_at is None and elig != "ELIGIBLE":
            rag_without_runtime += 1

    db_eligible = (
        db.query(models.KnowledgeUnit)
        .filter(models.KnowledgeUnit.runtime_eligibility == "ELIGIBLE")
        .count()
    )

    rag_eligible = 0
    for ku in db.query(models.KnowledgeUnit).all():
        if ku_rag_eligible_from_db(db, ku):
            rag_eligible += 1

    if not rag_activated and not kce_rows:
        indexed_count: str | int = "NOT_APPLICABLE / NOT_ACTIVATED"
    else:
        indexed_count = indexed

    return RagCoherenceReport(
        orphan_rag_record=orphan,
        rag_record_without_db_authority=no_auth,
        rag_record_without_provenance=no_prov,
        retracted_rag_runtime_eligible=retracted_eligible,
        superseded_rag_runtime_eligible=superseded_eligible,
        rights_blocked_rag_eligible=rights_blocked_eligible,
        rag_eligible_without_runtime_eligible_db=rag_without_runtime,
        rag_db_identity_mismatch=identity_mismatch,
        db_eligible_count=db_eligible,
        rag_eligible_count=rag_eligible,
        rag_indexed_count=indexed_count,
        rag_stale_count=stale,
        rag_invalidated_count=invalidated,
        rag_activated=rag_activated,
        production_rag_applied=prod_applied,
        computation_basis="DB_DERIVED",
    )

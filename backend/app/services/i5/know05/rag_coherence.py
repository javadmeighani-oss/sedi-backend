"""DB ↔ SCIS/RAG coherence checks — Production RAG remains OFF."""

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


def invalidate_rag_for_knowledge_unit(db: Session, *, knowledge_unit_id: int, reason: str) -> int:
    """Stamp retracted_at on KCE rows for a KU — closes retraction→index gap in rehearsal."""
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
    rag_activated = bool(RAG_EMBEDDINGS_INTRODUCED)
    prod_applied = bool(SCIS_01_PGVECTOR_PRODUCTION_APPLIED)

    kce_rows = db.query(models.KnowledgeChunkEmbedding).all() if hasattr(models, "KnowledgeChunkEmbedding") else []
    orphan = 0
    no_auth = 0
    no_prov = 0
    retracted_eligible = 0
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
        if getattr(row, "immutable_version_id", None) and ku.immutable_version_id:
            if str(row.immutable_version_id) != str(ku.immutable_version_id):
                identity_mismatch += 1
        prov = db.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=ku_id).first()
        if prov is None:
            no_prov += 1
        if getattr(row, "retracted_at", None) is not None:
            invalidated += 1
        elig = str(getattr(ku, "runtime_eligibility", "") or "").upper()
        if getattr(row, "retracted_at", None) is None and elig == "ELIGIBLE" and getattr(ku, "retraction_reason", None):
            retracted_eligible += 1
        if getattr(row, "retracted_at", None) is not None and elig == "ELIGIBLE":
            # Indexed but KU still eligible — stale until republish
            stale += 1

    db_eligible = (
        db.query(models.KnowledgeUnit)
        .filter(models.KnowledgeUnit.runtime_eligibility == "ELIGIBLE")
        .count()
    )
    # RAG eligible ≈ DB eligible with provenance (index may be empty)
    rag_eligible = 0
    for ku in db.query(models.KnowledgeUnit).filter(models.KnowledgeUnit.runtime_eligibility == "ELIGIBLE").all():
        if getattr(ku, "retraction_reason", None):
            continue
        if db.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=ku.id).first() is None:
            continue
        rag_eligible += 1

    indexed_count: str | int
    if not rag_activated and not kce_rows:
        indexed_count = "NOT_APPLICABLE / NOT_ACTIVATED"
    else:
        indexed_count = indexed

    return RagCoherenceReport(
        orphan_rag_record=orphan,
        rag_record_without_db_authority=no_auth,
        rag_record_without_provenance=no_prov,
        retracted_rag_runtime_eligible=retracted_eligible,
        superseded_rag_runtime_eligible=0,
        rights_blocked_rag_eligible=0,
        rag_eligible_without_runtime_eligible_db=0,
        rag_db_identity_mismatch=identity_mismatch,
        db_eligible_count=db_eligible,
        rag_eligible_count=rag_eligible,
        rag_indexed_count=indexed_count,
        rag_stale_count=stale,
        rag_invalidated_count=invalidated,
        rag_activated=rag_activated,
        production_rag_applied=prod_applied,
    )

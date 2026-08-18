"""Bridge eligible governed KU rows into lexical/FTS KCE without vector generation."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import KnowledgeUnitRuntimeEligibility
from backend.app.services.i5.runtime_eligibility_gate import evaluate_knowledge_unit_eligibility
from backend.app.services.scis.lexical_indexing import index_knowledge_unit_lexical_only


def index_eligible_knowledge_unit_if_ready(
    db: Session,
    ku: models.KnowledgeUnit,
    *,
    source_profile_id: Optional[int] = None,
    raw_evidence_id: Optional[int] = None,
) -> List[models.KnowledgeChunkEmbedding]:
    """Index KU into lexical-searchable KCE when runtime eligibility gate passes."""
    gate = evaluate_knowledge_unit_eligibility(ku)
    if gate != KnowledgeUnitRuntimeEligibility.ELIGIBLE:
        return []
    if ku.runtime_eligibility != KnowledgeUnitRuntimeEligibility.ELIGIBLE.value:
        return []
    existing = (
        db.query(models.KnowledgeChunkEmbedding)
        .filter(models.KnowledgeChunkEmbedding.knowledge_unit_id == int(ku.id))
        .count()
    )
    if existing > 0:
        return list(
            db.query(models.KnowledgeChunkEmbedding)
            .filter(models.KnowledgeChunkEmbedding.knowledge_unit_id == int(ku.id))
            .all()
        )
    return index_knowledge_unit_lexical_only(
        db,
        ku,
        source_profile_id=source_profile_id,
        raw_evidence_id=raw_evidence_id,
    )

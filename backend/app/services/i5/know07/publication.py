"""Governed evidence-aware SCIS publication seam (eligible KU → publishable item → index)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Union

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.know07 import GLOBAL_GOVERNED_KNOWLEDGE_LABEL
from backend.app.services.i5.know07.exclusions import hard_exclude_ku
from backend.app.services.scis.serving_bridge import index_eligible_knowledge_unit_if_ready


@dataclass(frozen=True)
class ScisPublishableItem:
    """Structured metadata retained with SCIS-publishable governed evidence."""

    knowledge_unit_id: Optional[int]
    canonical_unit_id: str
    immutable_version_id: str
    domain: str
    manifest_entity_id: Optional[str]
    disease_or_health_condition: Optional[str]
    knowledge_type: str
    evidence_strength: str
    directness: Optional[str]
    population: Optional[str]
    applicability: Optional[str]
    freshness_state: str
    publication_state: str
    conflict_state: str
    retraction_reason: Optional[str]
    provenance_complete: bool
    source_profile_id: Optional[int]
    raw_evidence_id: Optional[int]
    source_attribution: Optional[str]
    citation: Optional[str]
    label: str = GLOBAL_GOVERNED_KNOWLEDGE_LABEL
    extras: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = {
            "knowledge_unit_id": self.knowledge_unit_id,
            "canonical_unit_id": self.canonical_unit_id,
            "immutable_version_id": self.immutable_version_id,
            "domain": self.domain,
            "manifest_entity_id": self.manifest_entity_id,
            "disease_or_health_condition": self.disease_or_health_condition,
            "knowledge_type": self.knowledge_type,
            "evidence_strength": self.evidence_strength,
            "directness": self.directness,
            "population": self.population,
            "applicability": self.applicability,
            "freshness_state": self.freshness_state,
            "publication_state": self.publication_state,
            "conflict_state": self.conflict_state,
            "retraction_reason": self.retraction_reason,
            "provenance_complete": self.provenance_complete,
            "source_profile_id": self.source_profile_id,
            "raw_evidence_id": self.raw_evidence_id,
            "source_attribution": self.source_attribution,
            "citation": self.citation,
            "label": self.label,
        }
        d.update(dict(self.extras))
        return d


def _g(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def build_publishable_item(
    ku: Any,
    *,
    source_profile_id: Optional[int] = None,
    raw_evidence_id: Optional[int] = None,
    source_attribution: Optional[str] = None,
    citation: Optional[str] = None,
    directness: Optional[str] = None,
) -> ScisPublishableItem:
    excl = hard_exclude_ku(ku)
    if excl.excluded:
        raise ValueError(f"NOT_PUBLISHABLE:{excl.code}:{excl.reason}")
    return ScisPublishableItem(
        knowledge_unit_id=_g(ku, "id"),
        canonical_unit_id=str(_g(ku, "canonical_unit_id") or ""),
        immutable_version_id=str(_g(ku, "immutable_version_id") or ""),
        domain=str(_g(ku, "domain") or ""),
        manifest_entity_id=_g(ku, "manifest_entity_id"),
        disease_or_health_condition=_g(ku, "disease_or_health_condition"),
        knowledge_type=str(_g(ku, "knowledge_type") or ""),
        evidence_strength=str(_g(ku, "evidence_strength") or ""),
        directness=directness,
        population=_g(ku, "population"),
        applicability=_g(ku, "applicability"),
        freshness_state=str(_g(ku, "freshness_state") or ""),
        publication_state=str(_g(ku, "publication_state") or ""),
        conflict_state=str(_g(ku, "conflict_state") or ""),
        retraction_reason=_g(ku, "retraction_reason"),
        provenance_complete=bool(_g(ku, "provenance_complete")),
        source_profile_id=source_profile_id,
        raw_evidence_id=raw_evidence_id,
        source_attribution=source_attribution,
        citation=citation or f"ku:{_g(ku, 'canonical_unit_id')}:{_g(ku, 'immutable_version_id')}",
    )


def publish_eligible_ku_to_scis(
    db: Session,
    ku: models.KnowledgeUnit,
    *,
    source_profile_id: Optional[int] = None,
    raw_evidence_id: Optional[int] = None,
    source_attribution: Optional[str] = None,
) -> List[models.KnowledgeChunkEmbedding]:
    """Eligible-only publication into existing lexical KCE path."""
    item = build_publishable_item(
        ku,
        source_profile_id=source_profile_id,
        raw_evidence_id=raw_evidence_id,
        source_attribution=source_attribution,
    )
    assert item.label == GLOBAL_GOVERNED_KNOWLEDGE_LABEL
    # No personal user fields may be attached to global publication.
    forbidden_keys = {"user_id", "user_memory", "personal_fact", "patient_id"}
    if forbidden_keys.intersection(item.as_dict()):
        raise ValueError("PERSONAL_DATA_IN_GLOBAL_PUBLICATION_FORBIDDEN")
    return index_eligible_knowledge_unit_if_ready(
        db,
        ku,
        source_profile_id=source_profile_id,
        raw_evidence_id=raw_evidence_id,
    )

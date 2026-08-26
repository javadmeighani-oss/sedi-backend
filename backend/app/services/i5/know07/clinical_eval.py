"""Deterministic clinical eval harness for KNOW-07 (ALS/MS + D01–D19 representative)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Sequence

from backend.app.services.i5.enums import (
    ConflictState,
    EvidenceStrength,
    FreshnessState,
    KnowledgeUnitRuntimeEligibility,
    MedicalSafetyState,
    PublicationState,
)
from backend.app.services.i5.know07.conflict import collapse_forbidden, label_evidence_relation
from backend.app.services.i5.know07.evidence_bundle import (
    EvidenceBundle,
    build_evidence_bundle_from_scis,
)
from backend.app.services.i5.know07.exclusions import hard_exclude_ku
from backend.app.services.i5.know07.living_knowledge import resolve_living_knowledge_action
from backend.app.services.i5.know07.publication import build_publishable_item
from backend.app.services.scis.contracts import (
    FallbackState,
    ProvenanceRef,
    ScisEvidenceItem,
    ScisRetrievalResponse,
)


def _eligible_ku(**overrides) -> dict[str, Any]:
    base = {
        "id": 1,
        "canonical_unit_id": "ku-demo",
        "immutable_version_id": "v1",
        "domain": "neurology",
        "manifest_entity_id": "D18",
        "disease_or_health_condition": "ALS",
        "knowledge_type": "FACT",
        "evidence_strength": EvidenceStrength.MODERATE.value,
        "population": "adults",
        "applicability": "general",
        "freshness_state": FreshnessState.CURRENT.value,
        "publication_state": PublicationState.PUBLISHED.value,
        "conflict_state": ConflictState.NONE.value,
        "medical_safety_state": MedicalSafetyState.CLEARED.value,
        "retraction_reason": None,
        "runtime_eligibility": KnowledgeUnitRuntimeEligibility.ELIGIBLE.value,
        "provenance_complete": True,
    }
    base.update(overrides)
    return base


@dataclass(frozen=True)
class SuiteCase:
    case_id: str
    description: str
    run: Callable[[], None]


def _fake_scis_item(*, ku_id: int, content: str, meta: dict[str, Any]) -> ScisEvidenceItem:
    return ScisEvidenceItem(
        label="GLOBAL_GOVERNED_KNOWLEDGE",
        chunk_id=ku_id * 10,
        content=content,
        language="en",
        knowledge_unit_id=ku_id,
        immutable_version_id="v1",
        retrieval_branch="lexical",
        lexical_rank=1,
        vector_rank=None,
        fusion_rank=1,
        fusion_score=1.0,
        runtime_eligibility=meta.get("runtime_eligibility", "ELIGIBLE"),
        embedding_model="scis-lexical-fts-v1",
        embedding_version=None,
        provenance=ProvenanceRef(
            chunk_id=ku_id * 10,
            knowledge_unit_id=ku_id,
            immutable_version_id="v1",
            raw_evidence_id=100 + ku_id,
            source_profile_id=5,
        ),
        metadata=meta,
    )


def _bundle_for(items: List[ScisEvidenceItem], query: str = "q") -> EvidenceBundle:
    resp = ScisRetrievalResponse(
        request_trace_id="eval",
        mode="lexical",
        language="en",
        evidence=items,
        fallback_state=FallbackState.NONE,
    )
    return build_evidence_bundle_from_scis(resp, query=query, intent="clinical_eval")


def suite_valid_current() -> None:
    ku = _eligible_ku()
    assert hard_exclude_ku(ku).excluded is False
    item = build_publishable_item(ku, source_profile_id=1, raw_evidence_id=2, source_attribution="MedlinePlus")
    assert item.label == "GLOBAL_GOVERNED_KNOWLEDGE"
    assert item.provenance_complete is True


def suite_ineligible() -> None:
    ku = _eligible_ku(runtime_eligibility="NOT_ELIGIBLE", evidence_strength="UNKNOWN", provenance_complete=False)
    d = hard_exclude_ku(ku)
    assert d.excluded and d.code in {"INELIGIBLE", "MISSING_PROVENANCE"}


def suite_retracted() -> None:
    ku = _eligible_ku(retraction_reason="RETRACTED_BY_JOURNAL")
    d = hard_exclude_ku(ku)
    assert d.code == "RETRACTED"
    # Bundle must drop retracted even if SCIS returned it.
    meta = {
        "ku_provenance_complete": True,
        "ku_evidence_strength": "HIGH",
        "ku_freshness_state": "CURRENT",
        "ku_conflict_state": "NONE",
        "ku_medical_safety_state": "CLEARED",
        "ku_publication_state": "PUBLISHED",
        "ku_retraction_reason": "RETRACTED_BY_JOURNAL",
        "runtime_eligibility": "ELIGIBLE",
    }
    b = _bundle_for([_fake_scis_item(ku_id=9, content="retracted claim", meta=meta)])
    assert b.items == []
    assert b.filtered_counts.get("RETRACTED", 0) >= 1


def suite_superseded() -> None:
    ku = _eligible_ku(publication_state=PublicationState.SUPERSEDED.value)
    assert hard_exclude_ku(ku).code == "SUPERSEDED"


def suite_stale() -> None:
    ku = _eligible_ku(freshness_state=FreshnessState.STALE.value)
    assert hard_exclude_ku(ku).code == "STALE"


def suite_conflicting_and_negative() -> None:
    a = label_evidence_relation(
        support_direction="SUPPORTS",
        conflict_group={"disease": "MS", "intervention": "DMT", "outcome": "relapse"},
    )
    b = label_evidence_relation(
        support_direction="CONTRADICTS",
        conflict_group={"disease": "MS", "intervention": "DMT", "outcome": "relapse"},
    )
    c = label_evidence_relation(support_direction="REFUTES")
    d = label_evidence_relation(support_direction="INCONCLUSIVE")
    assert {a.support_direction, b.support_direction, c.support_direction, d.support_direction} == {
        "SUPPORTS",
        "CONTRADICTS",
        "REFUTES",
        "INCONCLUSIVE",
    }
    collapse_forbidden([a, b])


def suite_missing_provenance_and_citation() -> None:
    ku = _eligible_ku(provenance_complete=False)
    assert hard_exclude_ku(ku).code == "MISSING_PROVENANCE"
    meta = {
        "ku_provenance_complete": True,
        "ku_evidence_strength": "MODERATE",
        "ku_freshness_state": "CURRENT",
        "ku_conflict_state": "NONE",
        "ku_medical_safety_state": "CLEARED",
        "ku_publication_state": "PUBLISHED",
        "runtime_eligibility": "ELIGIBLE",
    }
    orphan = _fake_scis_item(ku_id=3, content="x", meta=meta)
    orphan.provenance = ProvenanceRef(
        chunk_id=1,
        knowledge_unit_id=None,
        immutable_version_id=None,
        raw_evidence_id=None,
        source_profile_id=None,
    )
    orphan.knowledge_unit_id = None
    orphan.immutable_version_id = None
    b = _bundle_for([orphan])
    assert b.items == []
    assert b.filtered_counts.get("citation_integrity_fail", 0) >= 1


def suite_uncertainty_safety_wording() -> None:
    meta = {
        "ku_provenance_complete": True,
        "ku_evidence_strength": "MODERATE",
        "ku_freshness_state": "CURRENT",
        "ku_conflict_state": "NONE",
        "ku_medical_safety_state": "CLEARED",
        "ku_publication_state": "PUBLISHED",
        "runtime_eligibility": "ELIGIBLE",
        "source_attribution": "NINDS",
    }
    b = _bundle_for([_fake_scis_item(ku_id=1, content="ALS supportive care evidence", meta=meta)], query="ALS care")
    assert len(b.items) == 1
    assert "not a diagnosis" in b.items[0].uncertainty_safety["wording"].lower()
    assert b.knowledge_plane == "GLOBAL_GOVERNED_KNOWLEDGE"
    assert b.uncertainty_safety["personal_memory_mixed"] is False


def suite_living_knowledge_events() -> None:
    for ev in (
        "NEW_PUBLICATION",
        "GUIDELINE_EDITION",
        "CORRECTION",
        "EXPRESSION_OF_CONCERN",
        "RETRACTION",
        "DRUG_APPROVAL_SAFETY_CHANGE",
        "TRIAL_STATUS_CHANGE",
        "GUIDELINE_SUPERSESSION",
    ):
        action = resolve_living_knowledge_action(ev)
        assert action.affects_eligibility is True or ev == "NEW_PUBLICATION"
        if ev in {"RETRACTION", "GUIDELINE_SUPERSESSION", "CORRECTION"}:
            assert action.invalidates_scis_index is True


ALS_SUITE: Sequence[SuiteCase] = (
    SuiteCase("ALS_VALID", "valid current ALS evidence publishable", suite_valid_current),
    SuiteCase("ALS_RETRACTED", "retracted ALS evidence excluded", suite_retracted),
    SuiteCase("ALS_UNCERTAINTY", "ALS uncertainty/safety wording", suite_uncertainty_safety_wording),
)

MS_SUITE: Sequence[SuiteCase] = (
    SuiteCase("MS_CONFLICT", "MS conflicting/negative evidence labels", suite_conflicting_and_negative),
    SuiteCase("MS_SUPERSEDED", "superseded MS evidence excluded", suite_superseded),
    SuiteCase("MS_STALE", "stale MS evidence excluded", suite_stale),
)

D01_D19_REPRESENTATIVE: Sequence[SuiteCase] = (
    SuiteCase("DXX_INELIGIBLE", "ineligible evidence hard exclude", suite_ineligible),
    SuiteCase("DXX_PROVENANCE", "missing provenance / citation integrity", suite_missing_provenance_and_citation),
    SuiteCase("DXX_LIVING", "living-knowledge event mapping", suite_living_knowledge_events),
)


def run_suite(cases: Sequence[SuiteCase]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for case in cases:
        case.run()
        out[case.case_id] = "PASS"
    return out


def run_all_clinical_suites() -> Dict[str, Any]:
    return {
        "ALS": run_suite(ALS_SUITE),
        "MS": run_suite(MS_SUITE),
        "D01_D19_REPRESENTATIVE": run_suite(D01_D19_REPRESENTATIVE),
    }

"""I5-KNOW-07 evidence-aware SCIS publication + clinical eval tests (offline)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.i5.know06 import (
    CONTRACT_CLOSED as KNOW06_CONTRACT_CLOSED,
    RUNTIME_IMPLEMENTATION_EXPECTED_IN_I5 as KNOW06_RUNTIME_IN_I5,
)
from backend.app.services.i5.know07 import (
    AUTHORITY_DOCS,
    GLOBAL_GOVERNED_KNOWLEDGE_LABEL,
    LIVING_KNOWLEDGE_EVENTS,
    PURE_VECTOR_ONLY_RAG_ALLOWED,
    SUPPORT_DIRECTIONS,
)
from backend.app.services.i5.know07.clinical_eval import run_all_clinical_suites
from backend.app.services.i5.know07.conflict import (
    collapse_forbidden,
    label_evidence_relation,
    normalize_support_direction,
)
from backend.app.services.i5.know07.evidence_bundle import (
    build_evidence_bundle_from_scis,
    evidence_aware_retrieve,
)
from backend.app.services.i5.know07.exclusions import assert_cannot_reenter, hard_exclude_ku
from backend.app.services.i5.know07.living_knowledge import resolve_living_knowledge_action
from backend.app.services.i5.know07.publication import build_publishable_item
from backend.app.services.scis.contracts import FallbackState, ProvenanceRef, RetrievalMode, ScisEvidenceItem, ScisRetrievalResponse


ROOT = Path(__file__).resolve().parents[2]


def _elig(**kw):
    base = {
        "id": 11,
        "canonical_unit_id": "c1",
        "immutable_version_id": "v1",
        "domain": "neurology",
        "manifest_entity_id": "D18",
        "disease_or_health_condition": "ALS",
        "knowledge_type": "FACT",
        "evidence_strength": "MODERATE",
        "population": "adults",
        "applicability": None,
        "freshness_state": "CURRENT",
        "publication_state": "PUBLISHED",
        "conflict_state": "NONE",
        "medical_safety_state": "CLEARED",
        "retraction_reason": None,
        "runtime_eligibility": "ELIGIBLE",
        "provenance_complete": True,
    }
    base.update(kw)
    return base


def test_authority_docs_and_flags():
    for rel in AUTHORITY_DOCS:
        assert (ROOT / rel).is_file()
    auth = (ROOT / AUTHORITY_DOCS[0]).read_text(encoding="utf-8")
    assert "PURE_VECTOR_ONLY_RAG" in auth
    assert "SUPPORTS/CONTRADICTS/REFUTES/INCONCLUSIVE" in auth
    assert PURE_VECTOR_ONLY_RAG_ALLOWED is False
    assert GLOBAL_GOVERNED_KNOWLEDGE_LABEL == "GLOBAL_GOVERNED_KNOWLEDGE"


def test_publication_path_eligible_only_no_personal_data():
    item = build_publishable_item(
        _elig(), source_profile_id=1, raw_evidence_id=2, source_attribution="NINDS", citation="ninds:als"
    )
    d = item.as_dict()
    assert d["label"] == GLOBAL_GOVERNED_KNOWLEDGE_LABEL
    assert d["provenance_complete"] is True
    assert "user_id" not in d
    with pytest.raises(ValueError, match="NOT_PUBLISHABLE"):
        build_publishable_item(_elig(retraction_reason="x"))


def test_hard_exclusions_and_reentry_forbidden():
    assert hard_exclude_ku(_elig()).excluded is False
    for ku, code in (
        (_elig(runtime_eligibility="NOT_ELIGIBLE", evidence_strength="UNKNOWN", provenance_complete=False), "MISSING_PROVENANCE"),
        (_elig(retraction_reason="RETRACTED"), "RETRACTED"),
        (_elig(publication_state="SUPERSEDED"), "SUPERSEDED"),
        (_elig(freshness_state="STALE"), "STALE"),
        (_elig(medical_safety_state="BLOCKED"), "UNSAFE_BLOCKED"),
    ):
        d = hard_exclude_ku(ku)
        assert d.excluded and d.code == code
        with pytest.raises(ValueError, match="EXCLUSION_REENTRY_FORBIDDEN"):
            assert_cannot_reenter(branch="lexical", exclusion=d)
        with pytest.raises(ValueError, match="EXCLUSION_REENTRY_FORBIDDEN"):
            assert_cannot_reenter(branch="vector", exclusion=d)
        with pytest.raises(ValueError, match="EXCLUSION_REENTRY_FORBIDDEN"):
            assert_cannot_reenter(branch="fallback", exclusion=d)
    assert hard_exclude_ku(_elig(), retracted_at="2026-01-01").code == "RETRACTED"


def test_support_directions_and_no_false_consensus():
    assert SUPPORT_DIRECTIONS == {"SUPPORTS", "CONTRADICTS", "REFUTES", "INCONCLUSIVE"}
    assert normalize_support_direction("weakly_supports") == "SUPPORTS"
    a = label_evidence_relation(support_direction="SUPPORTS", conflict_group={"disease": "MS"})
    b = label_evidence_relation(support_direction="CONTRADICTS", conflict_group={"disease": "MS"})
    collapse_forbidden([a, b])
    assert label_evidence_relation(support_direction="REFUTES").support_direction == "REFUTES"
    assert label_evidence_relation(support_direction="INCONCLUSIVE").support_direction == "INCONCLUSIVE"


def test_evidence_bundle_contract_and_pure_vector_forbidden():
    meta = {
        "ku_provenance_complete": True,
        "ku_evidence_strength": "HIGH",
        "ku_freshness_state": "CURRENT",
        "ku_conflict_state": "NONE",
        "ku_medical_safety_state": "CLEARED",
        "ku_publication_state": "PUBLISHED",
        "runtime_eligibility": "ELIGIBLE",
        "source_attribution": "MedlinePlus",
        "support_direction": "SUPPORTS",
    }
    ev = ScisEvidenceItem(
        label=GLOBAL_GOVERNED_KNOWLEDGE_LABEL,
        chunk_id=1,
        content="MS disease-modifying therapy evidence",
        language="en",
        knowledge_unit_id=42,
        immutable_version_id="v1",
        retrieval_branch="lexical",
        lexical_rank=1,
        vector_rank=None,
        fusion_rank=1,
        fusion_score=1.0,
        runtime_eligibility="ELIGIBLE",
        embedding_model="scis-lexical-fts-v1",
        embedding_version=None,
        provenance=ProvenanceRef(1, 42, "v1", 9, 3),
        metadata=meta,
    )
    bundle = build_evidence_bundle_from_scis(
        ScisRetrievalResponse("t", "lexical", "en", [ev], FallbackState.NONE),
        query="MS DMT",
        intent="clinical",
        domain="neurology",
    )
    assert bundle.knowledge_plane == GLOBAL_GOVERNED_KNOWLEDGE_LABEL
    assert len(bundle.items) == 1
    assert bundle.items[0].source_attribution == "MedlinePlus"
    assert bundle.items[0].citation
    assert bundle.uncertainty_safety["pure_vector_only_rag"] is False
    assert bundle.uncertainty_safety["personal_memory_mixed"] is False

    class _DB:
        pass

    with pytest.raises(ValueError, match="PURE_VECTOR_ONLY_RAG_FORBIDDEN"):
        evidence_aware_retrieve(_DB(), query="x", retrieval_mode=RetrievalMode.VECTOR)


def test_living_knowledge_invalidation_mapping():
    assert LIVING_KNOWLEDGE_EVENTS
    ret = resolve_living_knowledge_action("RETRACTION")
    assert ret.invalidates_scis_index is True
    assert ret.set_retraction_reason == "RETRACTION"
    sup = resolve_living_knowledge_action("GUIDELINE_SUPERSESSION")
    assert sup.target_publication_state == "SUPERSEDED"


def test_clinical_suites_als_ms_d01_d19():
    results = run_all_clinical_suites()
    assert all(v == "PASS" for v in results["ALS"].values())
    assert all(v == "PASS" for v in results["MS"].values())
    assert all(v == "PASS" for v in results["D01_D19_REPRESENTATIVE"].values())


def test_know06_boundary_regression():
    assert KNOW06_CONTRACT_CLOSED is True
    assert KNOW06_RUNTIME_IN_I5 is False


def test_d01_d19_manifest_and_weekly_regression():
    manifest = (ROOT / "backend/config/i5/coverage_manifest_v1.yaml").read_text(encoding="utf-8")
    assert "D01" in manifest and "D19" in manifest
    from backend.app.services.i5.governed_weekly_runtime import (
        WEEKLY_CRON_DAY_OF_WEEK,
        WEEKLY_CRON_HOUR,
        WEEKLY_CRON_MINUTE,
        WEEKLY_SCHEDULER_TIMEZONE_NAME,
    )

    assert WEEKLY_SCHEDULER_TIMEZONE_NAME == "Asia/Tehran"
    assert (WEEKLY_CRON_DAY_OF_WEEK, WEEKLY_CRON_HOUR, WEEKLY_CRON_MINUTE) == ("fri", 3, 30)


def test_scis_retrieval_metadata_enrichment_fields_present():
    src = (ROOT / "backend/app/services/scis/retrieval.py").read_text(encoding="utf-8")
    assert "ku_freshness_state" in src
    assert "ku_retraction_reason" in src

"""I5 final readiness — answer path + ungrounded protection (offline)."""

from __future__ import annotations

from backend.app.services.i5.know07.answer_path import (
    assert_ungrounded_blocked,
    bundle_to_retrieval_payload,
)
from backend.app.services.i5.know07.clinical_eval import run_all_clinical_suites
from backend.app.services.i5.know07.conflict import collapse_forbidden, label_evidence_relation
from backend.app.services.i5.know07.evidence_bundle import EvidenceBundle, EvidenceBundleItem
from backend.app.services.i5.know07.living_knowledge import resolve_living_knowledge_action
from backend.app.services.i5.reference_renderer import render_grounded_answer


def test_answer_path_bundle_to_grounded_synthesis():
    item = EvidenceBundleItem(
        label="GLOBAL_GOVERNED_KNOWLEDGE",
        knowledge_unit_id=42,
        content="ALS supportive care improves quality of life.",
        evidence_strength="MODERATE",
        evidence_type="FACT",
        freshness_state="CURRENT",
        publication_state="PUBLISHED",
        conflict_state="NONE",
        support_direction="SUPPORTS",
        eligibility_state="ELIGIBLE",
        provenance={
            "chunk_id": 1,
            "knowledge_unit_id": 42,
            "immutable_version_id": "v1",
            "raw_evidence_id": 9,
            "source_profile_id": 3,
        },
        source_attribution="NINDS",
        citation="ku:42:v1",
        uncertainty_safety={
            "medical_safety_state": "CLEARED",
            "wording": "Governed evidence only; not a diagnosis or prescription.",
        },
    )
    bundle = EvidenceBundle(
        query="ALS care",
        intent="clinical",
        domain="neurology",
        knowledge_plane="GLOBAL_GOVERNED_KNOWLEDGE",
        items=[item],
        filtered_counts={},
        retrieval_mode="lexical",
        fallback_state="none",
        uncertainty_safety={"no_ungrounded_serving": True, "pure_vector_only_rag": False, "personal_memory_mixed": False},
    )
    payload = bundle_to_retrieval_payload(bundle)
    answer = render_grounded_answer(payload, user_requested_sources=True)
    assert answer.no_base_model_fallback is True
    assert answer.synthesized_text
    assert answer.references
    assert answer.show_sources


def test_ungrounded_and_living_and_conflict():
    assert assert_ungrounded_blocked(
        {
            "provenance_complete": True,
            "evidence_strength": "HIGH",
            "freshness_state": "CURRENT",
            "conflict_state": "NONE",
            "medical_safety_state": "CLEARED",
            "publication_state": "PUBLISHED",
            "retraction_reason": "x",
            "runtime_eligibility": "ELIGIBLE",
        }
    ) == "RETRACTED"
    assert resolve_living_knowledge_action("RETRACTION").invalidates_scis_index
    assert resolve_living_knowledge_action("GUIDELINE_SUPERSESSION").target_publication_state == "SUPERSEDED"
    a = label_evidence_relation(support_direction="SUPPORTS")
    b = label_evidence_relation(support_direction="REFUTES")
    collapse_forbidden([a, b])
    results = run_all_clinical_suites()
    assert all(v == "PASS" for v in results["ALS"].values())

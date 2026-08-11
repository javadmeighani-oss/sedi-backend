"""I5-KNOW-05 deterministic extensions — NF18/NF20/NF21 + availability negatives."""

from __future__ import annotations

from backend.app.services.i5.know05.authority_audit import audit_knowledge_authority, compute_duplicate_authority
from backend.app.services.i5.know05.availability import derive_ku_availability
from backend.app.services.i5.know05.coverage_engine import CoveragePrioritizationItem
from backend.app.services.i5.know05.source_selection import select_connectors_for_gap
from backend.app.services.i5.know05.storage_matrix import matrices_summary


def test_nf21_authority_audit_derived_duplicate_zero():
    report = audit_knowledge_authority(db=None)
    assert report.computation_basis.startswith("ORM_INTROSPECTION")
    assert report.classified_count >= 40
    assert report.duplicate_knowledge_authority == 0
    assert report.duplicate_findings == []
    count, findings = compute_duplicate_authority(
        {r.table_name for r in report.rows if r.present_in_orm}
        | {"knowledge_units", "governed_source_profiles", "knowledge_chunk_embeddings", "knowledge_sources"}
    )
    assert count == 0
    assert findings == []
    s = matrices_summary()
    assert s["duplicate_knowledge_authority"] == 0
    assert s["authority_rows"] >= 40


def test_nf18_availability_superseded_withdrawn_rights_block():
    for pub in ("SUPERSEDED", "WITHDRAWN"):
        v = derive_ku_availability(
            ku_id=10,
            runtime_eligibility="ELIGIBLE",
            retraction_reason=None,
            freshness_state="CURRENT",
            provenance_complete=True,
            publication_state=pub,
            rights_state="RIGHTS_ALLOWED",
        )
        assert v.runtime_eligible is False
        assert v.rag_eligible is False

    blocked = derive_ku_availability(
        ku_id=11,
        runtime_eligibility="ELIGIBLE",
        retraction_reason=None,
        freshness_state="CURRENT",
        provenance_complete=True,
        publication_state="PUBLISHED",
        rights_state="RIGHTS_BLOCKED",
    )
    assert blocked.runtime_eligible is False
    assert blocked.rag_eligible is False
    assert "BLOCKED_RIGHTS" in blocked.states

    missing_prov = derive_ku_availability(
        ku_id=12,
        runtime_eligibility="ELIGIBLE",
        retraction_reason=None,
        freshness_state="CURRENT",
        provenance_complete=False,
        rights_state="RIGHTS_ALLOWED",
    )
    assert missing_prov.rag_eligible is False
    assert missing_prov.runtime_eligible is False


def test_nf20_source_selection_p0_and_non_p0_registry_fail_closed():
    """Without Registry rows, selection must fail closed (no hardcoded WHO/PubMed/CT.gov)."""

    class _FakeDB:
        def query(self, *_a, **_k):
            class _Q:
                def filter_by(self, **_kw):
                    return self

                def join(self, *a, **k):
                    return self

                def filter(self, *a, **k):
                    return self

                def first(self):
                    return None

                def all(self):
                    return []

            return _Q()

    items = [
        CoveragePrioritizationItem(
            cell_id=1,
            concept_id=1,
            dimension_code="PHARMACOLOGICAL_TREATMENT",
            evidence_class="GUIDELINE",
            cell_state="MISSING",
            priority="P0",
            p0_overlay=True,
            gap_key="als-guideline",
        ),
        CoveragePrioritizationItem(
            cell_id=2,
            concept_id=2,
            dimension_code="CLINICAL_TRIALS",
            evidence_class="CLINICAL_TRIALS",
            cell_state="MISSING",
            priority="P0",
            p0_overlay=True,
            gap_key="ms-trials",
        ),
        CoveragePrioritizationItem(
            cell_id=3,
            concept_id=3,
            dimension_code="DIAGNOSIS",
            evidence_class="SCIENTIFIC_STUDY",
            cell_state="PARTIAL",
            priority="P0",
            p0_overlay=True,
            gap_key="dm-lit",
        ),
        CoveragePrioritizationItem(
            cell_id=4,
            concept_id=4,
            dimension_code="PREVENTION",
            evidence_class="GUIDELINE",
            cell_state="MISSING",
            priority="P1",
            p0_overlay=False,
            gap_key="htn-guideline",
        ),
    ]
    from backend.app.services.i5.know05.source_selection import NO_ELIGIBLE_GOVERNED_SOURCE

    db = _FakeDB()
    sels = []
    for it in items:
        sels.extend(select_connectors_for_gap(db, it))
    assert any(s.gap_key == "als-guideline" and s.connector_key == NO_ELIGIBLE_GOVERNED_SOURCE for s in sels)
    assert any(s.gap_key == "ms-trials" and s.connector_key == NO_ELIGIBLE_GOVERNED_SOURCE for s in sels)
    assert any(s.gap_key == "dm-lit" and s.connector_key == NO_ELIGIBLE_GOVERNED_SOURCE for s in sels)
    assert any(s.gap_key == "htn-guideline" and s.p0_overlay is False for s in sels)
    assert not any(s.connector_key in {
        "who_guideline_catalogue",
        "clinicaltrials_gov_api_v2",
        "pubmed_ncbi_eutils",
        "pubmed_central",
    } for s in sels)
    for s in sels:
        assert s.automation_decision == "BLOCKED"
        assert s.block_reason

"""Static knowledge storage / availability matrices for KNOW-05 Evidence Pack (no migration)."""

from __future__ import annotations

from typing import Any

# Authority class: CANONICAL | SUPPORTING | INDEX | AUDIT | CACHE | LEGACY/DEPRECATED | NOT_RUNTIME_AUTHORITY

KNOWLEDGE_AUTHORITY_MATRIX: list[dict[str, str]] = [
    {"structure": "governed_source_profiles", "class": "CANONICAL"},
    {"structure": "i5_scientific_artifacts", "class": "CANONICAL"},
    {"structure": "i5_scientific_artifact_versions", "class": "CANONICAL"},
    {"structure": "knowledge_units", "class": "CANONICAL"},
    {"structure": "knowledge_provenance", "class": "CANONICAL"},
    {"structure": "i5_knowledge_unit_evidence_links", "class": "CANONICAL"},
    {"structure": "i5_knowledge_claim_details", "class": "CANONICAL"},
    {"structure": "knowledge_memory_items", "class": "CANONICAL"},
    {"structure": "knowledge_gaps", "class": "CANONICAL"},
    {"structure": "i5_clinical_studies", "class": "CANONICAL"},
    {"structure": "i5_study_effect_estimates", "class": "CANONICAL"},
    {"structure": "i5_clinical_recommendations", "class": "CANONICAL"},
    {"structure": "i5_knowledge_coverage_cells", "class": "CANONICAL"},
    {"structure": "i5_clinical_concepts", "class": "CANONICAL"},
    {"structure": "weekly_knowledge_runs", "class": "AUDIT"},
    {"structure": "i5_connector_profiles", "class": "SUPPORTING"},
    {"structure": "i5_scientific_change_events", "class": "AUDIT"},
    {"structure": "knowledge_chunk_embeddings", "class": "INDEX"},
    {"structure": "knowledge_sources", "class": "LEGACY/DEPRECATED"},
    {"structure": "iran_doctors", "class": "NOT_RUNTIME_AUTHORITY"},
]

KNOWLEDGE_STORAGE_MATRIX: list[dict[str, str]] = [
    {
        "object": "SOURCE",
        "canonical_table": "governed_source_profiles",
        "versioned": "YES (governed_source_profile_versions)",
        "provenance": "YES",
        "rights": "YES",
        "freshness": "YES",
        "governance": "YES",
        "runtime_eligible": "via runtime_eligibility",
        "structured_query": "YES",
        "scis_rag_eligible": "GATE_ONLY",
        "invalidation_path": "governance/registry_state",
    },
    {
        "object": "ARTIFACT",
        "canonical_table": "i5_scientific_artifacts",
        "versioned": "YES (i5_scientific_artifact_versions)",
        "provenance": "YES",
        "rights": "via source + ingestion audit",
        "freshness": "published_at/version_state",
        "governance": "change events",
        "runtime_eligible": "version_state filters",
        "structured_query": "YES",
        "scis_rag_eligible": "INDIRECT_VIA_KU",
        "invalidation_path": "apply_artifact_change",
    },
    {
        "object": "KNOWLEDGE_UNIT",
        "canonical_table": "knowledge_units",
        "versioned": "immutable_version_id",
        "provenance": "knowledge_provenance 1:1",
        "rights": "via provenance/source",
        "freshness": "freshness_state",
        "governance": "eligibility + safety",
        "runtime_eligible": "runtime_eligibility",
        "structured_query": "YES",
        "scis_rag_eligible": "WHEN_ELIGIBLE+PROVENANCE",
        "invalidation_path": "retraction_reason + KCE.retracted_at",
    },
    {
        "object": "STUDY/EFFECT",
        "canonical_table": "i5_clinical_studies / i5_study_effect_estimates",
        "versioned": "NO (append-only estimates)",
        "provenance": "artifact links",
        "rights": "inherited",
        "freshness": "study_status",
        "governance": "change events",
        "runtime_eligible": "via links/KU",
        "structured_query": "YES_SQL",
        "scis_rag_eligible": "STRUCTURED_PRIMARY",
        "invalidation_path": "artifact retraction",
    },
    {
        "object": "RECOMMENDATION",
        "canonical_table": "i5_clinical_recommendations",
        "versioned": "superseded_by_id",
        "provenance": "source_artifact_version_id",
        "rights": "inherited",
        "freshness": "effective_from/until",
        "governance": "status",
        "runtime_eligible": "status+artifact",
        "structured_query": "YES_SQL",
        "scis_rag_eligible": "STRUCTURED_PRIMARY",
        "invalidation_path": "supersede_guideline_recommendation",
    },
    {
        "object": "COVERAGE_CELL",
        "canonical_table": "i5_knowledge_coverage_cells",
        "versioned": "mutable state",
        "provenance": "detail",
        "rights": "N/A",
        "freshness": "freshness_note",
        "governance": "gap generation",
        "runtime_eligible": "NO (planning)",
        "structured_query": "YES",
        "scis_rag_eligible": "NO",
        "invalidation_path": "cell_state update",
    },
    {
        "object": "CHANGE/RETRACTION",
        "canonical_table": "i5_scientific_change_events",
        "versioned": "append-only",
        "provenance": "YES",
        "rights": "connector rights",
        "freshness": "created_at",
        "governance": "drives eligibility",
        "runtime_eligible": "N/A",
        "structured_query": "YES",
        "scis_rag_eligible": "NO",
        "invalidation_path": "propagate to artifact/KU/KCE",
    },
]


WEEKLY_GOVERNANCE_REUSE_MATRIX: list[dict[str, str]] = [
    {"asset": "WeeklyKnowledgeRun/Attempt/SourceResult/GapResult", "disposition": "REUSE"},
    {"asset": "KnowledgeGap + I5GovernanceDecision", "disposition": "REUSE"},
    {"asset": "weekly_orchestrator.py", "disposition": "EXTEND"},
    {"asset": "I5KnowledgeCoverageCell", "disposition": "EXTEND"},
    {"asset": "know04 connectors", "disposition": "REUSE"},
    {"asset": "parallel crawler-run schema", "disposition": "REJECT_REDUNDANT"},
    {"asset": "coverage-cell → KnowledgeGap generator", "disposition": "NEW_REQUIRED"},
    {"asset": "Production weekly activation", "disposition": "DEFER"},
]


def matrices_summary(db=None) -> dict[str, Any]:
    """Combine documentation matrices with NF21 introspected authority audit."""
    from backend.app.services.i5.know05.authority_audit import audit_knowledge_authority

    audit = audit_knowledge_authority(db)
    classes = [r.authority_class for r in audit.rows]
    return {
        "authority_rows": len(audit.rows),
        "storage_rows": len(KNOWLEDGE_STORAGE_MATRIX),
        "weekly_reuse_rows": len(WEEKLY_GOVERNANCE_REUSE_MATRIX),
        "duplicate_knowledge_authority": audit.duplicate_knowledge_authority,
        "duplicate_findings": list(audit.duplicate_findings),
        "canonical_count": classes.count("CANONICAL"),
        "index_count": classes.count("INDEX"),
        "legacy_count": classes.count("LEGACY_DEPRECATED"),
        "unclassified_knowledgeish": list(audit.unclassified_knowledgeish),
        "new_migration": "NO",
        "alembic_head": "065_i5_know04_connectors_change_intelligence",
        "computation_basis": audit.computation_basis,
        "static_doc_matrix_rows": len(KNOWLEDGE_AUTHORITY_MATRIX),
    }

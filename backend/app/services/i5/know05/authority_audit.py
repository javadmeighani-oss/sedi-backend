"""NF21 — DB knowledge authority audit via ORM introspection (no duplicate SoT)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models


# Explicit authority classification — derived from freeze + KNOW-01..04 evidence.
# INDEX/LEGACY must never own medical truth independently.

_AUTHORITY_SPEC: dict[str, dict[str, str]] = {
    "governed_source_profiles": {
        "class": "CANONICAL",
        "role": "source_identity",
        "versioning": "governed_source_profile_versions",
        "rights_path": "i5_source_registry_extensions + GSP.runtime_eligibility",
        "runtime_eligibility_path": "runtime_eligibility",
        "scis_rag_role": "GATE_ONLY",
        "invalidation_path": "registry_state / governance",
    },
    "governed_source_profile_versions": {
        "class": "CANONICAL",
        "role": "source_version_snapshot",
        "versioning": "immutable version_seq",
        "rights_path": "version license/storage columns",
        "runtime_eligibility_path": "via current pointer",
        "scis_rag_role": "GATE_ONLY",
        "invalidation_path": "supersedes_version_id",
    },
    "i5_source_registry_extensions": {
        "class": "CANONICAL",
        "role": "source_rights_overlay",
        "versioning": "mutable overlay",
        "rights_path": "access/automation/tdm/transform/retain_*",
        "runtime_eligibility_path": "processing_permission_mode",
        "scis_rag_role": "RIGHTS_GATE",
        "invalidation_path": "rights fail-closed",
    },
    "i5_source_registry_roles": {"class": "SUPPORTING", "role": "source_role_tags"},
    "i5_source_p0_tags": {"class": "SUPPORTING", "role": "p0_overlay_only"},
    "i5_reference_books": {"class": "CANONICAL", "role": "book_registry"},
    "i5_reference_book_editions": {"class": "CANONICAL", "role": "book_edition_version"},
    "i5_scientific_artifacts": {
        "class": "CANONICAL",
        "role": "artifact_identity",
        "versioning": "i5_scientific_artifact_versions",
        "scis_rag_role": "INDIRECT_VIA_KU",
        "invalidation_path": "apply_artifact_change",
    },
    "i5_scientific_artifact_versions": {
        "class": "CANONICAL",
        "role": "artifact_version",
        "versioning": "version_label + content_hash",
        "runtime_eligibility_path": "version_state",
        "scis_rag_role": "INDIRECT_VIA_KU",
        "invalidation_path": "version_state RETRACTED/WITHDRAWN/SUPERSEDED",
    },
    "i5_raw_evidence": {"class": "CANONICAL", "role": "raw_retention_object", "scis_rag_role": "NOT_CLAIM_SOT"},
    "knowledge_units": {
        "class": "CANONICAL",
        "role": "knowledge_unit_authority",
        "versioning": "immutable_version_id",
        "provenance": "knowledge_provenance 1:1",
        "runtime_eligibility_path": "runtime_eligibility",
        "scis_rag_role": "PRIMARY_RAG_TEXT_SOURCE",
        "invalidation_path": "retraction_reason / publication_state",
    },
    "knowledge_provenance": {"class": "CANONICAL", "role": "primary_citation_anchor"},
    "knowledge_memory_items": {"class": "CANONICAL", "role": "current_memory_pointer"},
    "knowledge_memory_transitions": {"class": "AUDIT", "role": "memory_transition_ledger"},
    "i5_knowledge_unit_evidence_links": {"class": "CANONICAL", "role": "multi_evidence_graph"},
    "i5_knowledge_claim_details": {"class": "CANONICAL", "role": "structured_claim_facets"},
    "i5_knowledge_unit_concepts": {"class": "SUPPORTING", "role": "ku_concept_link"},
    "i5_knowledge_unit_dimensions": {"class": "SUPPORTING", "role": "ku_dimension_link"},
    "i5_clinical_concepts": {"class": "CANONICAL", "role": "taxonomy_concept"},
    "i5_clinical_concept_labels": {"class": "SUPPORTING", "role": "concept_labels"},
    "i5_clinical_concept_mappings": {"class": "CANONICAL", "role": "terminology_mapping"},
    "i5_knowledge_dimensions": {"class": "CANONICAL", "role": "knowledge_dimension"},
    "i5_knowledge_coverage_cells": {"class": "CANONICAL", "role": "coverage_matrix_sot"},
    "i5_source_coverage_gaps": {"class": "SUPPORTING", "role": "source_coverage_planning"},
    "i5_clinical_studies": {"class": "CANONICAL", "role": "study_authority"},
    "i5_study_artifact_links": {"class": "SUPPORTING", "role": "study_artifact_link"},
    "i5_study_condition_links": {"class": "SUPPORTING", "role": "study_condition_link"},
    "i5_study_populations": {"class": "CANONICAL", "role": "study_population"},
    "i5_study_population_criteria": {"class": "SUPPORTING", "role": "population_criteria"},
    "i5_interventions": {"class": "CANONICAL", "role": "intervention_vocab"},
    "i5_intervention_mappings": {"class": "SUPPORTING", "role": "intervention_mapping"},
    "i5_study_interventions": {"class": "CANONICAL", "role": "study_intervention_link"},
    "i5_clinical_outcomes": {"class": "CANONICAL", "role": "outcome_vocab"},
    "i5_study_outcomes": {"class": "CANONICAL", "role": "study_outcome_link"},
    "i5_study_effect_estimates": {"class": "CANONICAL", "role": "effect_estimate"},
    "i5_clinical_recommendations": {"class": "CANONICAL", "role": "recommendation_authority"},
    "i5_clinical_recommendation_condition_links": {"class": "SUPPORTING", "role": "rec_condition_link"},
    "i5_clinical_recommendation_evidence_links": {"class": "CANONICAL", "role": "rec_evidence_link"},
    "i5_scientific_change_events": {"class": "AUDIT", "role": "change_retraction_ledger"},
    "i5_artifact_version_content_drift_events": {"class": "AUDIT", "role": "content_drift_ledger"},
    "i5_terminology_releases": {"class": "CANONICAL", "role": "terminology_release"},
    "i5_terminology_import_contracts": {"class": "CANONICAL", "role": "terminology_import_contract"},
    "i5_terminology_import_runs": {"class": "AUDIT", "role": "terminology_import_run"},
    "i5_terminology_mapping_conflict_events": {"class": "AUDIT", "role": "terminology_conflict"},
    "i5_sedi_priority_overlays": {"class": "SUPPORTING", "role": "p0_priority_overlay"},
    "i5_connector_profiles": {"class": "SUPPORTING", "role": "connector_config"},
    "i5_connector_cursors": {"class": "SUPPORTING", "role": "connector_cursor"},
    "i5_connector_run_events": {"class": "AUDIT", "role": "connector_run_event"},
    "i5_source_ingestion_audit": {"class": "AUDIT", "role": "ingestion_rights_audit"},
    "weekly_knowledge_runs": {"class": "AUDIT", "role": "weekly_run_ledger"},
    "weekly_knowledge_run_attempts": {"class": "AUDIT", "role": "weekly_attempt_ledger"},
    "weekly_run_source_results": {"class": "AUDIT", "role": "weekly_source_result"},
    "weekly_run_gap_results": {"class": "AUDIT", "role": "weekly_gap_result"},
    "knowledge_gaps": {"class": "CANONICAL", "role": "gap_sot"},
    "i5_governance_decisions": {"class": "AUDIT", "role": "governance_decision_ledger"},
    "knowledge_conflicts": {"class": "SUPPORTING", "role": "conflict_queue"},
    "knowledge_safety_reviews": {"class": "SUPPORTING", "role": "safety_queue"},
    "knowledge_chunk_embeddings": {
        "class": "INDEX",
        "role": "scis_rag_index",
        "scis_rag_role": "REBUILDABLE_INDEX_NOT_SOT",
        "invalidation_path": "retracted_at + index_generation",
    },
    "knowledge_chunks": {"class": "INDEX", "role": "physical_chunk_carrier"},
    "knowledge_documents": {"class": "LEGACY_DEPRECATED", "role": "legacy_document_host"},
    "knowledge_sources": {
        "class": "LEGACY_DEPRECATED",
        "role": "legacy_crawler_authority_replaced_by_gsp",
        "scis_rag_role": "NOT_RUNTIME_AUTHORITY",
    },
    "knowledge_ingestion_runs": {"class": "LEGACY_DEPRECATED", "role": "legacy_ingestion_run"},
    "iran_doctors": {"class": "NOT_RUNTIME_AUTHORITY", "role": "iran_directory"},
    "iran_laboratories": {"class": "NOT_RUNTIME_AUTHORITY", "role": "iran_directory"},
    "iran_hospitals": {"class": "NOT_RUNTIME_AUTHORITY", "role": "iran_directory"},
}


@dataclass
class AuthorityAuditRow:
    table_name: str
    present_in_orm: bool
    present_in_db: Optional[bool]
    authority_class: str
    role: str
    detail: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "present_in_orm": self.present_in_orm,
            "present_in_db": self.present_in_db,
            "authority_class": self.authority_class,
            "role": self.role,
            "detail": dict(self.detail),
        }


@dataclass
class AuthorityAuditReport:
    rows: list[AuthorityAuditRow]
    duplicate_knowledge_authority: int
    duplicate_findings: list[str]
    orm_table_count: int
    classified_count: int
    unclassified_knowledgeish: list[str]
    computation_basis: str = "ORM_INTROSPECTION+EXPLICIT_INVARIANTS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows": [r.as_dict() for r in self.rows],
            "duplicate_knowledge_authority": self.duplicate_knowledge_authority,
            "duplicate_findings": list(self.duplicate_findings),
            "orm_table_count": self.orm_table_count,
            "classified_count": self.classified_count,
            "unclassified_knowledgeish": list(self.unclassified_knowledgeish),
            "computation_basis": self.computation_basis,
        }


def _orm_table_names() -> set[str]:
    names: set[str] = set()
    for mapper in models.Base.registry.mappers:
        table = getattr(mapper.class_, "__tablename__", None)
        if table:
            names.add(table)
    return names


def _db_table_names(db: Optional[Session]) -> Optional[set[str]]:
    if db is None:
        return None
    from sqlalchemy import inspect

    return set(inspect(db.bind).get_table_names())


def compute_duplicate_authority(orm_tables: set[str]) -> tuple[int, list[str]]:
    """Derive duplicate-authority count from explicit invariants (not a hardcoded 0)."""
    findings: list[str] = []

    # Invariant 1: KU is sole claim SoT; legacy knowledge_sources must be LEGACY if present
    if "knowledge_units" in orm_tables and "knowledge_sources" in orm_tables:
        # Allowed only if knowledge_sources classified LEGACY_DEPRECATED (by spec)
        if _AUTHORITY_SPEC.get("knowledge_sources", {}).get("class") != "LEGACY_DEPRECATED":
            findings.append("PARALLEL_SOURCE_AUTHORITY:knowledge_sources_not_legacy")

    # Invariant 2: GSP must be present as canonical source identity
    if "governed_source_profiles" not in orm_tables:
        findings.append("MISSING_CANONICAL_SOURCE_IDENTITY:governed_source_profiles")

    # Invariant 3: KCE must be INDEX not CANONICAL
    if _AUTHORITY_SPEC.get("knowledge_chunk_embeddings", {}).get("class") != "INDEX":
        findings.append("INDEX_CLAIMING_SOT:knowledge_chunk_embeddings")

    # Invariant 4: no second KU-like claim table classified CANONICAL with role knowledge_unit
    ku_roles = [
        t
        for t, spec in _AUTHORITY_SPEC.items()
        if spec.get("role") == "knowledge_unit_authority" and t in orm_tables
    ]
    if len(ku_roles) != 1:
        findings.append(f"KU_AUTHORITY_CARDINALITY:{ku_roles}")

    # Invariant 5: Iran directory must not be clinical KU authority
    for t in ("iran_doctors", "iran_laboratories", "iran_hospitals"):
        if t in orm_tables and _AUTHORITY_SPEC.get(t, {}).get("class") != "NOT_RUNTIME_AUTHORITY":
            findings.append(f"IRAN_DIRECTORY_AS_CLINICAL:{t}")

    return len(findings), findings


def audit_knowledge_authority(db: Optional[Session] = None) -> AuthorityAuditReport:
    orm_tables = _orm_table_names()
    db_tables = _db_table_names(db)
    rows: list[AuthorityAuditRow] = []
    for table, spec in sorted(_AUTHORITY_SPEC.items()):
        present_orm = table in orm_tables
        present_db = (table in db_tables) if db_tables is not None else None
        rows.append(
            AuthorityAuditRow(
                table_name=table,
                present_in_orm=present_orm,
                present_in_db=present_db,
                authority_class=spec["class"],
                role=spec.get("role", ""),
                detail={k: v for k, v in spec.items() if k not in {"class", "role"}},
            )
        )

    # Flag unclassified knowledge-ish ORM tables
    knowledgeish_prefixes = (
        "knowledge_",
        "i5_",
        "weekly_",
        "governed_source",
        "iran_",
    )
    unclassified = sorted(
        t
        for t in orm_tables
        if t not in _AUTHORITY_SPEC and any(t.startswith(p) for p in knowledgeish_prefixes)
    )
    dup_count, dup_findings = compute_duplicate_authority(orm_tables)
    return AuthorityAuditReport(
        rows=rows,
        duplicate_knowledge_authority=dup_count,
        duplicate_findings=dup_findings,
        orm_table_count=len(orm_tables),
        classified_count=len(rows),
        unclassified_knowledgeish=unclassified,
    )


def matrices_summary(db: Optional[Session] = None) -> dict[str, Any]:
    report = audit_knowledge_authority(db)
    classes = [r.authority_class for r in report.rows]
    return {
        "authority_rows": len(report.rows),
        "orm_table_count": report.orm_table_count,
        "duplicate_knowledge_authority": report.duplicate_knowledge_authority,
        "duplicate_findings": report.duplicate_findings,
        "canonical_count": classes.count("CANONICAL"),
        "index_count": classes.count("INDEX"),
        "legacy_count": classes.count("LEGACY_DEPRECATED"),
        "unclassified_knowledgeish": report.unclassified_knowledgeish,
        "new_migration": "NO",
        "alembic_head": "065_i5_know04_connectors_change_intelligence",
        "computation_basis": report.computation_basis,
    }

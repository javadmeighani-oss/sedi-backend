"""Taxonomy / concept / dimension services (universal — no P0-specific branching)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    ClinicalConceptType,
    KnowledgeDimensionCode,
    SediCoveragePriority,
    SediRootCategory,
    TerminologySystem,
)


def ensure_dimension(db: Session, code: str, label: Optional[str] = None) -> models.I5KnowledgeDimension:
    KnowledgeDimensionCode(code)
    row = db.query(models.I5KnowledgeDimension).filter_by(code=code).first()
    if row:
        return row
    row = models.I5KnowledgeDimension(code=code, label=label or code.replace("_", " ").title())
    db.add(row)
    db.flush()
    return row


def seed_all_dimensions(db: Session) -> int:
    n = 0
    for dim in KnowledgeDimensionCode:
        ensure_dimension(db, dim.value)
        n += 1
    return n


def upsert_concept(
    db: Session,
    *,
    concept_key: str,
    preferred_name: str,
    concept_type: str,
    root_category: Optional[str] = None,
    parent_concept_id: Optional[int] = None,
    **flags,
) -> models.I5ClinicalConcept:
    ClinicalConceptType(concept_type)
    if root_category:
        SediRootCategory(root_category)
    row = db.query(models.I5ClinicalConcept).filter_by(concept_key=concept_key).first()
    if row is None:
        row = models.I5ClinicalConcept(
            concept_key=concept_key,
            preferred_name=preferred_name,
            normalized_name=preferred_name.strip().lower(),
            concept_type=concept_type,
        )
        db.add(row)
    row.preferred_name = preferred_name
    row.normalized_name = preferred_name.strip().lower()
    row.concept_type = concept_type
    row.root_category = root_category
    row.parent_concept_id = parent_concept_id
    for k, v in flags.items():
        if hasattr(row, k) and v is not None:
            setattr(row, k, v)
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def add_mapping(
    db: Session,
    *,
    concept_id: int,
    terminology_system: str,
    external_code: str,
    release_version: Optional[str] = None,
    is_primary: bool = False,
    mapping_status: str = "PROVISIONAL",
    provenance_note: Optional[str] = None,
) -> models.I5ClinicalConceptMapping:
    TerminologySystem(terminology_system)
    existing = (
        db.query(models.I5ClinicalConceptMapping)
        .filter_by(
            terminology_system=terminology_system,
            external_code=external_code,
            release_version=release_version,
        )
        .first()
    )
    if existing:
        if existing.concept_id == concept_id:
            existing.is_primary = is_primary
            existing.mapping_status = mapping_status
            if provenance_note is not None:
                existing.provenance_note = provenance_note
            db.flush()
            return existing
        from backend.app.services.i5.know04.terminology_remap import record_mapping_conflict

        raise record_mapping_conflict(
            db,
            mapping_kind="CLINICAL_CONCEPT",
            terminology_system=terminology_system,
            external_code=external_code,
            release_version=release_version,
            existing_target_id=existing.concept_id,
            incoming_target_id=concept_id,
            existing_mapping_id=existing.id,
        )
    row = models.I5ClinicalConceptMapping(
        concept_id=concept_id,
        terminology_system=terminology_system,
        external_code=external_code,
        release_version=release_version,
        is_primary=is_primary,
        mapping_status=mapping_status,
        provenance_note=provenance_note,
    )
    db.add(row)
    db.flush()
    return row


def add_label(
    db: Session,
    *,
    concept_id: int,
    language: str,
    label_kind: str,
    label_text: str,
    verified: bool = False,
    provenance_note: Optional[str] = None,
) -> models.I5ClinicalConceptLabel:
    row = models.I5ClinicalConceptLabel(
        concept_id=concept_id,
        language=language,
        label_kind=label_kind,
        label_text=label_text,
        verified=verified,
        provenance_note=provenance_note,
    )
    db.add(row)
    db.flush()
    return row


def set_priority_overlay(
    db: Session,
    *,
    concept_id: int,
    priority_class: str,
    track_key: Optional[str] = None,
    rationale: Optional[str] = None,
) -> models.I5SediPriorityOverlay:
    SediCoveragePriority(priority_class)
    row = (
        db.query(models.I5SediPriorityOverlay)
        .filter_by(concept_id=concept_id, track_key=track_key)
        .first()
    )
    if row is None:
        row = models.I5SediPriorityOverlay(
            concept_id=concept_id, priority_class=priority_class, track_key=track_key
        )
        db.add(row)
    row.priority_class = priority_class
    row.rationale = rationale
    row.active = True
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def link_ku_concept(
    db: Session, *, knowledge_unit_id: int, concept_id: int, relation_role: str = "ABOUT"
) -> models.I5KnowledgeUnitConcept:
    existing = (
        db.query(models.I5KnowledgeUnitConcept)
        .filter_by(
            knowledge_unit_id=knowledge_unit_id, concept_id=concept_id, relation_role=relation_role
        )
        .first()
    )
    if existing:
        return existing
    row = models.I5KnowledgeUnitConcept(
        knowledge_unit_id=knowledge_unit_id, concept_id=concept_id, relation_role=relation_role
    )
    db.add(row)
    db.flush()
    return row


def link_ku_dimension(
    db: Session, *, knowledge_unit_id: int, dimension_code: str
) -> models.I5KnowledgeUnitDimension:
    KnowledgeDimensionCode(dimension_code)
    ensure_dimension(db, dimension_code)
    existing = (
        db.query(models.I5KnowledgeUnitDimension)
        .filter_by(knowledge_unit_id=knowledge_unit_id, dimension_code=dimension_code)
        .first()
    )
    if existing:
        return existing
    row = models.I5KnowledgeUnitDimension(
        knowledge_unit_id=knowledge_unit_id, dimension_code=dimension_code
    )
    db.add(row)
    db.flush()
    return row


def upsert_coverage_cell(
    db: Session,
    *,
    concept_id: int,
    dimension_code: str,
    cell_state: str,
    evidence_class: Optional[str] = None,
    detail: Optional[str] = None,
) -> models.I5KnowledgeCoverageCell:
    from backend.app.services.i5.enums import CoverageCellState

    CoverageCellState(cell_state)
    ensure_dimension(db, dimension_code)
    row = (
        db.query(models.I5KnowledgeCoverageCell)
        .filter_by(concept_id=concept_id, dimension_code=dimension_code, evidence_class=evidence_class)
        .first()
    )
    if row is None:
        row = models.I5KnowledgeCoverageCell(
            concept_id=concept_id,
            dimension_code=dimension_code,
            evidence_class=evidence_class,
            cell_state=cell_state,
        )
        db.add(row)
    row.cell_state = cell_state
    row.detail = detail
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def query_kus_by_concept_and_dimension(
    db: Session, *, concept_id: int, dimension_code: str
) -> Sequence[models.KnowledgeUnit]:
    return (
        db.query(models.KnowledgeUnit)
        .join(
            models.I5KnowledgeUnitConcept,
            models.I5KnowledgeUnitConcept.knowledge_unit_id == models.KnowledgeUnit.id,
        )
        .join(
            models.I5KnowledgeUnitDimension,
            models.I5KnowledgeUnitDimension.knowledge_unit_id == models.KnowledgeUnit.id,
        )
        .filter(models.I5KnowledgeUnitConcept.concept_id == concept_id)
        .filter(models.I5KnowledgeUnitDimension.dimension_code == dimension_code)
        .all()
    )

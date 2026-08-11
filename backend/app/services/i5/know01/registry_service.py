"""Trusted Source Registry service — queryable overlay on GSP."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    P0DiseaseRelevance,
    RightDecision,
    SourceAuthorityClass,
    SourceRole,
    SourceUniverse,
)
from backend.app.services.i5.know01.rights_engine import evaluate_automation_rights


def upsert_registry_extension(
    db: Session,
    *,
    source_profile_id: int,
    source_universe: str,
    authority_class: str,
    publisher_family: Optional[str] = None,
    roles: Sequence[str] = (),
    p0_tags: Optional[dict] = None,
    **fields,
) -> models.I5SourceRegistryExtension:
    if source_universe == SourceUniverse.IRAN_LOCAL_DIRECTORY.value:
        # Hard invariant: never clinical KU authority via this universe alone
        fields.setdefault("notes", (fields.get("notes") or "") + " | IRAN_DIRECTORY!=CLINICAL_KU")
    row = db.query(models.I5SourceRegistryExtension).filter_by(source_profile_id=source_profile_id).first()
    if row is None:
        row = models.I5SourceRegistryExtension(
            source_profile_id=source_profile_id,
            source_universe=source_universe,
            authority_class=authority_class,
            publisher_family=publisher_family,
        )
        db.add(row)
    else:
        row.source_universe = source_universe
        row.authority_class = authority_class
        if publisher_family is not None:
            row.publisher_family = publisher_family
    for k, v in fields.items():
        if hasattr(row, k) and v is not None:
            setattr(row, k, v)
    row.updated_at = datetime.utcnow()
    db.flush()

    # replace roles
    if roles:
        db.query(models.I5SourceRegistryRole).filter_by(source_profile_id=source_profile_id).delete()
        for role in roles:
            SourceRole(role)  # validate
            db.add(models.I5SourceRegistryRole(source_profile_id=source_profile_id, role=role))
    if p0_tags:
        for disease, relevance in p0_tags.items():
            P0DiseaseRelevance(relevance)
            existing = (
                db.query(models.I5SourceP0Tag)
                .filter_by(source_profile_id=source_profile_id, disease=disease)
                .first()
            )
            if existing:
                existing.relevance = relevance
            else:
                db.add(
                    models.I5SourceP0Tag(
                        source_profile_id=source_profile_id, disease=disease, relevance=relevance
                    )
                )
    db.flush()
    return row


def automation_decision_for_extension(ext: models.I5SourceRegistryExtension):
    return evaluate_automation_rights(
        access_right=ext.access_right,
        automation_right=ext.automation_right,
        tdm_right=ext.tdm_right,
        transform_right=ext.transform_right,
        retain_raw_right=ext.retain_raw_right,
        retain_derived_right=ext.retain_derived_right,
        redistribution_right=ext.redistribution_right,
        robots_state=ext.robots_state,
        processing_permission_mode=ext.processing_permission_mode,
    )


def query_sources_by_role(db: Session, role: str) -> List[models.I5SourceRegistryExtension]:
    SourceRole(role)
    return (
        db.query(models.I5SourceRegistryExtension)
        .join(
            models.I5SourceRegistryRole,
            models.I5SourceRegistryRole.source_profile_id
            == models.I5SourceRegistryExtension.source_profile_id,
        )
        .filter(models.I5SourceRegistryRole.role == role)
        .all()
    )


def query_iran_directory_sources(db: Session, role: Optional[str] = None):
    q = db.query(models.I5SourceRegistryExtension).filter(
        models.I5SourceRegistryExtension.source_universe == SourceUniverse.IRAN_LOCAL_DIRECTORY.value
    )
    if role:
        q = q.join(
            models.I5SourceRegistryRole,
            models.I5SourceRegistryRole.source_profile_id
            == models.I5SourceRegistryExtension.source_profile_id,
        ).filter(models.I5SourceRegistryRole.role == role)
    return q.all()


def assert_commercial_not_primary_credential(ext: models.I5SourceRegistryExtension) -> None:
    if (
        ext.authority_class == SourceAuthorityClass.COMMERCIAL_DIRECTORY.value
        and ext.credential_authority
    ):
        raise PermissionError("COMMERCIAL_DIRECTORY_CANNOT_BE_PRIMARY_CREDENTIAL_AUTHORITY")


def ensure_gsp(db: Session, *, canonical_key: str, locator: Optional[str] = None) -> models.GovernedSourceProfile:
    row = db.query(models.GovernedSourceProfile).filter_by(canonical_key=canonical_key).first()
    if row:
        return row
    row = models.GovernedSourceProfile(
        canonical_key=canonical_key,
        locator_kind="URL" if locator else None,
        normalized_locator=locator,
        operational_status="disabled",
        registry_state="DISCOVERED",
        runtime_eligibility="NOT_ELIGIBLE",
        canonicalization_version="v1",
    )
    db.add(row)
    db.flush()
    return row

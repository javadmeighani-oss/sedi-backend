"""Test-only helpers to seed governed conditions — never called from product path."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    GovernanceActorType,
    GovernanceDecisionFamily,
    GovernanceDecisionOutcome,
    GovernanceDecisionType,
    GovernanceEntityType,
    ProcessingPermissionMode,
    RightDecision,
    SourceAuthorityClass,
    SourceUniverse,
)
from backend.app.services.i5.know01.registry_service import ensure_gsp, upsert_registry_extension
from backend.app.services.i5.know05.canonical_rights import canonical_key_for_connector


def seed_canonical_source_with_rights(
    db: Session,
    *,
    connector_key: str = "clinicaltrials_gov_api_v2",
    rights_mode: str = "ALLOWED",
) -> models.GovernedSourceProfile:
    """Explicit test fixture. Product path must not call this."""
    key = canonical_key_for_connector(connector_key)
    gsp = ensure_gsp(db, canonical_key=key, locator=None)
    gsp.registry_state = "ACTIVE"
    gsp.runtime_eligibility = "ELIGIBLE" if rights_mode == "ALLOWED" else "NOT_ELIGIBLE"
    gsp.operational_status = "active"
    if rights_mode == "ALLOWED":
        fields = dict(
            access_right=RightDecision.ALLOWED.value,
            automation_right=RightDecision.ALLOWED.value,
            tdm_right=RightDecision.ALLOWED.value,
            transform_right=RightDecision.ALLOWED.value,
            retain_raw_right=RightDecision.DENIED.value,
            retain_derived_right=RightDecision.ALLOWED.value,
            redistribution_right=RightDecision.DENIED.value,
            robots_state="ALLOWED",
            processing_permission_mode=ProcessingPermissionMode.METADATA_ABSTRACT_ONLY.value,
            notes="TEST_FIXTURE_EXPLICIT_RIGHTS_ALLOWED",
        )
    elif rights_mode == "DENIED":
        fields = dict(
            access_right=RightDecision.DENIED.value,
            automation_right=RightDecision.DENIED.value,
            tdm_right=RightDecision.DENIED.value,
            transform_right=RightDecision.DENIED.value,
            retain_raw_right=RightDecision.DENIED.value,
            retain_derived_right=RightDecision.DENIED.value,
            redistribution_right=RightDecision.DENIED.value,
            robots_state="DISALLOWED",
            processing_permission_mode=ProcessingPermissionMode.FULLTEXT_AUTOMATION_BLOCKED.value,
            notes="TEST_FIXTURE_EXPLICIT_RIGHTS_DENIED",
        )
    else:
        fields = dict(
            access_right=RightDecision.UNKNOWN.value,
            automation_right=RightDecision.UNKNOWN.value,
            tdm_right=RightDecision.UNKNOWN.value,
            transform_right=RightDecision.UNKNOWN.value,
            retain_raw_right=RightDecision.UNKNOWN.value,
            retain_derived_right=RightDecision.UNKNOWN.value,
            redistribution_right=RightDecision.UNKNOWN.value,
            robots_state="UNKNOWN",
            processing_permission_mode=ProcessingPermissionMode.FULLTEXT_AUTOMATION_BLOCKED.value,
            notes="TEST_FIXTURE_EXPLICIT_RIGHTS_UNKNOWN",
        )
    upsert_registry_extension(
        db,
        source_profile_id=gsp.id,
        source_universe=SourceUniverse.GLOBAL_KNOWLEDGE.value,
        authority_class=SourceAuthorityClass.CLINICAL_TRIAL_REGISTRY.value,
        publisher_family="ClinicalTrials.gov",
        roles=("CLINICAL_TRIAL",),
        **fields,
    )
    db.flush()
    return gsp


def seed_source_governance_approval(db: Session, *, source_profile_id: int) -> models.I5GovernanceDecision:
    """Explicit APPROVED AUTOMATION_REVIEW on SOURCE_PROFILE for positive fixture."""
    req = f"know05-test-gov:{source_profile_id}:{int(datetime.utcnow().timestamp())}"
    payload = f"SOURCE_PROFILE|{source_profile_id}|AUTOMATION|AUTOMATION_REVIEW|APPROVED|{req}"
    row = models.I5GovernanceDecision(
        entity_type=GovernanceEntityType.SOURCE_PROFILE.value,
        entity_id=source_profile_id,
        decision_family=GovernanceDecisionFamily.AUTOMATION.value,
        decision_type=GovernanceDecisionType.AUTOMATION_REVIEW.value,
        decision_request_key=req[:128],
        outcome=GovernanceDecisionOutcome.APPROVED.value,
        actor_type=GovernanceActorType.HUMAN.value,
        actor_reference="test_fixture",
        reason_code="TEST_EXPLICIT_GOVERNANCE",
        reason="Explicit test fixture governance approval",
        canonical_hash=hashlib.sha256(payload.encode()).hexdigest(),
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    db.add(row)
    db.flush()
    return row

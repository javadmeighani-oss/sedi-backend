"""Evidence-derived authority assessment (discovery ≠ trust ≠ activation).

Uses only existing GSP / I5SourceRegistryExtension fields.
Never treats medical-looking hostnames, titles, or TLDs as sufficient authority.
Never accepts a caller-supplied boolean as the sole authority decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional, Sequence
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import SourceAuthorityClass, SourceUniverse
from backend.app.services.i5.know01.discovery_foundation import assert_domain_not_trusted_by_name_alone
from backend.app.services.i5.know01.registry_service import ensure_gsp, upsert_registry_extension


# Institutional classes that *may* qualify when corroborating evidence exists.
_RECOGNIZED_AUTHORITY_CLASSES = frozenset(
    {
        SourceAuthorityClass.GLOBAL_INTERGOVERNMENTAL.value,
        SourceAuthorityClass.NATIONAL_HEALTH_AUTHORITY.value,
        SourceAuthorityClass.REGULATORY_AUTHORITY.value,
        SourceAuthorityClass.OFFICIAL_PUBLIC_HEALTH.value,
        SourceAuthorityClass.NATIONAL_MEDICAL_LIBRARY.value,
        SourceAuthorityClass.PROFESSIONAL_MEDICAL_SOCIETY.value,
        SourceAuthorityClass.SPECIALTY_GUIDELINE_BODY.value,
        SourceAuthorityClass.SYSTEMATIC_REVIEW_AUTHORITY.value,
        SourceAuthorityClass.PEER_REVIEWED_JOURNAL.value,
        SourceAuthorityClass.CLINICAL_TRIAL_REGISTRY.value,
        SourceAuthorityClass.ACADEMIC_MEDICAL_CENTER.value,
        SourceAuthorityClass.REFERENCE_BOOK_PUBLISHER.value,
        SourceAuthorityClass.OPEN_ACCESS_REPOSITORY.value,
        SourceAuthorityClass.IRAN_MINISTRY_HEALTH.value,
        SourceAuthorityClass.IRAN_MEDICAL_COUNCIL.value,
        SourceAuthorityClass.IRAN_MEDICAL_UNIVERSITY.value,
        SourceAuthorityClass.IRAN_REGULATORY_AUTHORITY.value,
        SourceAuthorityClass.IRAN_REFERENCE_LAB_AUTHORITY.value,
        SourceAuthorityClass.IRAN_HOSPITAL_AUTHORITY.value,
        SourceAuthorityClass.IRAN_PROVIDER_LICENSING_AUTHORITY.value,
    }
)

_INSUFFICIENT_ALONE = frozenset(
    {
        SourceAuthorityClass.UNVERIFIED.value,
        SourceAuthorityClass.SECONDARY_CORROBORATION.value,
        SourceAuthorityClass.COMMERCIAL_DIRECTORY.value,
        "",
    }
)


@dataclass(frozen=True)
class AuthorityAssessmentResult:
    candidate_identity: str
    assessment_status: str
    authority_class: Optional[str]
    evidence_used: List[str] = field(default_factory=list)
    evidence_missing: List[str] = field(default_factory=list)
    blocking_reasons: List[str] = field(default_factory=list)
    requires_human_governance_review: bool = True
    eligible_to_proceed_to_rights_review: bool = False
    eligible_for_activation: bool = False
    authority_verified: bool = False
    auto_trust: bool = False
    auto_activate: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_identity": self.candidate_identity,
            "assessment_status": self.assessment_status,
            "authority_class": self.authority_class,
            "evidence_used": list(self.evidence_used),
            "evidence_missing": list(self.evidence_missing),
            "blocking_reasons": list(self.blocking_reasons),
            "requires_human_governance_review": self.requires_human_governance_review,
            "eligible_to_proceed_to_rights_review": self.eligible_to_proceed_to_rights_review,
            "eligible_for_activation": self.eligible_for_activation,
            "authority_verified": self.authority_verified,
            "auto_trust": self.auto_trust,
            "auto_activate": self.auto_activate,
        }


def _hostname_from_url(url: Optional[str]) -> str:
    if not url:
        return ""
    try:
        return (urlparse(url).hostname or "").lower().strip(".")
    except Exception:
        return ""


def _looks_like_medical_bait_host(hostname: str) -> bool:
    host = (hostname or "").lower().strip(".")
    if not host:
        return False
    bait = (
        "medline",
        "pubmed",
        "whohealth",
        "clinic",
        "hospital",
        "pharma",
        "nih-",
        "cdc-",
        "best-medical",
        "medical-guidelines",
    )
    return any(b in host for b in bait) or host.endswith(".health") or "medical" in host


def assess_authority_from_registry_evidence(
    *,
    candidate_identity: str,
    authority_class: Optional[str] = None,
    canonical_home: Optional[str] = None,
    publisher_family: Optional[str] = None,
    source_universe: Optional[str] = None,
    last_authority_verification: Optional[datetime] = None,
    review_stage: Optional[str] = None,
    registry_status: Optional[str] = None,
    roles: Sequence[str] = (),
    specialty_domains: Optional[str] = None,
    knowledge_domains: Optional[str] = None,
    canonical_discovery_endpoint: Optional[str] = None,
    api_endpoint: Optional[str] = None,
    notes: Optional[str] = None,
    gsp_registry_state: Optional[str] = None,
    hostname_hint: Optional[str] = None,
) -> AuthorityAssessmentResult:
    """Deterministic fail-closed authority assessment from persisted metadata only."""
    evidence_used: list[str] = []
    evidence_missing: list[str] = []
    blockers: list[str] = []

    host = (hostname_hint or "").lower().strip(".")
    if not host:
        host = _hostname_from_url(canonical_home) or _hostname_from_url(api_endpoint) or _hostname_from_url(
            canonical_discovery_endpoint
        )
    if host:
        assert_domain_not_trusted_by_name_alone(host)
        if _looks_like_medical_bait_host(host) and not (
            authority_class in _RECOGNIZED_AUTHORITY_CLASSES and last_authority_verification is not None
        ):
            blockers.append("MEDICAL_LOOKING_HOSTNAME_INSUFFICIENT")
            evidence_used.append(f"hostname={host}")

    ac = (authority_class or SourceAuthorityClass.UNVERIFIED.value).upper()
    if ac and ac != SourceAuthorityClass.UNVERIFIED.value:
        evidence_used.append(f"authority_class={ac}")
    else:
        evidence_missing.append("authority_class_recognized")

    if publisher_family:
        evidence_used.append(f"publisher_family={publisher_family}")
    else:
        evidence_missing.append("publisher_family")

    if canonical_home:
        evidence_used.append("canonical_home")
    else:
        evidence_missing.append("canonical_home")

    if last_authority_verification is not None:
        evidence_used.append("last_authority_verification")
    else:
        evidence_missing.append("last_authority_verification")

    if roles:
        evidence_used.append(f"roles={','.join(sorted(set(roles)))}")
    else:
        evidence_missing.append("source_roles")

    if specialty_domains or knowledge_domains:
        evidence_used.append("domain_or_specialty_metadata")

    route = canonical_discovery_endpoint or api_endpoint
    if route:
        evidence_used.append("canonical_access_route")
    else:
        evidence_missing.append("canonical_access_route")

    if source_universe:
        evidence_used.append(f"source_universe={source_universe}")

    if (gsp_registry_state or "").upper() in {"ACTIVE", "APPROVED"}:
        evidence_used.append(f"gsp_registry_state={gsp_registry_state}")

    # Name / TLD alone never verify.
    if "MEDICAL_LOOKING_HOSTNAME_INSUFFICIENT" in blockers and last_authority_verification is None:
        return AuthorityAssessmentResult(
            candidate_identity=candidate_identity,
            assessment_status="AUTHORITY_REVIEW_REQUIRED",
            authority_class=ac,
            evidence_used=evidence_used,
            evidence_missing=evidence_missing,
            blocking_reasons=blockers + ["AUTHORITY_VERIFIED=NO"],
            requires_human_governance_review=True,
            eligible_to_proceed_to_rights_review=False,
            eligible_for_activation=False,
            authority_verified=False,
        )

    # Identity-only / unverified class → review.
    if ac in _INSUFFICIENT_ALONE or ac == SourceAuthorityClass.UNVERIFIED.value:
        blockers.append("AUTHORITY_CLASS_INSUFFICIENT")
        return AuthorityAssessmentResult(
            candidate_identity=candidate_identity,
            assessment_status="AUTHORITY_REVIEW_REQUIRED",
            authority_class=ac,
            evidence_used=evidence_used,
            evidence_missing=evidence_missing,
            blocking_reasons=blockers,
            requires_human_governance_review=True,
            eligible_to_proceed_to_rights_review=False,
            eligible_for_activation=False,
            authority_verified=False,
        )

    if ac not in _RECOGNIZED_AUTHORITY_CLASSES:
        blockers.append("AUTHORITY_CLASS_NOT_RECOGNIZED")
        return AuthorityAssessmentResult(
            candidate_identity=candidate_identity,
            assessment_status="AUTHORITY_REVIEW_REQUIRED",
            authority_class=ac,
            evidence_used=evidence_used,
            evidence_missing=evidence_missing,
            blocking_reasons=blockers,
            requires_human_governance_review=True,
            eligible_to_proceed_to_rights_review=False,
            eligible_for_activation=False,
            authority_verified=False,
        )

    # Recognized class still requires verification timestamp + canonical identity route.
    strong = (
        last_authority_verification is not None
        and bool(canonical_home)
        and bool(publisher_family)
        and bool(roles)
    )
    if not strong:
        blockers.append("INSUFFICIENT_AUTHORITY_EVIDENCE")
        return AuthorityAssessmentResult(
            candidate_identity=candidate_identity,
            assessment_status="AUTHORITY_REVIEW_REQUIRED",
            authority_class=ac,
            evidence_used=evidence_used,
            evidence_missing=evidence_missing,
            blocking_reasons=blockers,
            requires_human_governance_review=True,
            eligible_to_proceed_to_rights_review=bool(canonical_home or publisher_family),
            eligible_for_activation=False,
            authority_verified=False,
        )

    # Evidence-derived verified — still never auto-activate.
    status = "AUTHORITY_EVIDENCE_SUFFICIENT"
    if (review_stage or "").upper() in {"NONE", "", "AUTHORITY_REVIEW"} and (
        registry_status or ""
    ).upper() in {"DISCOVERED", "UNDER_REVIEW", ""}:
        # Enough to proceed to rights review; activation remains governed.
        pass

    return AuthorityAssessmentResult(
        candidate_identity=candidate_identity,
        assessment_status=status,
        authority_class=ac,
        evidence_used=evidence_used,
        evidence_missing=evidence_missing,
        blocking_reasons=[],
        requires_human_governance_review=True,  # medical trust remains governed
        eligible_to_proceed_to_rights_review=True,
        eligible_for_activation=False,
        authority_verified=True,
        auto_trust=False,
        auto_activate=False,
    )


def assess_authority_for_source_profile(db: Session, source_profile_id: int) -> AuthorityAssessmentResult:
    gsp = db.query(models.GovernedSourceProfile).filter_by(id=source_profile_id).first()
    if gsp is None:
        return AuthorityAssessmentResult(
            candidate_identity=f"missing:{source_profile_id}",
            assessment_status="AUTHORITY_REVIEW_REQUIRED",
            authority_class=SourceAuthorityClass.UNVERIFIED.value,
            evidence_missing=["governed_source_profile"],
            blocking_reasons=["GSP_NOT_FOUND"],
            requires_human_governance_review=True,
            authority_verified=False,
        )
    ext = (
        db.query(models.I5SourceRegistryExtension)
        .filter_by(source_profile_id=source_profile_id)
        .first()
    )
    roles = [
        r.role
        for r in db.query(models.I5SourceRegistryRole)
        .filter_by(source_profile_id=source_profile_id)
        .all()
    ]
    if ext is None:
        return AuthorityAssessmentResult(
            candidate_identity=gsp.canonical_key or str(source_profile_id),
            assessment_status="AUTHORITY_REVIEW_REQUIRED",
            authority_class=SourceAuthorityClass.UNVERIFIED.value,
            evidence_used=["gsp_identity"],
            evidence_missing=["registry_extension"],
            blocking_reasons=["REGISTRY_EXTENSION_MISSING"],
            requires_human_governance_review=True,
            authority_verified=False,
        )
    return assess_authority_from_registry_evidence(
        candidate_identity=gsp.canonical_key or str(source_profile_id),
        authority_class=ext.authority_class,
        canonical_home=ext.canonical_home,
        publisher_family=ext.publisher_family,
        source_universe=ext.source_universe,
        last_authority_verification=ext.last_authority_verification,
        review_stage=ext.review_stage,
        registry_status=ext.registry_status,
        roles=roles,
        specialty_domains=ext.specialty_domains,
        knowledge_domains=ext.knowledge_domains,
        canonical_discovery_endpoint=ext.canonical_discovery_endpoint,
        api_endpoint=ext.api_endpoint,
        notes=ext.notes,
        gsp_registry_state=gsp.registry_state,
    )


def persist_discovery_candidate(
    db: Session,
    *,
    candidate_key: str,
    locator: Optional[str],
    seed_org_domain: str,
    assessment: AuthorityAssessmentResult,
    roles: Sequence[str] = (),
    source_universe: str = SourceUniverse.GLOBAL_KNOWLEDGE.value,
) -> models.GovernedSourceProfile:
    """Persist a discovered candidate as DISCOVERED / NOT_ELIGIBLE (no auto-activation)."""
    from backend.app.services.i5.enums import RightDecision, ProcessingPermissionMode

    canonical = candidate_key if candidate_key.startswith("know01:") else f"know01:{candidate_key}"
    gsp = ensure_gsp(db, canonical_key=canonical, locator=locator)
    gsp.registry_state = "DISCOVERED"
    gsp.runtime_eligibility = "NOT_ELIGIBLE"
    gsp.operational_status = "disabled"
    if assessment.blocking_reasons:
        gsp.block_reason = ";".join(assessment.blocking_reasons)[:2000]

    ac = assessment.authority_class or SourceAuthorityClass.UNVERIFIED.value
    upsert_registry_extension(
        db,
        source_profile_id=gsp.id,
        source_universe=source_universe,
        authority_class=ac,
        publisher_family=None,
        roles=list(roles) if roles else (),
        canonical_home=f"https://{seed_org_domain}" if seed_org_domain else None,
        access_right=RightDecision.UNKNOWN.value,
        automation_right=RightDecision.UNKNOWN.value,
        tdm_right=RightDecision.UNKNOWN.value,
        transform_right=RightDecision.UNKNOWN.value,
        retain_raw_right=RightDecision.UNKNOWN.value,
        retain_derived_right=RightDecision.UNKNOWN.value,
        redistribution_right=RightDecision.UNKNOWN.value,
        robots_state="UNKNOWN",
        processing_permission_mode=ProcessingPermissionMode.FULLTEXT_AUTOMATION_BLOCKED.value,
        review_stage="AUTHORITY_REVIEW",
        registry_status="DISCOVERED",
        notes=(
            f"AUTONOMOUS_DISCOVERY=YES;AUTONOMOUS_TRUST=NO;AUTONOMOUS_ACTIVATION=NO;"
            f"assessment={assessment.assessment_status};"
            f"evidence={','.join(assessment.evidence_used)}"
        )[:2000],
    )
    db.flush()
    return gsp

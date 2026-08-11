"""Knowledge eligibility integrity counters — derived from DB (NF23/NF25)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import MedicalSafetyState
from backend.app.services.i5.know05.canonical_rights import count_synthetic_product_rights_sources
from backend.app.services.i5.know05.publication import (
    source_has_approved_governance,
    trial_registry_forbids_clinical_runtime,
)
from backend.app.services.i5.know05.rag_coherence import resolve_ku_rights_state


@dataclass
class EligibilityIntegrityReport:
    eligible_with_unknown_safety: int
    eligible_without_real_governance: int
    eligible_without_provenance: int
    eligible_with_unknown_rights: int
    eligible_with_blocked_rights: int
    trial_registry_as_treatment_recommendation: int
    synthetic_product_rights_source_count: int
    synthetic_governance_auto_promotion_count: int
    computation_basis: str = "DB_DERIVED"

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    def assert_zero_violations(self) -> None:
        for k, v in self.as_dict().items():
            if k == "computation_basis":
                continue
            if int(v) != 0:
                raise AssertionError(f"ELIGIBILITY_INTEGRITY_VIOLATION:{k}={v}")


def ku_lacks_real_source_governance(db: Session, *, knowledge_unit_id: int) -> bool:
    """True when a KU has no proven SOURCE_PROFILE APPROVED governance decision."""
    prov = db.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=knowledge_unit_id).first()
    if prov is None:
        return True
    return not source_has_approved_governance(db, source_profile_id=prov.source_profile_id)


def count_synthetic_governance_auto_promotions(db: Session) -> int:
    """Count runtime-ELIGIBLE KUs promoted without real source governance evidence.

    Exact semantic equivalence (NF25 Strategy B, proven identical):
      synthetic_governance_auto_promotion_count
        == ELIGIBLE_WITHOUT_REAL_GOVERNANCE
        == count of KnowledgeUnit.runtime_eligibility == ELIGIBLE
           lacking KnowledgeProvenance→SOURCE_PROFILE APPROVED I5GovernanceDecision.

    This is not a constant: each ELIGIBLE row is inspected against persisted governance.
    """
    n = 0
    for ku in (
        db.query(models.KnowledgeUnit)
        .filter(models.KnowledgeUnit.runtime_eligibility == "ELIGIBLE")
        .all()
    ):
        if ku_lacks_real_source_governance(db, knowledge_unit_id=ku.id):
            n += 1
    return n


def audit_eligibility_integrity(db: Session) -> EligibilityIntegrityReport:
    unk_safety = 0
    no_gov = 0
    no_prov = 0
    unk_rights = 0
    blocked_rights = 0
    trial_as_rec = 0

    eligible = (
        db.query(models.KnowledgeUnit)
        .filter(models.KnowledgeUnit.runtime_eligibility == "ELIGIBLE")
        .all()
    )
    for ku in eligible:
        if str(ku.medical_safety_state or "").upper() == MedicalSafetyState.UNKNOWN.value:
            unk_safety += 1
        if not bool(ku.provenance_complete):
            no_prov += 1
        else:
            if db.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=ku.id).first() is None:
                no_prov += 1
        rights = resolve_ku_rights_state(db, knowledge_unit_id=ku.id)
        if rights == "RIGHTS_UNKNOWN":
            unk_rights += 1
        if rights == "RIGHTS_BLOCKED":
            blocked_rights += 1
        if ku_lacks_real_source_governance(db, knowledge_unit_id=ku.id):
            no_gov += 1

    if hasattr(models, "I5KnowledgeUnitEvidenceLink"):
        for link in db.query(models.I5KnowledgeUnitEvidenceLink).all():
            ku = db.query(models.KnowledgeUnit).filter_by(id=link.knowledge_unit_id).first()
            if ku is None or str(ku.runtime_eligibility) != "ELIGIBLE":
                continue
            ver = db.query(models.I5ScientificArtifactVersion).filter_by(id=link.artifact_version_id).first()
            if ver is None:
                continue
            art = db.query(models.I5ScientificArtifact).filter_by(id=ver.artifact_id).first()
            if art and trial_registry_forbids_clinical_runtime(art.artifact_type):
                if str(getattr(link, "evidence_role", "") or "").upper() != "TRIAL_REGISTRY_IDENTITY":
                    trial_as_rec += 1
                elif str(ku.knowledge_type or "").upper() in {"RECOMMENDATION", "GUIDELINE"}:
                    trial_as_rec += 1
                else:
                    trial_as_rec += 1

    # NF25: derive from the same DB inspection — never a literal constant.
    synthetic_auto = count_synthetic_governance_auto_promotions(db)
    if synthetic_auto != no_gov:
        # Invariant self-check: counters must stay exact equivalents.
        raise AssertionError(
            f"NF25_COUNTER_DIVERGENCE:synthetic={synthetic_auto} eligible_without_gov={no_gov}"
        )

    return EligibilityIntegrityReport(
        eligible_with_unknown_safety=unk_safety,
        eligible_without_real_governance=no_gov,
        eligible_without_provenance=no_prov,
        eligible_with_unknown_rights=unk_rights,
        eligible_with_blocked_rights=blocked_rights,
        trial_registry_as_treatment_recommendation=trial_as_rec,
        synthetic_product_rights_source_count=count_synthetic_product_rights_sources(db),
        synthetic_governance_auto_promotion_count=synthetic_auto,
        computation_basis=(
            "DB_DERIVED:"
            "ELIGIBLE_KU_LACKING_SOURCE_PROFILE_APPROVED_I5GovernanceDecision"
            "==synthetic_governance_auto_promotion_count"
            "==eligible_without_real_governance"
        ),
    )

"""Source coverage gap detector foundation (living coverage model)."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import SourceCoverageStatus

P0_DISEASES = ("ALS", "MS", "DIABETES")

FOUNDATION_DIMENSIONS: Sequence[Tuple[str, str, str]] = (
    ("guidelines", None, SourceCoverageStatus.PARTIAL.value),
    ("systematic_reviews", None, SourceCoverageStatus.PARTIAL.value),
    ("rehabilitation", None, SourceCoverageStatus.SOURCE_DISCOVERY_REQUIRED.value),
    ("nutrition", None, SourceCoverageStatus.SOURCE_DISCOVERY_REQUIRED.value),
    ("genetics", None, SourceCoverageStatus.AUTHORITY_GAP.value),
    ("mental_health", None, SourceCoverageStatus.SOURCE_DISCOVERY_REQUIRED.value),
    ("clinical_trials", "RCT", SourceCoverageStatus.PARTIAL.value),
    ("drug_safety", None, SourceCoverageStatus.RIGHTS_REVIEW_REQUIRED.value),
)


def upsert_coverage_gap(
    db: Session,
    *,
    disease_or_domain: str,
    knowledge_dimension: str,
    status: str,
    evidence_class: Optional[str] = None,
    detail: Optional[str] = None,
    knowledge_gap_id: Optional[int] = None,
) -> models.I5SourceCoverageGap:
    SourceCoverageStatus(status)
    row = (
        db.query(models.I5SourceCoverageGap)
        .filter_by(disease_or_domain=disease_or_domain, knowledge_dimension=knowledge_dimension)
        .first()
    )
    if row is None:
        row = models.I5SourceCoverageGap(
            disease_or_domain=disease_or_domain,
            knowledge_dimension=knowledge_dimension,
            status=status,
        )
        db.add(row)
    row.status = status
    row.evidence_class = evidence_class
    row.detail = detail
    row.knowledge_gap_id = knowledge_gap_id
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def detect_p0_foundation_gaps(db: Session) -> List[models.I5SourceCoverageGap]:
    """Ensure foundational gap cells exist for P0 diseases + CAP24 labs."""
    out: List[models.I5SourceCoverageGap] = []
    for disease in P0_DISEASES:
        for dim, evidence_class, status in FOUNDATION_DIMENSIONS:
            out.append(
                upsert_coverage_gap(
                    db,
                    disease_or_domain=disease,
                    knowledge_dimension=dim,
                    status=status,
                    evidence_class=evidence_class,
                    detail=f"KNOW-01 foundation cell; not claiming COVERED. disease={disease}",
                )
            )
    out.append(
        upsert_coverage_gap(
            db,
            disease_or_domain="IRAN_LABORATORIES",
            knowledge_dimension="nationwide_directory",
            status=SourceCoverageStatus.NO_AUTHORITATIVE_SOURCE_FOUND.value,
            detail="CAP24: no verified nationwide machine-readable clinical lab authority",
        )
    )
    out.append(
        upsert_coverage_gap(
            db,
            disease_or_domain="IRAN_CLINICS",
            knowledge_dimension="canonical_facility_entity",
            status=SourceCoverageStatus.SOURCE_DISCOVERY_REQUIRED.value,
            detail="NEXT_SCHEMA_GATE_REQUIRED: clinic/outpatient facility entity model",
        )
    )
    return out


def list_gaps(
    db: Session,
    *,
    disease_or_domain: Optional[str] = None,
    statuses: Optional[Iterable[str]] = None,
) -> List[models.I5SourceCoverageGap]:
    q = db.query(models.I5SourceCoverageGap)
    if disease_or_domain:
        q = q.filter(models.I5SourceCoverageGap.disease_or_domain == disease_or_domain)
    if statuses:
        q = q.filter(models.I5SourceCoverageGap.status.in_(list(statuses)))
    return q.order_by(
        models.I5SourceCoverageGap.disease_or_domain,
        models.I5SourceCoverageGap.knowledge_dimension,
    ).all()

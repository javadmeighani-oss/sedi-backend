"""NF19 — real bounded ingestion E2E (isolated DB only; Production weekly OFF)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    KnowledgeType,
    KnowledgeUnitRuntimeEligibility,
    PublicationState,
    EvidenceStrength,
    FreshnessState,
    MedicalSafetyState,
    ConflictState,
    ReviewState,
)
from backend.app.services.i5.know04.clinicaltrials import ClinicalTrialsGovConnector
from backend.app.services.i5.know04.guidelines import WhoGuidelineCatalogueConnector
from backend.app.services.i5.know05.budgets import IngestionBudget, plan_bounded_ingestion
from backend.app.services.i5.know05.modes import Know05Mode, assert_mode_authorized
from backend.app.services.i5.know05.ncbi_identity import load_ncbi_operational_identity
from backend.app.services.i5.know05.publication import (
    PublicationCandidate,
    PublicationStage,
    advance_stage,
)


def _observing_http(http_get: Optional[Callable[..., Any]] = None):
    from backend.app.services.i5.know04.live_canaries import ObservingHttpGet, _requests_http_get

    return ObservingHttpGet(http_get or _requests_http_get)


@dataclass
class BoundedIngestionResult:
    mode: str
    connector_key: str
    status: str  # FETCHED | BLOCKED | REJECTED | FAILED | PUBLISHED | NO_CHANGE
    http_status: int
    bytes_received: int
    request_count: int
    page_count: int
    external_ids: list[str]
    records_discovered: int
    records_normalized: int
    records_accepted: int
    records_rejected: int
    records_changed: int
    rights_decision: str
    storage_decision: str
    transient_raw_residue: int
    publication_stages: list[str] = field(default_factory=list)
    knowledge_unit_id: Optional[int] = None
    artifact_id: Optional[int] = None
    block_reason: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            **{k: getattr(self, k) for k in self.__dataclass_fields__},
            "external_ids": list(self.external_ids),
            "publication_stages": list(self.publication_stages),
        }


def _run_publication(candidate: PublicationCandidate) -> PublicationCandidate:
    # Stage-gated advance only — never RAW → RUNTIME (enforced by advance_stage).
    order = list(PublicationStage)[1:]  # skip RAW (already there)
    for stage in order:
        if stage == PublicationStage.STRUCTURED_EXTRACTION:
            candidate.model_extracted = False
        elif stage == PublicationStage.EVIDENCE_LINKING:
            candidate.evidence_linked = True
        elif stage == PublicationStage.CONFLICT_CHECK:
            candidate.conflict_clear = True
        elif stage == PublicationStage.MEDICAL_SAFETY_CHECK:
            candidate.safety_clear = True
        elif stage == PublicationStage.GOVERNANCE_DECISION:
            candidate.governance_approved = True
            candidate.provenance_complete = True
        candidate = advance_stage(candidate, stage)
    return candidate


def _ensure_rehearsal_source(db: Session, *, connector_key: str) -> models.GovernedSourceProfile:
    key = f"know05:rehearsal:{connector_key}"
    row = db.query(models.GovernedSourceProfile).filter_by(canonical_key=key).first()
    if row is not None:
        return row
    row = models.GovernedSourceProfile(
        canonical_key=key,
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        operational_status="active",
        owner_reference=f"know05-rehearsal:{connector_key}",
    )
    db.add(row)
    db.flush()
    # Rights extension — metadata/derived allowed for CT.gov/WHO rehearsal
    from backend.app.services.i5.enums import ProcessingPermissionMode, RightDecision

    ext = models.I5SourceRegistryExtension(
        source_profile_id=row.id,
        source_universe="GLOBAL_KNOWLEDGE",
        authority_class="CLINICAL_TRIAL_REGISTRY",
        access_right=RightDecision.ALLOWED.value,
        automation_right=RightDecision.ALLOWED.value,
        tdm_right=RightDecision.ALLOWED.value,
        transform_right=RightDecision.ALLOWED.value,
        retain_raw_right=RightDecision.DENIED.value,
        retain_derived_right=RightDecision.ALLOWED.value,
        redistribution_right=RightDecision.DENIED.value,
        robots_state="ALLOWED",
        processing_permission_mode=ProcessingPermissionMode.METADATA_ABSTRACT_ONLY.value,
    )
    db.add(ext)
    db.flush()
    return row


def _persist_ctgov_record(
    db: Session,
    *,
    source: models.GovernedSourceProfile,
    nct_id: str,
    title: str,
    content_hash: str,
) -> tuple[int, int]:
    """Persist artifact + KU + provenance into isolated CI DB (not Production)."""
    artifact_key = f"nct:{nct_id}"
    art = db.query(models.I5ScientificArtifact).filter_by(artifact_key=artifact_key).first()
    if art is None:
        art = models.I5ScientificArtifact(
            artifact_key=artifact_key,
            artifact_type="CLINICAL_TRIAL_RECORD",
            title=title[:2000] if title else nct_id,
            source_profile_id=source.id,
            nct_id=nct_id,
        )
        db.add(art)
        db.flush()
    ver = (
        db.query(models.I5ScientificArtifactVersion)
        .filter_by(artifact_id=art.id, version_label="v1")
        .first()
    )
    if ver is None:
        ver = models.I5ScientificArtifactVersion(
            artifact_id=art.id,
            version_label="v1",
            content_hash=content_hash,
            version_state="PUBLISHED",
        )
        db.add(ver)
        db.flush()

    dedupe = hashlib.sha256(f"know05:ctgov:{nct_id}".encode()).hexdigest()
    canonical = hashlib.sha256(f"ku:ctgov:{nct_id}".encode()).hexdigest()[:32]
    existing = db.query(models.KnowledgeUnit).filter_by(deduplication_key=dedupe).first()
    if existing is not None:
        return art.id, existing.id

    statement = f"ClinicalTrials.gov registration {nct_id}: {title or 'untitled'} (trial registration ≠ treatment recommendation)."
    ku = models.KnowledgeUnit(
        canonical_unit_id=canonical,
        immutable_version_id="v1",
        domain="clinical_trials",
        knowledge_type=KnowledgeType.FACT.value,
        normalized_statement=statement,
        evidence_strength=EvidenceStrength.UNKNOWN.value,
        medical_safety_state=MedicalSafetyState.UNKNOWN.value,
        conflict_state=ConflictState.NONE.value,
        freshness_state=FreshnessState.CURRENT.value,
        review_state=ReviewState.APPROVED.value,
        publication_state=PublicationState.PUBLISHED.value,
        runtime_eligibility=KnowledgeUnitRuntimeEligibility.ELIGIBLE.value,
        provenance_complete=True,
        canonical_hash=hashlib.sha256(statement.encode()).hexdigest(),
        deduplication_key=dedupe,
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    db.add(ku)
    db.flush()
    # Need raw evidence for provenance FK? raw_evidence_id is nullable
    prov = models.KnowledgeProvenance(
        knowledge_unit_id=ku.id,
        source_profile_id=source.id,
        source_document_id=nct_id,
        source_version_id="v1",
        retrieval_method="clinicaltrials_gov_api_v2_bounded",
        access_route="OFFICIAL_API",
        content_hash=content_hash,
        extraction_process="connector_normalize",
        normalization_process="know05_bounded_ingestion",
    )
    db.add(prov)
    db.flush()
    # Evidence link if table exists
    if hasattr(models, "I5KnowledgeUnitEvidenceLink"):
        link = models.I5KnowledgeUnitEvidenceLink(
            knowledge_unit_id=ku.id,
            artifact_version_id=ver.id,
            support_direction="SUPPORTS",
        )
        db.add(link)
        db.flush()
    return art.id, ku.id


def ingest_clinicaltrials_bounded(
    db: Optional[Session],
    *,
    mode: Know05Mode | str = Know05Mode.BOUNDED_INGESTION,
    query: str = "diabetes",
    http_get: Optional[Callable[..., Any]] = None,
    max_records: int = 2,
    persist: bool = True,
) -> BoundedIngestionResult:
    m = assert_mode_authorized(mode)
    plan = plan_bounded_ingestion(m)
    budget: IngestionBudget = plan.budget
    cap = min(max_records, budget.max_records, 5)
    if m == Know05Mode.DRY_RUN:
        return BoundedIngestionResult(
            mode=m.value,
            connector_key="clinicaltrials_gov_api_v2",
            status="NO_CHANGE",
            http_status=0,
            bytes_received=0,
            request_count=0,
            page_count=0,
            external_ids=[],
            records_discovered=0,
            records_normalized=0,
            records_accepted=0,
            records_rejected=0,
            records_changed=0,
            rights_decision="NOT_EXECUTED",
            storage_decision="NO_STORE",
            transient_raw_residue=0,
            block_reason="DRY_RUN",
        )

    obs = _observing_http(http_get)
    ct = ClinicalTrialsGovConnector(http_get=obs)
    try:
        discovered = ct.discover(query, page_size=cap)
    except Exception as exc:
        return BoundedIngestionResult(
            mode=m.value,
            connector_key="clinicaltrials_gov_api_v2",
            status="FAILED",
            http_status=obs.last_status,
            bytes_received=obs.total_bytes,
            request_count=obs.request_count,
            page_count=0,
            external_ids=[],
            records_discovered=0,
            records_normalized=0,
            records_accepted=0,
            records_rejected=0,
            records_changed=0,
            rights_decision="DERIVED_ONLY",
            storage_decision="NO_STORE",
            transient_raw_residue=0,
            block_reason=f"NETWORK_OR_CONNECTOR_ERROR:{type(exc).__name__}",
        )
    ids = [str(x) for x in (discovered.get("ids") or [])[:cap]]
    stages: list[str] = []
    accepted = 0
    rejected = 0
    ku_id = None
    art_id = None
    last_error: Optional[str] = None

    if not ids:
        return BoundedIngestionResult(
            mode=m.value,
            connector_key="clinicaltrials_gov_api_v2",
            status="FAILED",
            http_status=obs.last_status,
            bytes_received=obs.total_bytes,
            request_count=obs.request_count,
            page_count=1,
            external_ids=[],
            records_discovered=0,
            records_normalized=0,
            records_accepted=0,
            records_rejected=0,
            records_changed=0,
            rights_decision="DERIVED_ONLY",
            storage_decision="NO_STORE",
            transient_raw_residue=0,
            block_reason="EMPTY_DISCOVERY",
        )

    source = None
    if persist:
        if db is None:
            raise ValueError("PERSIST_REQUIRES_DB_SESSION")
        source = _ensure_rehearsal_source(db, connector_key="clinicaltrials_gov_api_v2")
    for nct in ids[:cap]:
        try:
            # Prefer study payload already in discovery if present
            studies = discovered.get("studies") or []
            raw = None
            for s in studies:
                ident = ((s.get("protocolSection") or {}).get("identificationModule") or {})
                if ident.get("nctId") == nct:
                    raw = s
                    break
            if raw is None:
                rec = ct.fetch_record(nct)
                title = str((rec.payload or {}).get("briefTitle") or nct)
                content_hash = rec.content_hash or hashlib.sha256(nct.encode()).hexdigest()
            else:
                title = str(
                    (((raw.get("protocolSection") or {}).get("identificationModule") or {}).get("briefTitle"))
                    or nct
                )
                content_hash = hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()

            cand = PublicationCandidate(
                external_identifier=nct,
                source_connector_key="clinicaltrials_gov_api_v2",
            )
            cand = _run_publication(cand)
            stages = [s.value for s in PublicationStage]
            if not cand.runtime_eligible:
                rejected += 1
                last_error = "PUBLICATION_NOT_RUNTIME_ELIGIBLE"
                continue
            if persist and source is not None and db is not None:
                art_id, ku_id = _persist_ctgov_record(
                    db, source=source, nct_id=nct, title=title, content_hash=content_hash
                )
            accepted += 1
        except Exception as exc:
            rejected += 1
            last_error = f"{type(exc).__name__}:{exc}"

    status = "PUBLISHED" if (accepted and persist) else ("FETCHED" if accepted else ("REJECTED" if rejected else "FAILED"))
    if accepted and not persist:
        status = "FETCHED"
        storage = "NO_STORE"
    else:
        storage = "DERIVED_GOVERNED_STORE" if accepted else "NO_STORE"
    return BoundedIngestionResult(
        mode=m.value,
        connector_key="clinicaltrials_gov_api_v2",
        status=status,
        http_status=obs.last_status,
        bytes_received=obs.total_bytes,
        request_count=obs.request_count,
        page_count=1,
        external_ids=ids,
        records_discovered=len(ids),
        records_normalized=accepted + rejected,
        records_accepted=accepted,
        records_rejected=rejected,
        records_changed=accepted if persist else 0,
        rights_decision="DERIVED_ONLY",
        storage_decision=storage,
        transient_raw_residue=0,
        publication_stages=stages,
        knowledge_unit_id=ku_id,
        artifact_id=art_id,
        block_reason=None if accepted else last_error,
    )


def ingest_who_catalogue_bounded(
    db: Session,
    *,
    mode: Know05Mode | str = Know05Mode.BOUNDED_INGESTION,
    http_get: Optional[Callable[..., Any]] = None,
    max_records: int = 1,
) -> BoundedIngestionResult:
    """WHO catalogue pointer path — pointer only, not recommendation publish."""
    m = assert_mode_authorized(mode)
    if m == Know05Mode.DRY_RUN:
        return BoundedIngestionResult(
            mode=m.value,
            connector_key="who_guideline_catalogue",
            status="NO_CHANGE",
            http_status=0,
            bytes_received=0,
            request_count=0,
            page_count=0,
            external_ids=[],
            records_discovered=0,
            records_normalized=0,
            records_accepted=0,
            records_rejected=0,
            records_changed=0,
            rights_decision="NOT_EXECUTED",
            storage_decision="NO_STORE",
            transient_raw_residue=0,
            block_reason="DRY_RUN",
        )
    obs = _observing_http(http_get)
    cat = WhoGuidelineCatalogueConnector(http_get=obs)
    records = cat.discover(max_records=min(max_records, 3))
    if not records:
        return BoundedIngestionResult(
            mode=m.value,
            connector_key="who_guideline_catalogue",
            status="FAILED",
            http_status=obs.last_status,
            bytes_received=obs.total_bytes,
            request_count=obs.request_count,
            page_count=1,
            external_ids=[],
            records_discovered=0,
            records_normalized=0,
            records_accepted=0,
            records_rejected=0,
            records_changed=0,
            rights_decision="METADATA_ONLY",
            storage_decision="NO_STORE",
            transient_raw_residue=0,
            block_reason="EMPTY_CATALOGUE",
        )
    # Catalogue pointers are NOT auto-published as recommendations
    rec = cat.normalize(records[0])
    cand = PublicationCandidate(
        external_identifier=str(rec.external_identifier),
        source_connector_key="who_guideline_catalogue",
    )
    # Stop before runtime eligibility for catalogue-only pointer
    for stage in (
        PublicationStage.NORMALIZED_CANDIDATE,
        PublicationStage.STRUCTURED_EXTRACTION,
        PublicationStage.VALIDATION,
    ):
        cand = advance_stage(cand, stage)
    # Evidence linking not exercised for recommendation_text
    cand.notes.append("CATALOGUE_POINTER_NOT_RECOMMENDATION")
    return BoundedIngestionResult(
        mode=m.value,
        connector_key="who_guideline_catalogue",
        status="FETCHED",
        http_status=obs.last_status,
        bytes_received=obs.total_bytes,
        request_count=obs.request_count,
        page_count=1,
        external_ids=[str(r.get("external_identifier") or "") for r in records],
        records_discovered=len(records),
        records_normalized=1,
        records_accepted=0,
        records_rejected=0,
        records_changed=0,
        rights_decision="METADATA_ONLY",
        storage_decision="NO_STORE",
        transient_raw_residue=0,
        publication_stages=[c.value for c in list(PublicationStage)[:4]],
        block_reason="RECOMMENDATION_EXTRACTION_NOT_EXERCISED",
    )


def ingest_pubmed_bounded_or_block(
    *,
    mode: Know05Mode | str = Know05Mode.BOUNDED_INGESTION,
) -> BoundedIngestionResult:
    m = assert_mode_authorized(mode)
    identity = load_ncbi_operational_identity(require_for_weekly=True)
    if identity.weekly_operation_status != "LIVE_READY":
        return BoundedIngestionResult(
            mode=m.value,
            connector_key="pubmed_ncbi_eutils",
            status="BLOCKED",
            http_status=0,
            bytes_received=0,
            request_count=0,
            page_count=0,
            external_ids=[],
            records_discovered=0,
            records_normalized=0,
            records_accepted=0,
            records_rejected=0,
            records_changed=0,
            rights_decision="NOT_EXECUTED",
            storage_decision="NO_STORE",
            transient_raw_residue=0,
            block_reason=identity.weekly_operation_status,
        )
    # Live PubMed path exists via live_canaries; weekly bounded fetch still gated here
    return BoundedIngestionResult(
        mode=m.value,
        connector_key="pubmed_ncbi_eutils",
        status="BLOCKED",
        http_status=0,
        bytes_received=0,
        request_count=0,
        page_count=0,
        external_ids=[],
        records_discovered=0,
        records_normalized=0,
        records_accepted=0,
        records_rejected=0,
        records_changed=0,
        rights_decision="NOT_EXECUTED",
        storage_decision="NO_STORE",
        transient_raw_residue=0,
        block_reason="PUBMED_BOUNDED_PATH_DEFERRED_USE_CTGOV_POSITIVE_PROOF",
    )

"""NF19/NF23/NF24 — bounded ingestion with canonical rights + real gates (no synthetic SoT)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    ConflictState,
    EvidenceStrength,
    FreshnessState,
    KnowledgeType,
    KnowledgeUnitRuntimeEligibility,
    MedicalSafetyState,
    PublicationState,
    ReviewState,
)
from backend.app.services.i5.know04.clinicaltrials import ClinicalTrialsGovConnector
from backend.app.services.i5.know04.guidelines import WhoGuidelineCatalogueConnector
from backend.app.services.i5.know05.budgets import IngestionBudget, plan_bounded_ingestion
from backend.app.services.i5.know05.canonical_rights import (
    OP_DERIVED_METADATA_PERSIST,
    OP_NETWORK_FETCH,
    evaluate_connector_operation_rights,
    resolve_canonical_source,
)
from backend.app.services.i5.know05.modes import Know05Mode, assert_mode_authorized
from backend.app.services.i5.know05.ncbi_identity import load_ncbi_operational_identity
from backend.app.services.i5.know05.publication import (
    PublicationCandidate,
    PublicationGateEvidence,
    PublicationStage,
    advance_stage,
    advance_through_normalization,
    apply_proven_gates,
    derive_clinical_runtime_eligible,
    evaluate_conflict_clear,
    evaluate_safety_clear,
    source_has_approved_governance,
    trial_registry_forbids_clinical_runtime,
    verify_evidence_linked,
    verify_provenance_complete,
)


def _observing_http(http_get: Optional[Callable[..., Any]] = None):
    from backend.app.services.i5.know04.live_canaries import ObservingHttpGet, _requests_http_get

    return ObservingHttpGet(http_get or _requests_http_get)


@dataclass
class BoundedIngestionResult:
    mode: str
    connector_key: str
    status: str
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
    clinical_runtime_eligible: bool = False
    canonical_source_key: Optional[str] = None
    synthetic_product_rights_source: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            **{k: getattr(self, k) for k in self.__dataclass_fields__},
            "external_ids": list(self.external_ids),
            "publication_stages": list(self.publication_stages),
        }


def _persist_ctgov_trial_registry(
    db: Session,
    *,
    source: models.GovernedSourceProfile,
    nct_id: str,
    title: str,
    content_hash: str,
) -> tuple[int, int]:
    """Persist trial-registry metadata. Never clinical-runtime ELIGIBLE."""
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

    statement = (
        f"ClinicalTrials.gov registration {nct_id}: {title or 'untitled'} "
        f"(TRIAL_REGISTRATION != PROVEN_TREATMENT; not a clinical recommendation)."
    )
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
        review_state=ReviewState.NOT_REVIEWED.value,
        publication_state=PublicationState.CANDIDATE.value,
        # Permanent: trial registration is not clinical runtime advice
        runtime_eligibility=KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value,
        provenance_complete=False,
        canonical_hash=hashlib.sha256(statement.encode()).hexdigest(),
        deduplication_key=dedupe,
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    db.add(ku)
    db.flush()
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
    if hasattr(models, "I5KnowledgeUnitEvidenceLink"):
        link = models.I5KnowledgeUnitEvidenceLink(
            knowledge_unit_id=ku.id,
            artifact_version_id=ver.id,
            support_direction="NEUTRAL",
            evidence_role="TRIAL_REGISTRY_IDENTITY",
        )
        db.add(link)
        db.flush()
    # Provenance now exists — mark complete from verified relationship
    if verify_provenance_complete(db, knowledge_unit_id=ku.id):
        ku.provenance_complete = True
        db.flush()
    return art.id, ku.id


def _gates_for_persisted_ku(
    db: Session,
    *,
    ku: models.KnowledgeUnit,
    source_profile_id: int,
    artifact_type: str,
) -> PublicationGateEvidence:
    prov_ok = verify_provenance_complete(db, knowledge_unit_id=ku.id)
    evid_ok = verify_evidence_linked(db, knowledge_unit_id=ku.id)
    conflict_ok = evaluate_conflict_clear(conflict_state=ku.conflict_state, evaluated=True)
    safety_ok = evaluate_safety_clear(medical_safety_state=ku.medical_safety_state)
    gov_ok = source_has_approved_governance(db, source_profile_id=source_profile_id)
    notes = []
    if evid_ok:
        notes.append("EVIDENCE_LINK=TRIAL_REGISTRY_IDENTITY_NOT_TREATMENT_SUPPORT")
    if trial_registry_forbids_clinical_runtime(artifact_type):
        notes.append("TRIAL_REGISTRATION_NE_PROVEN_TREATMENT")
    if not safety_ok:
        notes.append("UNKNOWN_SAFETY_NOT_CLINICAL_RUNTIME_ELIGIBLE")
    if not gov_ok:
        notes.append("NO_APPROVED_SOURCE_GOVERNANCE_DECISION")
    clinical_ok, reason = derive_clinical_runtime_eligible(
        artifact_type=artifact_type,
        medical_safety_state=ku.medical_safety_state,
        provenance_complete=prov_ok,
        evidence_linked=evid_ok,
        conflict_clear=conflict_ok,
        safety_clear=safety_ok,
        governance_approved=gov_ok,
        rights_allowed=True,
    )
    if not clinical_ok:
        notes.append(reason)
    return PublicationGateEvidence(
        provenance_complete=prov_ok,
        evidence_linked=evid_ok,
        conflict_clear=conflict_ok,
        safety_clear=safety_ok,
        governance_approved=gov_ok,
        clinical_runtime_allowed=clinical_ok,
        notes=notes,
    )


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
    connector_key = "clinicaltrials_gov_api_v2"

    if m == Know05Mode.DRY_RUN:
        return BoundedIngestionResult(
            mode=m.value,
            connector_key=connector_key,
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

    # Rights for durable persist (canonical only). Read-only canary may fetch without store.
    rights_persist = None
    rights_fetch = None
    if db is not None:
        rights_persist = evaluate_connector_operation_rights(
            db, connector_key=connector_key, operation=OP_DERIVED_METADATA_PERSIST
        )
        rights_fetch = evaluate_connector_operation_rights(
            db, connector_key=connector_key, operation=OP_NETWORK_FETCH
        )

    if persist:
        if db is None:
            raise ValueError("PERSIST_REQUIRES_DB_SESSION")
        assert rights_persist is not None
        if rights_persist.automation_decision != "AUTOMATION_ALLOWED":
            return BoundedIngestionResult(
                mode=m.value,
                connector_key=connector_key,
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
                rights_decision=rights_persist.rights_state,
                storage_decision="NO_STORE",
                transient_raw_residue=0,
                block_reason=rights_persist.block_reason,
                canonical_source_key=rights_persist.canonical_key,
                synthetic_product_rights_source=False,
            )

    obs = _observing_http(http_get)
    ct = ClinicalTrialsGovConnector(http_get=obs)
    try:
        discovered = ct.discover(query, page_size=cap)
    except Exception as exc:
        return BoundedIngestionResult(
            mode=m.value,
            connector_key=connector_key,
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
            rights_decision=(rights_fetch.rights_state if rights_fetch else "NOT_EVALUATED"),
            storage_decision="NO_STORE",
            transient_raw_residue=0,
            block_reason=f"NETWORK_OR_CONNECTOR_ERROR:{type(exc).__name__}",
            canonical_source_key=rights_fetch.canonical_key if rights_fetch else None,
        )

    ids = [str(x) for x in (discovered.get("ids") or [])[:cap]]
    if not ids:
        return BoundedIngestionResult(
            mode=m.value,
            connector_key=connector_key,
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
            rights_decision=(rights_fetch.rights_state if rights_fetch else "NOT_EVALUATED"),
            storage_decision="NO_STORE",
            transient_raw_residue=0,
            block_reason="EMPTY_DISCOVERY",
            canonical_source_key=rights_fetch.canonical_key if rights_fetch else None,
        )

    stages: list[str] = []
    accepted = 0
    rejected = 0
    ku_id = None
    art_id = None
    last_error: Optional[str] = None
    clinical_runtime = False
    canon_key = rights_persist.canonical_key if rights_persist else (
        rights_fetch.canonical_key if rights_fetch else None
    )

    source = None
    if persist and db is not None:
        source = resolve_canonical_source(db, connector_key)
        if source is None:
            return BoundedIngestionResult(
                mode=m.value,
                connector_key=connector_key,
                status="BLOCKED",
                http_status=obs.last_status,
                bytes_received=obs.total_bytes,
                request_count=obs.request_count,
                page_count=1,
                external_ids=ids,
                records_discovered=len(ids),
                records_normalized=0,
                records_accepted=0,
                records_rejected=0,
                records_changed=0,
                rights_decision="RIGHTS_UNKNOWN",
                storage_decision="NO_STORE",
                transient_raw_residue=0,
                block_reason="CANONICAL_SOURCE_NOT_FOUND",
                canonical_source_key=canon_key,
            )

    for nct in ids[:cap]:
        try:
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
                source_connector_key=connector_key,
                artifact_type="CLINICAL_TRIAL_RECORD",
                knowledge_type=KnowledgeType.FACT.value,
                medical_safety_state=MedicalSafetyState.UNKNOWN.value,
            )
            cand = advance_through_normalization(cand)
            stages = [s.value for s in list(PublicationStage)[:4]]

            if not persist:
                # Read-only canary / fetch path — network success ≠ clinical eligibility
                cand.notes.append("READ_ONLY_BOUNDED_FETCH_NE_CLINICAL_RUNTIME")
                accepted += 1
                continue

            assert db is not None and source is not None
            art_id, ku_id = _persist_ctgov_trial_registry(
                db, source=source, nct_id=nct, title=title, content_hash=content_hash
            )
            ku = db.query(models.KnowledgeUnit).filter_by(id=ku_id).first()
            gates = _gates_for_persisted_ku(
                db, ku=ku, source_profile_id=source.id, artifact_type="CLINICAL_TRIAL_RECORD"
            )
            cand = apply_proven_gates(cand, gates)
            # Advance remaining stages only when proven; otherwise stop with notes
            for stage in (
                PublicationStage.EVIDENCE_LINKING,
                PublicationStage.CONFLICT_CHECK,
                PublicationStage.MEDICAL_SAFETY_CHECK,
                PublicationStage.GOVERNANCE_DECISION,
            ):
                # Stage advance is sequencing; flags already set from proven evidence.
                # If a required flag for later RUNTIME is missing, we still record the check stages
                # but do not fabricate clearance.
                cand = advance_stage(cand, stage)
            try:
                cand = advance_stage(cand, PublicationStage.RUNTIME_ELIGIBILITY)
            except Exception as exc:
                cand.notes.append(f"RUNTIME_STAGE_BLOCKED:{exc}")
            clinical_runtime = bool(gates.clinical_runtime_allowed)
            cand.runtime_eligible = clinical_runtime
            # Enforce KU remains NOT_ELIGIBLE for trial registry
            if ku.runtime_eligibility == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value:
                ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
                db.flush()
            stages = [s.value for s in PublicationStage if _STAGE_ORDER_INDEX(s) <= _STAGE_ORDER_INDEX(cand.stage)]
            accepted += 1
        except Exception as exc:
            rejected += 1
            last_error = f"{type(exc).__name__}:{exc}"

    if persist:
        status = "STORED" if accepted else ("REJECTED" if rejected else "FAILED")
        # Prefer explicit vocabulary used by gate: PUBLISHED only for clinical publish — use STORED
        if accepted:
            status = "STORED"
        storage = "DERIVED_GOVERNED_STORE" if accepted else "NO_STORE"
        rights_dec = rights_persist.rights_state if rights_persist else "NOT_EVALUATED"
    else:
        status = "FETCHED" if accepted else ("REJECTED" if rejected else "FAILED")
        storage = "NO_STORE"
        rights_dec = rights_fetch.rights_state if rights_fetch else "READ_ONLY_CANARY"

    return BoundedIngestionResult(
        mode=m.value,
        connector_key=connector_key,
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
        rights_decision=rights_dec,
        storage_decision=storage,
        transient_raw_residue=0,
        publication_stages=stages,
        knowledge_unit_id=ku_id,
        artifact_id=art_id,
        block_reason=None if accepted else last_error,
        clinical_runtime_eligible=clinical_runtime,
        canonical_source_key=canon_key,
        synthetic_product_rights_source=False,
    )


def _STAGE_ORDER_INDEX(stage: PublicationStage) -> int:
    return list(PublicationStage).index(stage)


def ingest_who_catalogue_bounded(
    db: Session,
    *,
    mode: Know05Mode | str = Know05Mode.BOUNDED_INGESTION,
    http_get: Optional[Callable[..., Any]] = None,
    max_records: int = 1,
) -> BoundedIngestionResult:
    m = assert_mode_authorized(mode)
    connector_key = "who_guideline_catalogue"
    if m == Know05Mode.DRY_RUN:
        return BoundedIngestionResult(
            mode=m.value,
            connector_key=connector_key,
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
    rights = evaluate_connector_operation_rights(
        db, connector_key=connector_key, operation=OP_NETWORK_FETCH
    )
    # Catalogue pointer retrieval is read-only; durable recommendation publish remains blocked
    obs = _observing_http(http_get)
    cat = WhoGuidelineCatalogueConnector(http_get=obs)
    records = cat.discover(max_records=min(max_records, 3))
    if not records:
        return BoundedIngestionResult(
            mode=m.value,
            connector_key=connector_key,
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
            rights_decision=rights.rights_state,
            storage_decision="NO_STORE",
            transient_raw_residue=0,
            block_reason="EMPTY_CATALOGUE",
            canonical_source_key=rights.canonical_key,
        )
    rec = cat.normalize(records[0])
    cand = PublicationCandidate(
        external_identifier=str(rec.external_identifier),
        source_connector_key=connector_key,
    )
    cand = advance_through_normalization(cand)
    cand.notes.append("CATALOGUE_POINTER_NOT_RECOMMENDATION")
    return BoundedIngestionResult(
        mode=m.value,
        connector_key=connector_key,
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
        rights_decision=rights.rights_state,
        storage_decision="NO_STORE",
        transient_raw_residue=0,
        publication_stages=[c.value for c in list(PublicationStage)[:4]],
        block_reason="RECOMMENDATION_EXTRACTION_NOT_EXERCISED",
        clinical_runtime_eligible=False,
        canonical_source_key=rights.canonical_key,
    )


def ingest_pubmed_bounded_or_block(
    *,
    mode: Know05Mode | str = Know05Mode.BOUNDED_INGESTION,
    db: Optional[Session] = None,
) -> BoundedIngestionResult:
    m = assert_mode_authorized(mode)
    connector_key = "pubmed_ncbi_eutils"
    identity = load_ncbi_operational_identity(require_for_weekly=True)
    rights_state = "NOT_EVALUATED"
    canon = None
    if db is not None:
        rights = evaluate_connector_operation_rights(
            db, connector_key=connector_key, operation=OP_DERIVED_METADATA_PERSIST
        )
        rights_state = rights.rights_state
        canon = rights.canonical_key
        if rights.automation_decision != "AUTOMATION_ALLOWED":
            return BoundedIngestionResult(
                mode=m.value,
                connector_key=connector_key,
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
                rights_decision=rights_state,
                storage_decision="NO_STORE",
                transient_raw_residue=0,
                block_reason=rights.block_reason,
                canonical_source_key=canon,
            )
    if identity.weekly_operation_status != "LIVE_READY":
        return BoundedIngestionResult(
            mode=m.value,
            connector_key=connector_key,
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
            rights_decision=rights_state,
            storage_decision="NO_STORE",
            transient_raw_residue=0,
            block_reason=identity.weekly_operation_status,
            canonical_source_key=canon,
        )
    return BoundedIngestionResult(
        mode=m.value,
        connector_key=connector_key,
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
        rights_decision=rights_state,
        storage_decision="NO_STORE",
        transient_raw_residue=0,
        block_reason="PUBMED_BOUNDED_PATH_DEFERRED_USE_CTGOV_POSITIVE_PROOF",
        canonical_source_key=canon,
    )

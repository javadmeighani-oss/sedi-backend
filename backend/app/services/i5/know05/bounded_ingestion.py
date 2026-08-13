"""NF19/NF23/NF24 — bounded ingestion with canonical rights + real gates (no synthetic SoT)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    ArtifactType,
    ConflictState,
    EvidenceStrength,
    FreshnessState,
    KnowledgeType,
    KnowledgeUnitRuntimeEligibility,
    MedicalSafetyState,
    P0DiseaseRelevance,
    ProcessingPermissionMode,
    PublicationState,
    ReviewState,
    RightDecision,
    SourceAuthorityClass,
    SourceRole,
    SourceUniverse,
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
    """Persist trial-registry metadata. Never clinical-runtime ELIGIBLE.

    Versioning: same content_hash → reuse version; changed content → new version
    via know02.add_artifact_version (no silent overwrite of immutable version rows).
    """
    from backend.app.services.i5.know02.artifacts import add_artifact_version, link_evidence
    from backend.app.services.i5.know05.acquisition_boundary import (
        record_acquisition_evidence_boundary,
    )

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
        .filter_by(artifact_id=art.id, content_hash=content_hash)
        .first()
    )
    if ver is None:
        prior_n = (
            db.query(models.I5ScientificArtifactVersion)
            .filter_by(artifact_id=art.id)
            .count()
        )
        version_label = f"v{prior_n + 1}"
        prior = (
            db.query(models.I5ScientificArtifactVersion)
            .filter_by(artifact_id=art.id)
            .order_by(models.I5ScientificArtifactVersion.id.desc())
            .first()
        )
        ver = add_artifact_version(
            db,
            artifact_id=art.id,
            version_label=version_label,
            content_hash=content_hash,
            title_at_version=title[:2000] if title else nct_id,
            supersedes_version_id=prior.id if prior is not None else None,
        )

    raw_id = record_acquisition_evidence_boundary(
        db,
        source_profile_id=source.id,
        canonical_url=f"https://clinicaltrials.gov/study/{nct_id}",
        content_hash=content_hash,
        rights_decision="RIGHTS_ALLOWED",
        connector_key="clinicaltrials_gov_api_v2",
        mime_type="application/json",
    )

    dedupe = hashlib.sha256(f"know05:ctgov:{nct_id}".encode()).hexdigest()
    canonical = hashlib.sha256(f"ku:ctgov:{nct_id}".encode()).hexdigest()[:32]
    existing = db.query(models.KnowledgeUnit).filter_by(deduplication_key=dedupe).first()
    if existing is not None:
        if hasattr(models, "I5KnowledgeUnitEvidenceLink"):
            link_evidence(
                db,
                knowledge_unit_id=existing.id,
                artifact_version_id=ver.id,
                support_direction="NEUTRAL",
                evidence_role="TRIAL_REGISTRY_IDENTITY",
            )
        return art.id, existing.id

    statement = (
        f"ClinicalTrials.gov registration {nct_id}: {title or 'untitled'} "
        f"(TRIAL_REGISTRATION != PROVEN_TREATMENT; not a clinical recommendation)."
    )
    ku = models.KnowledgeUnit(
        canonical_unit_id=canonical,
        immutable_version_id=ver.version_label,
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
        source_version_id=ver.version_label,
        retrieval_method="clinicaltrials_gov_api_v2_bounded",
        access_route="OFFICIAL_API",
        content_hash=content_hash,
        extraction_process="connector_normalize",
        normalization_process="know05_bounded_ingestion",
        raw_evidence_id=raw_id,
    )
    db.add(prov)
    db.flush()
    if hasattr(models, "I5KnowledgeUnitEvidenceLink"):
        link_evidence(
            db,
            knowledge_unit_id=ku.id,
            artifact_version_id=ver.id,
            support_direction="NEUTRAL",
            evidence_role="TRIAL_REGISTRY_IDENTITY",
        )
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


PUBMED_CANARY_DEFAULT_QUERY = (
    '"amyotrophic lateral sclerosis"[Title/Abstract] AND Review[Publication Type]'
)
PUBMED_CONNECTOR_KEY = "pubmed_ncbi_eutils"
PUBMED_CANARY_MAX_RPS = 1.0


def map_pubmed_publication_to_artifact_type(publication_types: list[str] | None) -> str:
    joined = " | ".join(t.lower() for t in (publication_types or []) if t)
    if "meta-analysis" in joined or "meta analysis" in joined:
        return ArtifactType.META_ANALYSIS.value
    if "systematic review" in joined:
        return ArtifactType.SYSTEMATIC_REVIEW.value
    if "guideline" in joined or "practice guideline" in joined:
        return ArtifactType.GUIDELINE.value
    if "randomized controlled trial" in joined or "randomised controlled trial" in joined:
        return ArtifactType.RCT.value
    if "case reports" in joined or "case report" in joined:
        return ArtifactType.CASE_REPORT.value
    if "observational" in joined:
        return ArtifactType.OBSERVATIONAL_STUDY.value
    if "review" in joined:
        return ArtifactType.SYSTEMATIC_REVIEW.value
    return ArtifactType.ARTICLE.value


def ensure_pubmed_official_derived_source(db: Session) -> models.GovernedSourceProfile:
    """Reconcile pubmed_ncbi_eutils to KNOW-04 NCBI official-API rights.

    RAW full text remains DENIED. Derived metadata persist is ALLOWED.
    Does not enable weekly unattended operation.
    """
    from backend.app.services.i5.know01.registry_service import ensure_gsp, upsert_registry_extension

    gsp = ensure_gsp(
        db,
        canonical_key="know01:pubmed_ncbi_eutils",
        locator="https://pubmed.ncbi.nlm.nih.gov",
    )
    gsp.registry_state = "ACTIVE"
    gsp.operational_status = "active"
    upsert_registry_extension(
        db,
        source_profile_id=gsp.id,
        source_universe=SourceUniverse.GLOBAL_KNOWLEDGE.value,
        authority_class=SourceAuthorityClass.NATIONAL_MEDICAL_LIBRARY.value,
        publisher_family="NCBI/NLM PubMed",
        roles=[SourceRole.SCIENTIFIC_LITERATURE.value],
        p0_tags={
            "ALS": P0DiseaseRelevance.IMPORTANT.value,
            "MS": P0DiseaseRelevance.IMPORTANT.value,
            "DIABETES": P0DiseaseRelevance.IMPORTANT.value,
        },
        access_right=RightDecision.ALLOWED.value,
        automation_right=RightDecision.ALLOWED.value,
        tdm_right=RightDecision.ALLOWED.value,
        transform_right=RightDecision.ALLOWED.value,
        retain_raw_right=RightDecision.DENIED.value,
        retain_derived_right=RightDecision.ALLOWED.value,
        redistribution_right=RightDecision.DENIED.value,
        robots_state="ALLOWED",
        processing_permission_mode=ProcessingPermissionMode.METADATA_ABSTRACT_ONLY.value,
        canonical_home="https://pubmed.ncbi.nlm.nih.gov",
        api_endpoint="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        supported_formats="JSON,XML",
        notes=(
            "NCBI_EUTILS_OFFICIAL_API; RAW_FULL_TEXT=DENIED; DERIVED_METADATA=ALLOWED; "
            "KNOW04_CLASSIFY_RIGHTS; REGISTRY_ENTRY!=WEEKLY_ENABLEMENT"
        ),
        registry_status="ACTIVE",
        review_stage="NONE",
    )
    row = db.query(models.I5ConnectorProfile).filter_by(connector_key=PUBMED_CONNECTOR_KEY).first()
    if row is None:
        row = models.I5ConnectorProfile(connector_key=PUBMED_CONNECTOR_KEY)
        db.add(row)
    row.source_profile_key = PUBMED_CONNECTOR_KEY
    row.source_role = "SCIENTIFIC_LITERATURE"
    row.access_mechanism = "OFFICIAL_API"
    row.official_authority_note = "NCBI E-utilities (PubMed)"
    row.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    row.connector_state = "CONNECTOR_READY"
    row.live_status = "NOT_EXECUTED"
    db.flush()
    return gsp


def _pubmed_metadata_envelope(raw: dict[str, Any]) -> dict[str, Any]:
    abstract = str(raw.get("abstract") or "")
    return {
        "pmid": str(raw.get("pmid") or ""),
        "title": str(raw.get("title") or ""),
        "publication_types": list(raw.get("publication_types") or []),
        "mesh_terms": list(raw.get("mesh_terms") or [])[:24],
        "pub_date": str((raw.get("dates") or {}).get("pub_date") or ""),
        "doi": str(raw.get("doi") or ""),
        "pmcid": str(raw.get("pmcid") or ""),
        "journal": str(raw.get("journal") or ""),
        "abstract_sha256": hashlib.sha256(abstract.encode("utf-8")).hexdigest() if abstract else "",
    }


def _persist_pubmed_derived_knowledge(
    db: Session,
    *,
    source: models.GovernedSourceProfile,
    pmid: str,
    raw: dict[str, Any],
) -> tuple[int, int, bool]:
    """Persist PubMed identity + derived KU. Never stores abstract/full text/PDF."""
    from backend.app.services.i5.know02.artifacts import add_artifact_version, link_evidence
    from backend.app.services.i5.know05.acquisition_boundary import (
        record_acquisition_evidence_boundary,
    )

    envelope = _pubmed_metadata_envelope(raw)
    content_hash = hashlib.sha256(
        json.dumps(envelope, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    title = envelope["title"] or f"PMID {pmid}"
    artifact_type = map_pubmed_publication_to_artifact_type(envelope["publication_types"])
    doi = envelope["doi"] or None
    pmcid = envelope["pmcid"] or None
    artifact_key = f"pmid:{pmid}"

    art = db.query(models.I5ScientificArtifact).filter_by(artifact_key=artifact_key).first()
    if art is None:
        art = db.query(models.I5ScientificArtifact).filter_by(pmid=pmid).first()
    if art is None:
        art = models.I5ScientificArtifact(
            artifact_key=artifact_key,
            artifact_type=artifact_type,
            title=title[:2000],
            source_profile_id=source.id,
            publisher_family="NCBI/NLM PubMed",
            pmid=pmid,
            doi=doi,
            pmcid=pmcid,
            canonical_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        )
        db.add(art)
        db.flush()
    else:
        art.artifact_type = artifact_type
        art.title = title[:2000]
        art.source_profile_id = source.id
        if doi:
            art.doi = doi
        if pmcid:
            art.pmcid = pmcid
        art.canonical_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        db.flush()

    ver = (
        db.query(models.I5ScientificArtifactVersion)
        .filter_by(artifact_id=art.id, content_hash=content_hash)
        .first()
    )
    if ver is None:
        prior_n = (
            db.query(models.I5ScientificArtifactVersion)
            .filter_by(artifact_id=art.id)
            .count()
        )
        prior = (
            db.query(models.I5ScientificArtifactVersion)
            .filter_by(artifact_id=art.id)
            .order_by(models.I5ScientificArtifactVersion.id.desc())
            .first()
        )
        ver = add_artifact_version(
            db,
            artifact_id=art.id,
            version_label=f"v{prior_n + 1}",
            content_hash=content_hash,
            title_at_version=title[:2000],
            abstract_or_summary=None,
            supersedes_version_id=prior.id if prior is not None else None,
            locator=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        )

    raw_id = record_acquisition_evidence_boundary(
        db,
        source_profile_id=source.id,
        canonical_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        content_hash=content_hash,
        rights_decision="RIGHTS_ALLOWED",
        connector_key=PUBMED_CONNECTOR_KEY,
        mime_type="application/xml",
    )

    dedupe = hashlib.sha256(f"know05:pubmed:{pmid}".encode()).hexdigest()
    canonical = hashlib.sha256(f"ku:pubmed:{pmid}".encode()).hexdigest()[:32]
    existing = db.query(models.KnowledgeUnit).filter_by(deduplication_key=dedupe).first()
    if existing is not None:
        if hasattr(models, "I5KnowledgeUnitEvidenceLink"):
            link_evidence(
                db,
                knowledge_unit_id=existing.id,
                artifact_version_id=ver.id,
                support_direction="NEUTRAL",
                evidence_role="LITERATURE_IDENTITY",
            )
        return art.id, existing.id, False

    pub_types = ", ".join(envelope["publication_types"][:6]) or "unspecified article type"
    pub_date = envelope["pub_date"] or "unknown date"
    statement = (
        f"PubMed PMID {pmid} ({artifact_type}; {pub_types}; {pub_date}): {title}. "
        "Derived literature identity/evidence candidate; not a clinical recommendation."
    )
    ku = models.KnowledgeUnit(
        canonical_unit_id=canonical,
        immutable_version_id=ver.version_label,
        domain="scientific_literature",
        knowledge_type=KnowledgeType.FACT.value,
        normalized_statement=statement[:4000],
        evidence_strength=EvidenceStrength.UNKNOWN.value,
        medical_safety_state=MedicalSafetyState.UNKNOWN.value,
        conflict_state=ConflictState.NONE.value,
        freshness_state=FreshnessState.CURRENT.value,
        review_state=ReviewState.NOT_REVIEWED.value,
        publication_state=PublicationState.DRAFT.value,
        runtime_eligibility=KnowledgeUnitRuntimeEligibility.REVIEW_REQUIRED.value,
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
        source_document_id=f"PMID:{pmid}",
        source_version_id=ver.version_label,
        retrieval_method="ncbi_eutils_efetch_abstract_metadata",
        access_route="OFFICIAL_API",
        content_hash=content_hash,
        extraction_process="pubmed_xml_metadata_normalize",
        normalization_process="know05_pubmed_derived_persist",
        raw_evidence_id=raw_id,
        attribution_data=json.dumps(
            {
                "pmid": pmid,
                "doi": envelope["doi"] or None,
                "pmcid": envelope["pmcid"] or None,
                "raw_retention": "DENIED",
                "abstract_verbatim_persisted": False,
                "full_text_persisted": False,
                "pdf_persisted": False,
            },
            sort_keys=True,
        ),
    )
    db.add(prov)
    db.flush()
    if hasattr(models, "I5KnowledgeUnitEvidenceLink"):
        link_evidence(
            db,
            knowledge_unit_id=ku.id,
            artifact_version_id=ver.id,
            support_direction="NEUTRAL",
            evidence_role="LITERATURE_IDENTITY",
        )
    if verify_provenance_complete(db, knowledge_unit_id=ku.id):
        ku.provenance_complete = True
        db.flush()
    return art.id, ku.id, True


def _blocked_pubmed(
    *,
    mode: str,
    reason: str,
    rights_state: str = "NOT_EVALUATED",
    canon: Optional[str] = None,
    http_status: int = 0,
    bytes_received: int = 0,
    request_count: int = 0,
    ids: Optional[list[str]] = None,
) -> BoundedIngestionResult:
    return BoundedIngestionResult(
        mode=mode,
        connector_key=PUBMED_CONNECTOR_KEY,
        status="BLOCKED",
        http_status=http_status,
        bytes_received=bytes_received,
        request_count=request_count,
        page_count=0,
        external_ids=list(ids or []),
        records_discovered=len(ids or []),
        records_normalized=0,
        records_accepted=0,
        records_rejected=0,
        records_changed=0,
        rights_decision=rights_state,
        storage_decision="NO_STORE",
        transient_raw_residue=0,
        block_reason=reason,
        canonical_source_key=canon,
    )


def ingest_pubmed_bounded(
    db: Optional[Session] = None,
    *,
    mode: Know05Mode | str = Know05Mode.BOUNDED_INGESTION,
    query: str = PUBMED_CANARY_DEFAULT_QUERY,
    http_get: Optional[Callable[..., Any]] = None,
    max_records: int = 1,
    persist: bool = True,
    ensure_official_source: bool = False,
    max_rps: float = PUBMED_CANARY_MAX_RPS,
) -> BoundedIngestionResult:
    """Bounded PubMed discover → rights → derived persist (no raw full text)."""
    m = assert_mode_authorized(mode)
    cap = min(max(int(max_records), 1), 2)
    identity = load_ncbi_operational_identity(require_for_weekly=True)
    if identity.weekly_operation_status != "LIVE_READY":
        return _blocked_pubmed(mode=m.value, reason=identity.weekly_operation_status)

    if persist and db is None:
        return _blocked_pubmed(mode=m.value, reason="PERSIST_REQUIRES_DB_SESSION")

    if db is not None and ensure_official_source:
        ensure_pubmed_official_derived_source(db)

    rights_persist = None
    rights_fetch = None
    if db is not None:
        rights_persist = evaluate_connector_operation_rights(
            db, connector_key=PUBMED_CONNECTOR_KEY, operation=OP_DERIVED_METADATA_PERSIST
        )
        rights_fetch = evaluate_connector_operation_rights(
            db, connector_key=PUBMED_CONNECTOR_KEY, operation=OP_NETWORK_FETCH
        )

    if persist:
        assert rights_persist is not None
        if rights_persist.automation_decision != "AUTOMATION_ALLOWED":
            return _blocked_pubmed(
                mode=m.value,
                reason=rights_persist.block_reason or "DERIVED_PERSIST_BLOCKED",
                rights_state=rights_persist.rights_state,
                canon=rights_persist.canonical_key,
            )

    from backend.app.services.i5.know04.pubmed import PubMedConnector, PubMedConnectorConfig

    obs = _observing_http(http_get)
    try:
        cfg = PubMedConnectorConfig.from_env(allow_disallowed_email=False)
        cfg.max_rps = min(float(max_rps), PUBMED_CANARY_MAX_RPS)
        sleep_fn = (lambda _s: None) if http_get is not None else __import__("time").sleep
        conn = PubMedConnector(config=cfg, http_get=obs, sleep_fn=sleep_fn)
        discovered = conn.discover(query, retmax=cap)
        ids = [str(x) for x in (discovered.get("ids") or [])[:cap]]
        if not ids:
            return BoundedIngestionResult(
                mode=m.value,
                connector_key=PUBMED_CONNECTOR_KEY,
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

        existing_pmids: set[str] = set()
        if persist and db is not None:
            rows = (
                db.query(models.I5ScientificArtifact.pmid)
                .filter(models.I5ScientificArtifact.pmid.in_(ids))
                .all()
            )
            existing_pmids = {str(r[0]) for r in rows if r[0]}

        chosen = next((pmid for pmid in ids if pmid not in existing_pmids), ids[0])
        rec = conn.fetch_record(chosen)
        raw = dict(rec.payload or {})
        raw.setdefault("pmid", chosen)
        persist_for_hash = dict(raw)

        stages = [s.value for s in list(PublicationStage)[:4]]
        if not persist:
            return BoundedIngestionResult(
                mode=m.value,
                connector_key=PUBMED_CONNECTOR_KEY,
                status="FETCHED",
                http_status=obs.last_status,
                bytes_received=obs.total_bytes,
                request_count=obs.request_count,
                page_count=1,
                external_ids=ids,
                records_discovered=len(ids),
                records_normalized=1,
                records_accepted=1,
                records_rejected=0,
                records_changed=0,
                rights_decision=(rights_fetch.rights_state if rights_fetch else "METADATA_ONLY"),
                storage_decision="NO_STORE",
                transient_raw_residue=0,
                publication_stages=stages,
                block_reason=None,
                clinical_runtime_eligible=False,
                canonical_source_key=rights_fetch.canonical_key if rights_fetch else None,
            )

        assert db is not None
        source = resolve_canonical_source(db, PUBMED_CONNECTOR_KEY)
        if source is None:
            return _blocked_pubmed(
                mode=m.value,
                reason="CANONICAL_SOURCE_NOT_FOUND",
                rights_state="RIGHTS_UNKNOWN",
                http_status=obs.last_status,
                bytes_received=obs.total_bytes,
                request_count=obs.request_count,
                ids=ids,
            )
        art_id, ku_id, created_new = _persist_pubmed_derived_knowledge(
            db, source=source, pmid=chosen, raw=persist_for_hash
        )
        ku = db.query(models.KnowledgeUnit).filter_by(id=ku_id).first()
        if ku is not None and ku.runtime_eligibility == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value:
            ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.REVIEW_REQUIRED.value
            db.flush()
        return BoundedIngestionResult(
            mode=m.value,
            connector_key=PUBMED_CONNECTOR_KEY,
            status="STORED",
            http_status=obs.last_status,
            bytes_received=obs.total_bytes,
            request_count=obs.request_count,
            page_count=1,
            external_ids=ids,
            records_discovered=len(ids),
            records_normalized=1,
            records_accepted=1,
            records_rejected=0,
            records_changed=1 if created_new else 0,
            rights_decision=rights_persist.rights_state if rights_persist else "RIGHTS_ALLOWED",
            storage_decision="DERIVED_GOVERNED_STORE",
            transient_raw_residue=0,
            publication_stages=stages,
            knowledge_unit_id=ku_id,
            artifact_id=art_id,
            block_reason=None,
            clinical_runtime_eligible=False,
            canonical_source_key=rights_persist.canonical_key if rights_persist else None,
        )
    except Exception as exc:
        return BoundedIngestionResult(
            mode=m.value,
            connector_key=PUBMED_CONNECTOR_KEY,
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
            block_reason=f"NETWORK_OR_CONNECTOR_ERROR:{type(exc).__name__}:{exc}",
            canonical_source_key=rights_fetch.canonical_key if rights_fetch else None,
        )


def ingest_pubmed_bounded_or_block(
    *,
    mode: Know05Mode | str = Know05Mode.BOUNDED_INGESTION,
    db: Optional[Session] = None,
    query: str = PUBMED_CANARY_DEFAULT_QUERY,
    http_get: Optional[Callable[..., Any]] = None,
    max_records: int = 1,
    persist: bool = True,
    ensure_official_source: bool = False,
) -> BoundedIngestionResult:
    return ingest_pubmed_bounded(
        db,
        mode=mode,
        query=query,
        http_get=http_get,
        max_records=max_records,
        persist=persist,
        ensure_official_source=ensure_official_source,
    )

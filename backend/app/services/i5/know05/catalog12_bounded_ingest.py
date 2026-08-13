"""Bounded one-shot Catalog-12 specialty ingest (derived knowledge only).

Does not enable weekly unattended. Does not store raw HTML/PDF/full text.
New KU remains DRAFT / NOT_REVIEWED / REVIEW_REQUIRED.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from html import unescape
from typing import Any, Callable, Optional
from urllib.parse import urlparse

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
    ProcessingPermissionMode,
    PublicationState,
    ReviewState,
    RightDecision,
    SourceRole,
    SourceUniverse,
)
from backend.app.services.i5.know01.catalog12_specialty_authorities import (
    Catalog12CellAuthority,
    cell_by_id,
)
from backend.app.services.i5.know01.registry_service import ensure_gsp, upsert_registry_extension
from backend.app.services.i5.know05.canonical_rights import (
    OP_DERIVED_METADATA_PERSIST,
    OP_NETWORK_FETCH,
    evaluate_connector_operation_rights,
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class Catalog12IngestResult:
    cell_id: str
    connector_key: str
    status: str
    http_status: int = 0
    request_count: int = 0
    block_reason: Optional[str] = None
    source_profile_id: Optional[int] = None
    artifact_id: Optional[int] = None
    knowledge_unit_id: Optional[int] = None
    raw_evidence_id: Optional[int] = None
    created_new: bool = False
    rights_decision: str = "NOT_EVALUATED"
    storage_decision: str = "NO_STORE"
    unattended_weekly_enabled: bool = False
    publication_state: str = PublicationState.DRAFT.value
    review_state: str = ReviewState.NOT_REVIEWED.value
    runtime_eligibility: str = KnowledgeUnitRuntimeEligibility.REVIEW_REQUIRED.value
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _strip_tags(html: str) -> str:
    text = unescape(_TAG_RE.sub(" ", html or ""))
    return _WS_RE.sub(" ", text).strip()


def distill_official_html(html: str, *, cell: Catalog12CellAuthority) -> dict[str, Any]:
    """Bounded derived envelope. Never returns raw HTML or large verbatim body."""
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html or "", flags=re.I | re.S)
    title = _strip_tags(title_m.group(1) if title_m else "")[:240] or cell.primary_authority
    headings = [_strip_tags(h)[:180] for h in re.findall(r"<h1[^>]*>(.*?)</h1>", html or "", flags=re.I | re.S)]
    h2 = [_strip_tags(h)[:180] for h in re.findall(r"<h2[^>]*>(.*?)</h2>", html or "", flags=re.I | re.S)]
    claims = [c for c in (headings + h2) if c and len(c) > 8][:3]
    if not claims:
        claims = [f"{cell.primary_organization} publishes official {cell.specialty} health information."]
    envelope = {
        "cell_id": cell.cell_id,
        "authority": cell.primary_authority,
        "organization": cell.primary_organization,
        "domain": cell.primary_domain,
        "title": title,
        "claims": claims,
        "raw_html_retained": False,
        "pdf_retained": False,
        "verbatim_body_retained": False,
    }
    digest = hashlib.sha256(json.dumps(envelope, sort_keys=True).encode("utf-8")).hexdigest()
    envelope["content_hash"] = digest
    return envelope


def ensure_catalog12_source(db: Session, cell_id: str) -> models.GovernedSourceProfile:
    cell = cell_by_id(cell_id)
    key = f"know01:{cell.source_key}"
    gsp = ensure_gsp(db, canonical_key=key, locator=cell.canonical_home)
    gsp.registry_state = "ACTIVE"
    gsp.operational_status = "active"
    gsp.runtime_eligibility = "REVIEW_REQUIRED"
    upsert_registry_extension(
        db,
        source_profile_id=gsp.id,
        source_universe=SourceUniverse.GLOBAL_KNOWLEDGE.value,
        authority_class=cell.authority_class,
        publisher_family=cell.primary_organization,
        roles=list(cell.roles) or [SourceRole.PUBLIC_HEALTH.value],
        access_right=RightDecision.ALLOWED.value,
        automation_right=RightDecision.ALLOWED.value,
        tdm_right=RightDecision.ALLOWED.value,
        transform_right=RightDecision.ALLOWED.value,
        retain_raw_right=RightDecision.DENIED.value,
        retain_derived_right=RightDecision.ALLOWED.value,
        redistribution_right=RightDecision.DENIED.value,
        robots_state="ALLOWED",
        processing_permission_mode=ProcessingPermissionMode.DERIVED_KNOWLEDGE_ONLY.value,
        canonical_home=cell.canonical_home,
        canonical_discovery_endpoint=cell.canary_url,
        supported_formats="HTML",
        specialty_domains=cell.specialty,
        knowledge_domains=cell.knowledge_domains,
        notes=(
            f"CATALOG12_{cell.cell_id}; UNATTENDED_WEEKLY_ENABLED=NO; "
            "ONE_SHOT_CANARY_ALLOWED=YES; RAW_HTML=DENIED; DERIVED=ALLOWED"
        ),
        registry_status="ACTIVE",
        review_stage="NONE",
        rate_limit_policy="MAX_1_RPS_CANARY",
    )
    db.flush()
    return gsp


def _persist_derived(
    db: Session,
    *,
    cell: Catalog12CellAuthority,
    source: models.GovernedSourceProfile,
    envelope: dict[str, Any],
) -> tuple[int, int, Optional[int], bool]:
    from backend.app.services.i5.know02.artifacts import add_artifact_version, link_evidence
    from backend.app.services.i5.know05.acquisition_boundary import record_acquisition_evidence_boundary

    content_hash = envelope["content_hash"]
    title = str(envelope.get("title") or cell.primary_authority)
    artifact_key = f"catalog12:{cell.cell_id}:{cell.source_key}"
    art = db.query(models.I5ScientificArtifact).filter_by(artifact_key=artifact_key).first()
    if art is None:
        art = models.I5ScientificArtifact(
            artifact_key=artifact_key,
            artifact_type=ArtifactType.GUIDELINE.value,
            title=title[:2000],
            source_profile_id=source.id,
            publisher_family=cell.primary_organization[:240],
            canonical_url=cell.canary_url,
        )
        db.add(art)
        db.flush()
    else:
        art.title = title[:2000]
        art.source_profile_id = source.id
        art.canonical_url = cell.canary_url
        db.flush()

    ver = (
        db.query(models.I5ScientificArtifactVersion)
        .filter_by(artifact_id=art.id, content_hash=content_hash)
        .first()
    )
    if ver is None:
        prior_n = db.query(models.I5ScientificArtifactVersion).filter_by(artifact_id=art.id).count()
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
            locator=cell.canary_url,
        )

    raw_id = record_acquisition_evidence_boundary(
        db,
        source_profile_id=source.id,
        canonical_url=cell.canary_url,
        content_hash=content_hash,
        rights_decision="RIGHTS_ALLOWED",
        connector_key=cell.source_key,
        mime_type="text/html",
    )

    dedupe = hashlib.sha256(f"know05:catalog12:{cell.cell_id}:{cell.source_key}".encode()).hexdigest()
    existing = db.query(models.KnowledgeUnit).filter_by(deduplication_key=dedupe).first()
    if existing is not None:
        if hasattr(models, "I5KnowledgeUnitEvidenceLink"):
            link_evidence(
                db,
                knowledge_unit_id=existing.id,
                artifact_version_id=ver.id,
                support_direction="NEUTRAL",
                evidence_role="SPECIALTY_AUTHORITY_IDENTITY",
            )
        return art.id, existing.id, raw_id, False

    claims = "; ".join(envelope.get("claims") or [])[:800]
    statement = (
        f"{cell.cell_id} specialty authority {cell.primary_organization} ({cell.primary_domain}): "
        f"{title}. Derived claims: {claims}. "
        "Candidate knowledge only; not a clinical recommendation."
    )
    canonical = hashlib.sha256(f"ku:catalog12:{cell.cell_id}:{cell.source_key}".encode()).hexdigest()[:32]
    ku = models.KnowledgeUnit(
        canonical_unit_id=canonical,
        immutable_version_id=ver.version_label,
        domain=cell.specialty,
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
    db.add(
        models.KnowledgeProvenance(
            knowledge_unit_id=ku.id,
            source_profile_id=source.id,
            source_document_id=f"CATALOG12:{cell.cell_id}",
            source_version_id=ver.version_label,
            retrieval_method="official_public_web_https",
            access_route="OFFICIAL_PUBLIC_WEB",
            content_hash=content_hash,
            extraction_process="catalog12_html_heading_distill",
            normalization_process="know05_catalog12_derived_persist",
            raw_evidence_id=raw_id,
            attribution_data=json.dumps(
                {
                    "cell_id": cell.cell_id,
                    "organization": cell.primary_organization,
                    "domain": cell.primary_domain,
                    "url": cell.canary_url,
                    "raw_retention": "DENIED",
                    "html_verbatim_persisted": False,
                    "pdf_persisted": False,
                    "unattended_weekly_enabled": False,
                },
                sort_keys=True,
            ),
        )
    )
    if hasattr(models, "I5KnowledgeUnitEvidenceLink"):
        link_evidence(
            db,
            knowledge_unit_id=ku.id,
            artifact_version_id=ver.id,
            support_direction="NEUTRAL",
            evidence_role="SPECIALTY_AUTHORITY_IDENTITY",
        )
    db.flush()
    return art.id, ku.id, raw_id, True


def ingest_catalog12_cell(
    db: Session,
    cell_id: str,
    *,
    persist: bool = True,
    http_get: Optional[Callable[..., Any]] = None,
) -> Catalog12IngestResult:
    cell = cell_by_id(cell_id)
    connector_key = cell.source_key
    source = ensure_catalog12_source(db, cell_id)
    result = Catalog12IngestResult(
        cell_id=cell_id,
        connector_key=connector_key,
        status="BLOCKED",
        source_profile_id=source.id,
        unattended_weekly_enabled=False,
    )

    rights_fetch = evaluate_connector_operation_rights(
        db, connector_key=f"know01:{connector_key}", operation=OP_NETWORK_FETCH
    )
    if rights_fetch.automation_decision != "AUTOMATION_ALLOWED":
        result.block_reason = rights_fetch.block_reason or rights_fetch.rights_state
        result.rights_decision = rights_fetch.rights_state
        return result

    if http_get is None:
        result.block_reason = "NETWORK_DISABLED"
        return result

    parsed = urlparse(cell.canary_url)
    if parsed.scheme != "https":
        result.block_reason = "SCHEME_NOT_HTTPS"
        return result

    raw = http_get(
        cell.canary_url,
        headers={"User-Agent": "SediKB/1.0 (+https://sedi.health; curated-knowledge-fetch)"},
        timeout=15.0,
    )
    result.request_count = 1
    if isinstance(raw, dict):
        status = int(raw.get("status_code", 0))
        content = raw.get("content", b"")
        if isinstance(content, str):
            content = content.encode("utf-8")
    else:
        status = int(getattr(raw, "status_code", 0))
        content = getattr(raw, "content", b"") or b""
    result.http_status = status
    if status != 200:
        result.block_reason = f"HTTP_{status}"
        result.status = "FAILED"
        return result
    html = bytes(content).decode("utf-8", errors="replace")
    if "<html" not in html.lower() and "<title" not in html.lower():
        result.block_reason = "MALFORMED_PAYLOAD"
        result.status = "FAILED"
        return result
    envelope = distill_official_html(html, cell=cell)
    if any(k in html.lower() for k in ("<html",)) and len(html) > 50_000:
        # Distill only; never persist the page body.
        pass
    result.diagnostics["derived_title"] = envelope.get("title")
    result.diagnostics["claim_count"] = len(envelope.get("claims") or [])
    result.diagnostics["raw_html_bytes"] = 0

    if not persist:
        result.status = "FETCHED"
        result.rights_decision = rights_fetch.rights_state
        result.storage_decision = "NO_STORE"
        return result

    rights_persist = evaluate_connector_operation_rights(
        db, connector_key=f"know01:{connector_key}", operation=OP_DERIVED_METADATA_PERSIST
    )
    if rights_persist.automation_decision != "AUTOMATION_ALLOWED":
        result.block_reason = rights_persist.block_reason or rights_persist.rights_state
        result.rights_decision = rights_persist.rights_state
        result.status = "BLOCKED"
        return result

    art_id, ku_id, raw_id, created = _persist_derived(
        db, cell=cell, source=source, envelope=envelope
    )
    result.artifact_id = art_id
    result.knowledge_unit_id = ku_id
    result.raw_evidence_id = raw_id
    result.created_new = created
    result.status = "STORED"
    result.rights_decision = "RIGHTS_ALLOWED"
    result.storage_decision = "DERIVED_GOVERNED_STORE"
    return result

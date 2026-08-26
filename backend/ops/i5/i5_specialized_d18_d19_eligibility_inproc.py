"""Bounded D18/D19 specialized eligibility reprocess (production / CI ops).

Fetches only MedlinePlus ALS + MS URLs already on the allowlist, extracts with
chrome-stripped HTML, persists KU/provenance via governed weekly handoff path,
then applies specialized serving eligibility (MedlinePlus global low-risk stays NO).
"""
from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from typing import Any

from backend.app.database import get_db
import backend.app.models as models
from backend.app.schemas.i5_adapters import SourceGovernanceSnapshot
from backend.app.services.i5.adapters.base import default_registry
from backend.app.services.i5.conceptual_extraction import extract_from_html
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
from backend.app.services.i5.governed_ku_serving import apply_governed_finalize_and_lexical_index
from backend.app.services.i5.governed_specialized_entity_eligibility import (
    SPECIALIZED_SOURCE_KEY,
    content_quality_pass,
    resolve_specialized_entity_from_url,
    specialized_source_authorized,
)
from backend.app.services.i5.knowledge_unit_service import (
    build_canonical_hash,
    build_deduplication_key,
    validate_no_pii_markers,
)
from backend.app.services.i5.medical_safety_gate import assert_allowed_medical_safety_transition
from backend.app.services.i5.multisource_activation import active_allowlist_rows
from backend.app.services.i5.trusted_source_manifest import governed_low_risk_eligible, load_trusted_source_manifest


def _als_ms_urls() -> list[str]:
    rows = {r["source_key"]: r for r in active_allowlist_rows()}
    row = rows.get(SPECIALIZED_SOURCE_KEY)
    if not row:
        raise SystemExit("medlineplus_not_active")
    urls = [str(row["exact_url"])] + [str(u) for u in (row.get("additional_urls") or [])]
    out = []
    for u in urls:
        if resolve_specialized_entity_from_url(u) is not None:
            out.append(u)
    return out


def _gov_snapshot(source_profile_id: int, row: dict[str, Any]) -> SourceGovernanceSnapshot:
    return SourceGovernanceSnapshot(
        source_profile_id=source_profile_id,
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        rights_terms_state=str(row.get("rights_terms_state") or "PUBLIC_DOMAIN"),
        robots_access_state=str(row.get("robots_access_state") or "ALLOWED"),
        rate_limit_policy="DEFINED",
        allowed_domain=str(row.get("allowed_domain") or "medlineplus.gov"),
    )


def run() -> dict[str, Any]:
    load_trusted_source_manifest.cache_clear()
    if governed_low_risk_eligible(SPECIALIZED_SOURCE_KEY):
        raise SystemExit("HARD_STOP_medlineplus_global_low_risk_must_remain_NO")
    if not specialized_source_authorized(SPECIALIZED_SOURCE_KEY):
        raise SystemExit("specialized_source_not_authorized")

    urls = _als_ms_urls()
    if len(urls) < 2:
        raise SystemExit(f"expected_als_ms_urls_ge_2_got_{len(urls)}")

    db = next(get_db())
    report: dict[str, Any] = {"urls": urls, "results": []}
    try:
        row = next(r for r in active_allowlist_rows() if r["source_key"] == SPECIALIZED_SOURCE_KEY)
        gsp = (
            db.query(models.GovernedSourceProfile)
            .filter(models.GovernedSourceProfile.canonical_key == SPECIALIZED_SOURCE_KEY)
            .one()
        )
        ks = db.query(models.KnowledgeSource).filter_by(slug=SPECIALIZED_SOURCE_KEY).one()
        registry = default_registry()
        adapter = registry.resolve_by_mode("PUBLIC_WEB_FETCH")

        before = {
            "ku": db.query(models.KnowledgeUnit).count(),
            "eligible": db.query(models.KnowledgeUnit)
            .filter(models.KnowledgeUnit.runtime_eligibility == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value)
            .count(),
            "kce": db.query(models.KnowledgeChunkEmbedding).count(),
        }
        report["before"] = before

        for url in urls:
            spec = resolve_specialized_entity_from_url(url)
            assert spec is not None
            envelope = adapter.fetch_live(
                request_id=f"spec-{spec.entity_id}-{hashlib.sha256(url.encode()).hexdigest()[:12]}",
                url=url,
                governance=_gov_snapshot(int(gsp.id), row),
                max_bytes=2_000_000,
                timeout=45,
                allowed_url_patterns=list(row.get("allowed_url_patterns") or []),
                trust_level="official",
                review_required=True,
            )
            if envelope.error_category:
                report["results"].append({"url": url, "status": "FETCH_FAIL", "error": envelope.error_category})
                continue
            candidates = extract_from_html(envelope)
            primary = candidates[0]
            statement = (primary.claim_candidate or primary.normalized_text[:500]).strip()
            validate_no_pii_markers(statement)
            ok_q, q_reason = content_quality_pass(statement, spec)
            if not ok_q:
                report["results"].append(
                    {"url": url, "entity": spec.entity_id, "status": "QUALITY_REJECT", "reason": q_reason}
                )
                continue

            domain = spec.domain
            topic = spec.topic
            jurisdiction = "US"
            dedupe = build_deduplication_key(domain, topic, "general", jurisdiction, statement)
            canon = build_canonical_hash(statement, domain, KnowledgeType.OTHER.value, topic_taxonomy=topic)
            ku = db.query(models.KnowledgeUnit).filter_by(deduplication_key=dedupe).one_or_none()
            created = False
            if ku is None:
                created = True
                assert_allowed_medical_safety_transition(
                    MedicalSafetyState.UNKNOWN, MedicalSafetyState.PENDING_REVIEW
                )
                ku = models.KnowledgeUnit(
                    canonical_unit_id=f"ku-spec-{spec.entity_id.lower()}-{dedupe[:12]}",
                    immutable_version_id="v1",
                    domain=domain,
                    topic_taxonomy=topic,
                    disease_or_health_condition=spec.disease_label,
                    manifest_entity_id=spec.entity_id,
                    manifest_track_id=spec.track_id,
                    language="en",
                    knowledge_type=KnowledgeType.OTHER.value,
                    normalized_statement=statement,
                    applicability="consumer_health_education_not_diagnosis",
                    population="general",
                    jurisdiction=jurisdiction,
                    evidence_strength=EvidenceStrength.UNKNOWN.value,
                    medical_safety_state=MedicalSafetyState.PENDING_REVIEW.value,
                    conflict_state=ConflictState.NONE.value,
                    freshness_state=FreshnessState.UNKNOWN.value,
                    review_state=ReviewState.NOT_REVIEWED.value,
                    publication_state=PublicationState.DRAFT.value,
                    runtime_eligibility=KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value,
                    provenance_complete=False,
                    deduplication_key=dedupe,
                    canonical_hash=canon,
                    hash_algorithm="SHA-256",
                    canonicalization_version="v1",
                )
                db.add(ku)
                db.flush()
            else:
                ku.normalized_statement = statement
                ku.domain = domain
                ku.topic_taxonomy = topic
                ku.disease_or_health_condition = spec.disease_label
                ku.manifest_entity_id = spec.entity_id
                ku.manifest_track_id = spec.track_id
                ku.jurisdiction = jurisdiction
                db.flush()

            content_hash = hashlib.sha256((envelope.body or b"")).hexdigest()
            raw = (
                db.query(models.I5RawEvidence)
                .filter_by(
                    content_hash=content_hash,
                    source_profile_id=int(gsp.id),
                    canonical_url=url,
                )
                .one_or_none()
            )
            if raw is None:
                raw = models.I5RawEvidence(
                    source_profile_id=int(gsp.id),
                    retrieval_timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                    canonical_url=url,
                    content_hash=content_hash,
                    byte_hash=content_hash,
                    hash_algorithm="SHA-256",
                    mime_type=envelope.content_type or "text/html",
                    language="en",
                    jurisdiction=jurisdiction,
                    storage_mode="NONE",
                    retention_mode="RAW_MINIMAL_EVIDENCE_ONLY",
                    rights_terms_state="PUBLIC_DOMAIN",
                    robots_access_state="ALLOWED",
                    redaction_state="NONE",
                    prohibited_data_state="UNKNOWN",
                    expiry_state="ACTIVE",
                )
                db.add(raw)
                db.flush()

            prov = (
                db.query(models.KnowledgeProvenance)
                .filter_by(knowledge_unit_id=int(ku.id))
                .one_or_none()
            )
            attr = {
                "required_text": f"Information from {row.get('publisher')}",
                "license": "PUBLIC_DOMAIN",
                "source_url": url,
                "adapter_id": getattr(adapter, "adapter_id", "PUBLIC_WEB_FETCH"),
            }
            if prov is None:
                prov = models.KnowledgeProvenance(
                    knowledge_unit_id=int(ku.id),
                    source_profile_id=int(gsp.id),
                    raw_evidence_id=int(raw.id),
                    retrieval_method="PUBLIC_WEB_FETCH_HTTPS",
                    access_route="specialized_d18_d19_reprocess",
                    content_hash=content_hash,
                    byte_hash=content_hash,
                    extraction_process=primary.extractor_version,
                    normalization_process="w3p01-normalize",
                    attribution_data=json.dumps(attr, sort_keys=True),
                    citation_rendering_data=json.dumps(
                        {"attribution": attr["required_text"], "url": url}, sort_keys=True
                    ),
                )
                db.add(prov)
                db.flush()
            else:
                prov.raw_evidence_id = int(raw.id)
                prov.content_hash = content_hash
                prov.attribution_data = json.dumps(attr, sort_keys=True)
                prov.citation_rendering_data = json.dumps(
                    {"attribution": attr["required_text"], "url": url}, sort_keys=True
                )
                db.flush()

            ku.provenance_complete = True
            elig = apply_governed_finalize_and_lexical_index(
                db,
                ku,
                source_key=SPECIALIZED_SOURCE_KEY,
                source_profile_id=int(gsp.id),
                raw_evidence_id=int(raw.id),
                authoritative_provenance=prov,
                incoming_source_profile_id=int(gsp.id),
                canonical_url=url,
            )
            report["results"].append(
                {
                    "url": url,
                    "entity": spec.entity_id,
                    "status": "OK",
                    "ku_id": int(ku.id),
                    "created": created,
                    "eligibility": elig.value,
                    "quality": q_reason,
                    "ks_slug": ks.slug,
                }
            )

        db.commit()

        def entity_counts(entity_id: str) -> dict[str, int]:
            rows = (
                db.query(models.KnowledgeUnit)
                .filter(models.KnowledgeUnit.manifest_entity_id == entity_id)
                .all()
            )
            # Also count via provenance URL if entity not stamped on older rows
            return {
                "ku": len(rows),
                "eligible": sum(
                    1
                    for r in rows
                    if str(r.runtime_eligibility) == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value
                ),
            }

        after = {
            "ku": db.query(models.KnowledgeUnit).count(),
            "eligible": db.query(models.KnowledgeUnit)
            .filter(models.KnowledgeUnit.runtime_eligibility == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value)
            .count(),
            "kce": db.query(models.KnowledgeChunkEmbedding).count(),
            "d18": entity_counts("D18"),
            "d19": entity_counts("D19"),
            "medlineplus_global_low_risk": governed_low_risk_eligible(SPECIALIZED_SOURCE_KEY),
        }
        report["after"] = after
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return report
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()

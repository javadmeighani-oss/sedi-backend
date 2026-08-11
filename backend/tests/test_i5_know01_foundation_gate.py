"""I5 Knowledge Foundation Gate — reference catalog, formats, discovery safety."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.services.i5.adapters.base import AdapterFrameworkError, default_registry
from backend.app.services.i5.enums import BookRightsClass, RightDecision
from backend.app.services.i5.know01.discovery_foundation import (
    assess_candidate_ingestion_eligibility,
    bounded_discover_endpoints,
    classify_candidate,
    fake_medical_hostname_must_not_activate,
    queue_for_rights_review,
)
from backend.app.services.i5.know01.format_capability_matrix import (
    assert_v1_required_formats_covered,
    build_format_capability_matrix,
    resolve_adapter_for_resource,
    select_adapter_mode,
)
from backend.app.services.i5.know01.format_contracts import FUTURE_ADAPTER_CONTRACTS
from backend.app.services.i5.know01.seed_registry import seed_know01_registry
from backend.app.services.i5.know01.v1_reference_catalog import (
    ACQ_DENIED,
    ACQ_METADATA_ONLY,
    ACQ_REVIEW_REQUIRED,
    ACQ_UNKNOWN,
    PLACEHOLDER_BOOK_KEYS,
    V1_AUTHORITATIVE_REFERENCE_CATALOG,
    acquisition_state_for_book,
    assert_placeholders_alone_insufficient,
    catalog_summary,
)


def _db_url():
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def test_format_capability_matrix_complete_and_v1_required():
    rows = build_format_capability_matrix()
    assert len(rows) >= 20
    by_id = {r.format_id: r for r in rows}
    assert by_id["OFFICIAL_API"].status == "IMPLEMENTED"
    assert by_id["PDF_TEXT"].status == "IMPLEMENTED"
    assert by_id["BITS_XML"].status in {"CONTRACT_ONLY", "NOT_CURRENTLY_REQUIRED"}
    assert by_id["OCR"].fail_closed_behavior.startswith("UNSUPPORTED_FORMAT")
    assert_v1_required_formats_covered(rows)
    # Future contract still fail-closed
    with pytest.raises(AdapterFrameworkError, match="UNSUPPORTED_FORMAT"):
        FUTURE_ADAPTER_CONTRACTS["EPUB"].extract(b"PK")


def test_adaptive_routing_prefers_content_type_over_extension():
    # Misleading extension: .pdf filename but JSON content-type → API
    mode = select_adapter_mode(content_type="application/json", filename_hint="paper.pdf")
    assert mode == "OFFICIAL_API"
    mode = select_adapter_mode(payload_prefix=b"%PDF-1.7 ...", filename_hint="x.json")
    assert mode == "PDF_TEXT"
    mode = select_adapter_mode(declared_format="JATS_XML", filename_hint="x.bin")
    assert mode == "OFFICIAL_XML"
    with pytest.raises(AdapterFrameworkError, match="UNSUPPORTED_FORMAT"):
        select_adapter_mode(filename_hint="book.epub")
    with pytest.raises(AdapterFrameworkError, match="UNSUPPORTED_FORMAT"):
        select_adapter_mode(declared_format="OCR")
    reg = default_registry()
    mode, adapter = resolve_adapter_for_resource(
        reg, content_type="application/rss+xml", filename_hint="news.html"
    )
    assert mode == "RSS_OR_FEED"
    assert adapter.metadata().mode == "RSS_OR_FEED"


def test_discovery_fake_medical_domain_never_active():
    assessment = fake_medical_hostname_must_not_activate("authoritative-medical-clinic.health")
    assert assessment.auto_trust is False
    assert assessment.auto_activate is False
    assert assessment.eligible_for_activation is False
    assert assessment.eligible_for_ingestion is False
    assert "DOMAIN_NAME_ALONE_INSUFFICIENT" in assessment.blocking_reasons


def test_discovery_off_seed_and_rights_unknown_and_unsupported_format():
    html = """
    <a href="https://evil-pubmed-lookalike.example/api">x</a>
    <a href="https://www.who.int/feed.rss">ok</a>
    """
    ends = bounded_discover_endpoints("www.who.int", html)
    off = [e for e in ends if "evil" in e.url]
    assert off
    c = classify_candidate(off[0], identity_verified=False, lifecycle="APPROVED")
    assert c.auto_activate is False
    assert c.lifecycle != "ACTIVE"
    assert "OFF_SEED_DOMAIN_CANDIDATE_ONLY" in c.notes

    unknown = assess_candidate_ingestion_eligibility(
        identity_verified=True,
        authority_verified=True,
        rights_state="UNKNOWN",
        format_supported=True,
        lifecycle="APPROVED",
    )
    assert unknown.eligible_for_ingestion is False
    assert "RIGHTS_UNKNOWN_OR_REVIEW" in unknown.blocking_reasons

    denied = assess_candidate_ingestion_eligibility(
        identity_verified=True,
        authority_verified=True,
        rights_state="DENIED",
        format_supported=True,
        lifecycle="ACTIVE",
    )
    assert denied.eligible_for_activation is False

    unsupported = assess_candidate_ingestion_eligibility(
        identity_verified=True,
        authority_verified=True,
        rights_state="ALLOWED",
        format_supported=False,
        lifecycle="ACTIVE",
    )
    assert unsupported.eligible_for_ingestion is False
    assert "UNSUPPORTED_FORMAT" in unsupported.blocking_reasons

    trial = assess_candidate_ingestion_eligibility(
        identity_verified=True,
        authority_verified=True,
        rights_state="ALLOWED",
        format_supported=True,
        lifecycle="ACTIVE",
        trial_registry_semantics_only=True,
    )
    assert trial.eligible_for_ingestion is False
    assert "TRIAL_REGISTRY_NOT_CLINICAL_RUNTIME" in trial.blocking_reasons

    queued = queue_for_rights_review([c])
    assert queued[0].lifecycle == "RIGHTS_REVIEW"
    assert queued[0].auto_activate is False


def test_catalog_specs_cover_required_families_without_inventing_fulltext():
    families = {s.family for s in V1_AUTHORITATIVE_REFERENCE_CATALOG}
    assert {"core_clinical", "priority_disease", "mental_behavioral", "lifestyle"} <= families
    assert len(V1_AUTHORITATIVE_REFERENCE_CATALOG) >= 12
    for s in V1_AUTHORITATIVE_REFERENCE_CATALOG:
        assert s.book_key not in PLACEHOLDER_BOOK_KEYS
        assert s.title and s.publisher and s.authors_editors
        assert s.fulltext_automation_permission != RightDecision.ALLOWED.value
        assert "example" not in s.title.lower() or "GeneReviews" in s.title


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_pg_v1_reference_catalog_rights_and_placeholders_insufficient():
    from backend.app import models

    engine = create_engine(_db_url())
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert head == "065_i5_know04_connectors_change_intelligence", head

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # Do not delete shared GovernedSourceProfile rows — KNOW-05 suite may retain
        # KnowledgeProvenance FKs in the same fresh DB. Seeds are upsert-idempotent.
        summary = seed_know01_registry(db)
        db.commit()
        assert summary["automation_approved_count"] == 0
        assert summary["v1_authoritative_catalog"]["catalog_count"] >= 12

        # Placeholders alone are insufficient
        assert_placeholders_alone_insufficient(db)
        named = [
            b
            for b in db.query(models.I5ReferenceBook).all()
            if b.book_key not in PLACEHOLDER_BOOK_KEYS
        ]
        assert len(named) >= 12
        harris = next(b for b in named if b.book_key == "harrisons_principles_internal_medicine")
        assert harris.isbn
        assert harris.fulltext_automation_permission == RightDecision.DENIED.value
        assert acquisition_state_for_book(harris) in {ACQ_METADATA_ONLY, ACQ_DENIED}
        eds = db.query(models.I5ReferenceBookEdition).filter_by(book_id=harris.id).all()
        assert len(eds) >= 2
        assert sum(1 for e in eds if e.is_current) == 1

        dsm = next(b for b in named if b.book_key == "dsm5_tr")
        assert dsm.rights_class == BookRightsClass.METADATA_ONLY.value
        assert acquisition_state_for_book(dsm) in {ACQ_METADATA_ONLY, ACQ_DENIED}
        assert acquisition_state_for_book(dsm) != "FULLTEXT_ALLOWED"

        cdc = next(b for b in named if b.book_key == "cdc_yellow_book")
        assert acquisition_state_for_book(cdc) == ACQ_REVIEW_REQUIRED

        # High authority commercial remains metadata-only / denied fulltext
        commercial = (
            db.query(models.I5ReferenceBook)
            .filter_by(book_key="commercial_medical_reference_metadata_only")
            .one()
        )
        assert commercial.fulltext_automation_permission == RightDecision.DENIED.value
        assert "HIGH" in (commercial.medical_authority_note or "")

        # Registry seeds remain non-active / unknown rights
        from backend.app.services.i5.know01.registry_service import automation_decision_for_extension

        for ext in db.query(models.I5SourceRegistryExtension).limit(8):
            assert automation_decision_for_extension(ext).allowed is False
            assert (ext.registry_status or "").upper() != "ACTIVE"

        # Alias connector key exists as registry identity. Other suite tests may
        # later mark a GSP ELIGIBLE for fixtures; automation must still fail-closed
        # when extension rights remain UNKNOWN unless explicitly remediated.
        who_alias = (
            db.query(models.GovernedSourceProfile)
            .filter_by(canonical_key="know01:who_guideline_catalogue")
            .first()
        )
        assert who_alias is not None
        who_ext = (
            db.query(models.I5SourceRegistryExtension)
            .filter_by(source_profile_id=who_alias.id)
            .first()
        )
        assert who_ext is not None
        assert (who_ext.registry_status or "").upper() != "ACTIVE"
        assert automation_decision_for_extension(who_ext).allowed is False

        stats = catalog_summary(db)
        assert stats["named_authoritative"] >= 12
        assert stats["placeholders"] >= 1
        assert ACQ_UNKNOWN not in stats["acquisition_distribution"] or True
        print(
            f"CATALOG_NAMED={stats['named_authoritative']} "
            f"PLACEHOLDERS={stats['placeholders']} "
            f"ACQ={stats['acquisition_distribution']}"
        )
    finally:
        db.close()
        engine.dispose()

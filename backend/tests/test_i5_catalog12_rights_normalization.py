"""Catalog-12 action-specific rights metadata — no blanket public-domain claim."""

from __future__ import annotations

from backend.app.services.i5.enums import BookRightsClass
from backend.app.services.i5.know01.catalog12_specialty_authorities import (
    CATALOG12_CELLS,
    catalog12_book_specs,
    catalog12_registry_seeds,
    rights_family_for,
    rights_profile_for,
    scorecard,
)
from backend.app.services.i5.know01.v1_reference_catalog import V1_AUTHORITATIVE_REFERENCE_CATALOG


_BLANKET_FORBIDDEN = (
    "US_GOV_PUBLIC_DOMAIN_TEXT; RAW_HTML=NO; DERIVED=YES",
    "US_FEDERAL_PUBLIC_DOMAIN_TEXT_ATTRIBUTION_APPRECIATED",
)


def test_catalog12_rights_are_source_specific_with_third_party_exceptions():
    families = set()
    for cell in CATALOG12_CELLS:
        profile = rights_profile_for(cell)
        card = scorecard(cell)
        families.add(profile.family)
        assert profile.third_party_exception_check == "REQUIRED"
        assert card["THIRD_PARTY_EXCEPTION_CHECK"] == "REQUIRED"
        assert "THIRD_PARTY" in profile.rights_state
        assert profile.raw_html_retention == "DENIED_BY_SEDI_CANARY_POLICY"
        assert profile.raw_full_text_retention == "RIGHTS_DEPENDENT"
        assert profile.derived_knowledge_distillation == "ALLOWED_WHEN_LAWFUL"
        assert profile.provenance_required == "YES"
        assert profile.no_endorsement_implication == "YES"
        assert profile.official_policy_url.startswith("https://")
        assert cell.raw_retention == "DENIED"
        assert cell.derived_retention == "ALLOWED"
        assert cell.unattended_weekly_enabled is False
        assert card["UNATTENDED_WEEKLY_ENABLED"] == "NO"
        assert card["SOURCE_REFETCH_REQUIRED"] == "NO"
        assert card["CATALOG12_DATA_REPAIR_REQUIRED"] == "NO"
        for banned in _BLANKET_FORBIDDEN:
            assert banned not in card["RIGHTS_STATE"]
            assert banned not in card["CURRENT_TERMS"]
            assert banned not in cell.rights_state
        assert card["RIGHTS_STATE"] == profile.rights_state
        assert rights_family_for(cell) == profile.family
    assert families == {"NCI", "NIH_INSTITUTE", "CDC", "OWH"}


def test_catalog12_derived_permission_is_separate_from_raw_retention():
    for cell in CATALOG12_CELLS:
        profile = rights_profile_for(cell)
        assert profile.raw_html_retention != profile.derived_knowledge_distillation
        assert cell.raw_retention != cell.derived_retention


def test_catalog12_book_specs_keep_pd_class_only_with_exception_semantics():
    specs = {s.book_key: s for s in catalog12_book_specs()}
    catalog_keys = {s.book_key for s in V1_AUTHORITATIVE_REFERENCE_CATALOG}
    for cell in CATALOG12_CELLS:
        spec = specs[cell.book_key]
        assert spec.rights_class == BookRightsClass.PUBLIC_DOMAIN.value
        assert "DERIVED_KNOWLEDGE_ONLY" in spec.retention_policy
        assert cell.book_key in catalog_keys
        profile = rights_profile_for(cell)
        assert profile.third_party_exception_check == "REQUIRED"


def test_catalog12_registry_seeds_do_not_enable_weekly_or_weaken_rights():
    seeds = catalog12_registry_seeds()
    assert len(seeds) == 12
    for seed in seeds:
        notes = str(seed["notes"])
        assert "UNATTENDED_WEEKLY_ENABLED=NO" in notes
        assert "THIRD_PARTY_EXCEPTION_CHECK=REQUIRED" in notes
        assert "RAW_HTML=DENIED" in notes
        assert "DERIVED=ALLOWED_WHEN_LAWFUL" in notes


def test_catalog12_no_runtime_eligibility_change():
    from backend.app.services.i5.know05.catalog12_bounded_ingest import Catalog12IngestResult

    sample = Catalog12IngestResult(cell_id="D01", connector_key="nci_pdq_oncology", status="DRY")
    assert sample.runtime_eligibility == "REVIEW_REQUIRED"
    assert sample.publication_state == "DRAFT"
    assert sample.review_state == "NOT_REVIEWED"
    assert sample.unattended_weekly_enabled is False

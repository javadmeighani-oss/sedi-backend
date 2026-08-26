"""D08 NIDCD extraction / content-quality hardening — offline tests."""
from __future__ import annotations

from types import SimpleNamespace

from backend.app.services.i5.conceptual_extraction import EXTRACTOR_VERSION
from backend.app.services.i5.enums import ConflictState, MedicalSafetyState
from backend.app.services.i5.governed_specialized_entity_eligibility import (
    D08,
    can_apply_specialized_entity_eligibility,
    content_quality_pass,
    select_clinical_claim_window,
    statement_dominated_by_nav_chrome,
)
from backend.app.services.i5.trusted_source_manifest import (
    load_trusted_source_manifest,
    manifest_row_for_key,
)


NIDCD_NAV_CHROME = (
    "nidcd employee intranet | a-z index | en español home health info health info "
    "hearing, ear infections, and deafness balance taste and smell voice, speech, and language"
)

NIDCD_BODY = (
    "Noise-induced hearing loss on this page: What is noise-induced hearing loss? "
    "Noise-induced hearing loss (NIHL) occurs when loud sound damages the delicate "
    "structures of the inner ear. Over time, exposure can cause permanent hearing loss "
    "and tinnitus. Prevention includes lowering volume and using hearing protection."
)


def test_extractor_version_bumped_for_claim_window():
    assert EXTRACTOR_VERSION == "w3p01-conceptual-1.0.2"


def test_nidcd_nav_chrome_rejected_before_fix_reproduction():
    assert statement_dominated_by_nav_chrome(NIDCD_NAV_CHROME) is True
    ok, reason = content_quality_pass(NIDCD_NAV_CHROME, D08)
    assert ok is False
    assert reason == "NAV_CHROME_DOMINATED"


def test_nidcd_body_claim_accepted_after_window_selection():
    mixed = NIDCD_NAV_CHROME + " " + ("x " * 200) + " " + NIDCD_BODY
    window = select_clinical_claim_window(
        mixed,
        canonical_url="https://www.nidcd.nih.gov/health/noise-induced-hearing-loss",
    )
    assert "on this page:" in window.casefold() or "noise-induced" in window.casefold()
    assert statement_dominated_by_nav_chrome(window) is False
    ok, reason = content_quality_pass(window, D08)
    assert ok is True and reason == "OK"


def test_nidcd_specialized_eligibility_pass():
    ku = SimpleNamespace(
        provenance_complete=True,
        retraction_reason=None,
        conflict_state=ConflictState.NONE.value,
        medical_safety_state=MedicalSafetyState.PENDING_REVIEW.value,
        normalized_statement=NIDCD_BODY,
        manifest_entity_id=None,
    )
    allowed, reason, spec = can_apply_specialized_entity_eligibility(
        source_key="nidcd_hearing_balance",
        ku=ku,
        canonical_url="https://www.nidcd.nih.gov/health/noise-induced-hearing-loss",
    )
    assert allowed is True and reason == "OK"
    assert spec is not None and spec.entity_id == "D08"


def test_nidcd_allowlist_urls_are_live_topic_pages_not_404_slug():
    load_trusted_source_manifest.cache_clear()
    row = manifest_row_for_key("nidcd_hearing_balance")
    assert row is not None
    urls = [row["exact_url"]] + list(row.get("additional_urls") or [])
    assert "hearing-ear-infections" not in " ".join(urls)
    assert any("noise-induced-hearing-loss" in u for u in urls)
    assert any("ear-infections-children" in u for u in urls)
    assert any("balance-disorders" in u for u in urls)
    assert row.get("governed_low_risk_eligibility") in {"NO", False, "no"}
    assert "D08" in (row.get("specialized_serving_eligibility") or [])


def test_quality_threshold_unchanged_short_statement_still_fails():
    ok, reason = content_quality_pass("hearing loss brief", D08)
    assert ok is False
    assert reason == "STATEMENT_TOO_SHORT"

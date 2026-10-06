"""SEDI-79-B1 — MedlinePlus/NIMH claim-window chrome hardening (offline)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.schemas.i5_adapters import FetchEnvelope
from backend.app.services.i5.adapters.base import AdapterFrameworkError, sha256_hex
from backend.app.services.i5.conceptual_extraction import (
    EXTRACTOR_VERSION,
    extract_from_html,
)
from backend.app.services.i5.governed_specialized_entity_eligibility import (
    select_clinical_claim_window,
    statement_dominated_by_nav_chrome,
)


MEDLINEPLUS_CHROME = (
    "Here’s how you know Here’s how you know Official websites use .gov A .gov website "
    "belongs to an official government organization in the United States. About MedlinePlus "
    "Search MedlinePlus Genetics Medical Tests Medical Encyclopedia Find an Expert "
    "Patient Handouts Journal Articles Resources Reference Desk"
)

MEDLINEPLUS_CLAIM = (
    "Also called: diabetes mellitus, DM On this page Basics Summary Start here "
    "Diabetes is a disease that occurs when your blood glucose, also called blood sugar, "
    "is too high. Over time, high blood glucose can cause health problems such as heart "
    "disease, nerve damage, and kidney disease. Healthy eating and physical activity help "
    "many people manage blood sugar with their care team."
)

NIMH_CHROME = (
    "als if you or a friend or family member are thinking about taking part in clinical "
    "research, this page contains basic information about clinical research. Near, NIH will "
    "start introducing a new website experience designed to make it easier to find health "
    "information, research, funding opportunities."
)

NIMH_CLAIM = (
    "What is anxiety disorder? Anxiety disorders are conditions involving excessive fear "
    "or worry that interferes with daily life. Signs and symptoms may include restlessness, "
    "trouble concentrating, and sleep problems. Treatments and therapies can include "
    "psychotherapy and, when appropriate, medication prescribed by a clinician. Coping with "
    "anxiety often starts with talking to a trusted health professional."
)

NHS_HEALTHY = (
    "Most adults need between 7 and 9 hours of sleep a night. Good sleep hygiene includes "
    "keeping a regular bedtime, limiting caffeine in the evening, and keeping your bedroom "
    "dark and quiet. If sleep problems persist, speak with a GP."
)


def _html_envelope(text: str, url: str) -> FetchEnvelope:
    body = f"<html><title>T</title><body><p>{text}</p></body></html>".encode("utf-8")
    return FetchEnvelope(
        request_id="t",
        adapter_id="i5.public_web_fetch",
        adapter_version="b1-claim-quality",
        canonical_url=url,
        http_status=200,
        final_url=url,
        retrieved_at=datetime.now(timezone.utc).replace(tzinfo=None),
        content_type="text/html",
        charset="utf-8",
        byte_count=len(body),
        content_hash=sha256_hex(body),
        etag=None,
        last_modified=None,
        disposition="OK",
        retryable=False,
        error_category=None,
        body=body,
    )


def test_extractor_version_b1():
    assert EXTRACTOR_VERSION == "w3p01-conceptual-1.0.3"


def test_medlineplus_chrome_rejected_claim_preserved():
    chrome_only = MEDLINEPLUS_CHROME
    assert statement_dominated_by_nav_chrome(chrome_only) is True
    assert (
        select_clinical_claim_window(
            chrome_only,
            canonical_url="https://medlineplus.gov/diabetes.html",
        )
        == ""
    )

    mixed = MEDLINEPLUS_CHROME + (" pad " * 80) + MEDLINEPLUS_CLAIM
    window = select_clinical_claim_window(
        mixed,
        canonical_url="https://medlineplus.gov/diabetes.html",
    )
    assert window
    assert "blood glucose" in window.casefold() or "diabetes is a disease" in window.casefold()
    assert "official websites use .gov" not in window.casefold()
    assert statement_dominated_by_nav_chrome(window) is False


def test_nimh_chrome_rejected_claim_preserved():
    assert statement_dominated_by_nav_chrome(NIMH_CHROME) is True
    assert (
        select_clinical_claim_window(
            NIMH_CHROME,
            canonical_url="https://www.nimh.nih.gov/health/topics/anxiety-disorders",
        )
        == ""
    )

    mixed = NIMH_CHROME + (" pad " * 80) + NIMH_CLAIM
    window = select_clinical_claim_window(
        mixed,
        canonical_url="https://www.nimh.nih.gov/health/topics/anxiety-disorders",
    )
    assert window
    assert "anxiety" in window.casefold()
    assert "treatments and therapies" in window.casefold() or "signs and symptoms" in window.casefold()
    assert "taking part in clinical research" not in window.casefold()
    assert "new website experience" not in window.casefold()
    assert statement_dominated_by_nav_chrome(window) is False


def test_no_clean_claim_fail_closed_raises_in_html_extract():
    with pytest.raises(AdapterFrameworkError, match="EXTRACTION_FAILED"):
        extract_from_html(
            _html_envelope(
                MEDLINEPLUS_CHROME,
                "https://medlineplus.gov/nutrition.html",
            )
        )
    with pytest.raises(AdapterFrameworkError, match="EXTRACTION_FAILED"):
        extract_from_html(
            _html_envelope(
                NIMH_CHROME,
                "https://www.nimh.nih.gov/health/topics/caring-for-your-mental-health",
            )
        )


def test_medlineplus_html_extract_preserves_claim_candidate():
    mixed = MEDLINEPLUS_CHROME + (" pad " * 80) + MEDLINEPLUS_CLAIM
    cands = extract_from_html(
        _html_envelope(mixed, "https://medlineplus.gov/diabetes.html")
    )
    assert cands and cands[0].claim_candidate
    claim = cands[0].claim_candidate.casefold()
    assert "blood glucose" in claim or "diabetes is a disease" in claim
    assert "official websites use .gov" not in claim


def test_nhs_healthy_extraction_regression():
    window = select_clinical_claim_window(
        NHS_HEALTHY,
        canonical_url="https://www.nhs.uk/live-well/sleep-and-tiredness/",
    )
    assert window
    assert "sleep" in window.casefold()
    assert statement_dominated_by_nav_chrome(window) is False
    cands = extract_from_html(
        _html_envelope(
            NHS_HEALTHY,
            "https://www.nhs.uk/live-well/sleep-and-tiredness/",
        )
    )
    assert cands and cands[0].claim_candidate
    assert "sleep" in cands[0].claim_candidate.casefold()

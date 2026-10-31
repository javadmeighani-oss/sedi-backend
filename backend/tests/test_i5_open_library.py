"""R-044 open-licence library: OpenStax Psychology 2e (CC BY 4.0) enters ONLY through the D23 fail-closed lane.

Javad (2026-10-31): Sedi should hold a strong library of current, reliable knowledge - only open-licence sources.
Each book is a governed manifest source with an explicit licence note; its pages get the same crisis / medicine /
resource-list boundary as every new D23 page.
"""

from __future__ import annotations

import pytest

from backend.app.services.i5.governed_specialized_entity_eligibility import (
    _d23_mh_edu_content_blocked,
    can_apply_specialized_entity_eligibility,
    resolve_specialized_entity_from_url,
    specialized_allowed_entities_for_source,
)
from backend.app.services.i5.multisource_activation import _governance_evidence
from backend.app.services.i5.trusted_source_manifest import manifest_attribution, manifest_row_for_key

KEY = "openstax_psychology_2e"
BOOK = "https://openstax.org/books/psychology-2e/pages/"


def _row():
    return manifest_row_for_key(KEY)


def _urls():
    row = _row()
    return [row["exact_url"], *row["additional_urls"]]


def test_the_book_is_an_active_open_licence_source_with_attribution():
    row = _row()
    assert row is not None and row["activation"] in (True, "YES")
    assert "CC BY 4.0" in row["license_notes"] and "attribution required" in row["license_notes"]
    assert row["rights_terms_state"] == "APPROVED" and row["robots_access_state"] == "ALLOWED"
    assert str(row["governed_low_risk_eligibility"]).upper() in {"NO", "FALSE"}
    assert "OpenStax" in manifest_attribution(KEY)["required_text"]
    evidence = _governance_evidence(row)
    assert len(evidence["specialty_domain"]) <= 128 and len(evidence["permitted_use_restriction"]) <= 240


def test_every_chapter_is_inside_the_d23_lane_and_the_source_patterns():
    import re

    assert specialized_allowed_entities_for_source(KEY) == {"D23"}
    assert len(_urls()) == len(set(_urls())) == 28
    assert f"max_{len(_urls())}_urls" in _row()["rate_limit"]
    for url in _urls():
        assert url.startswith(BOOK)
        assert any(re.match(p, url) for p in _row()["allowed_url_patterns"])
        spec = resolve_specialized_entity_from_url(url)
        assert spec is not None and spec.entity_id == "D23", url


def test_another_publishers_page_is_not_served_by_the_book():
    class Ku:
        provenance_complete = True
        retraction_reason = None
        conflict_state = "NONE"
        manifest_entity_id = "D23"
        normalized_statement = (
            "Stress — Coping: Stress affects mental health. Coping with stress and worry through relaxation and "
            "talking with people you trust can help anxiety."
        )

    ok, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=KEY, ku=Ku(), canonical_url="https://www.nhs.uk/every-mind-matters/mental-health-issues/stress/"
    )
    assert (ok, reason) == (False, "URL_NOT_IN_SOURCE_DOMAIN")


@pytest.mark.parametrize(
    "text, reason",
    [
        (
            "16.2 Types of Treatment — Biomedical Therapies: Antidepressants and other medications are used to treat "
            "depression and anxiety in mental health care.",
            "MH_EDU_MEDICATION_BLOCK",
        ),
        (
            "9.4 Death and Dying — Grief: Grief and bereavement affect mental health; anyone thinking about suicide "
            "should get help right away.",
            "MH_EDU_BOUNDARY_BLOCK",
        ),
    ],
)
def test_book_passages_about_medicines_or_crisis_fail_closed(text, reason):
    url = BOOK + "16-2-types-of-treatment"
    assert _d23_mh_edu_content_blocked(text, resolve_specialized_entity_from_url(url), canonical_url=url) == (True, reason)

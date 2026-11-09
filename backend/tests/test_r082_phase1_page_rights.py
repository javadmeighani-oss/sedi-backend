"""R-082 phase 1: the page rights detector (offline, deterministic) + the shadow/enforce gate at the fetch seam."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.services.i5 import page_rights as pr
from backend.app.services.i5.adapters.base import AdapterFrameworkError

IR = "https://behdasht.gov.ir/page"
IR_AC = "https://journals.sbmu.ac.ir/article/1"
OTHER = "https://example.com/page"


def _html(footer: str, head: str = "") -> bytes:
    return f"<html><head>{head}</head><body><p>content</p><footer>{footer}</footer></body></html>".encode("utf-8")


# (id, html, url, expected class, allowed, serve_mode)
CASES = [
    ("cc_by_link", _html('<a rel="license" href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>'), OTHER, pr.OPEN_AUTOMATION_ALLOWED, True, "passage"),
    ("cc_by_text", _html("Licensed under Creative Commons Attribution 4.0"), OTHER, pr.OPEN_AUTOMATION_ALLOWED, True, "passage"),
    ("ogl", _html('All content is available under the <a href="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/">Open Government Licence v3.0</a>'), OTHER, pr.OPEN_AUTOMATION_ALLOWED, True, "passage"),
    ("cc0", _html('<a rel="license" href="https://creativecommons.org/publicdomain/zero/1.0/">CC0</a>'), OTHER, pr.PUBLIC_DOMAIN, True, "passage"),
    ("license_label", _html("License: CC BY 4.0"), OTHER, pr.OPEN_AUTOMATION_ALLOWED, True, "passage"),
    ("meta_license", _html("hello", head='<meta name="dc.rights" content="https://creativecommons.org/licenses/by/4.0/">'), OTHER, pr.OPEN_AUTOMATION_ALLOWED, True, "passage"),
    ("only_links_to_cc_by_is_not_a_declaration", _html('See <a href="https://creativecommons.org/licenses/by/4.0/">this CC BY resource</a>. © 2026 Site. All rights reserved.'), OTHER, pr.ALL_RIGHTS_RESERVED, False, "none"),
    ("page_about_cc_by_is_not_a_declaration", _html("Our guide explains what Creative Commons Attribution means."), OTHER, pr.UNKNOWN_RIGHTS, True, "passage"),
    ("tdm_meta_content_first", _html("CC BY 4.0", head='<meta content="1" name="tdm-reservation">'), OTHER, pr.FULLTEXT_TDM_PROHIBITED, False, "none"),
    ("noai_content_first", _html("hello", head='<meta content="noai, noimageai" name="robots">'), OTHER, pr.FULLTEXT_TDM_PROHIBITED, False, "none"),
    ("public_domain", _html("This work is in the public domain."), OTHER, pr.PUBLIC_DOMAIN, True, "passage"),
    ("us_gov", _html("Works of the United States Government are not subject to copyright."), OTHER, pr.PUBLIC_DOMAIN, True, "passage"),
    ("cc_by_nc_link", _html('<a href="https://creativecommons.org/licenses/by-nc/4.0/">x</a>'), OTHER, pr.OPEN_LICENSE_RESTRICTED, False, "none"),
    ("cc_by_nd_link", _html('<a href="https://creativecommons.org/licenses/by-nd/4.0/">x</a>'), OTHER, pr.OPEN_LICENSE_RESTRICTED, False, "none"),
    ("noncommercial_text", _html("Creative Commons Attribution-NonCommercial 4.0"), OTHER, pr.OPEN_LICENSE_RESTRICTED, False, "none"),
    ("by_sa_needs_decision", _html('<a href="https://creativecommons.org/licenses/by-sa/4.0/">x</a>'), OTHER, pr.OPEN_LICENSE_RESTRICTED, False, "none"),
    ("nc_beats_by", _html('CC BY 4.0 text, images <a href="https://creativecommons.org/licenses/by-nc-nd/4.0/">CC BY-NC-ND</a>'), OTHER, pr.OPEN_LICENSE_RESTRICTED, False, "none"),
    ("tdm_meta", _html("CC BY 4.0", head='<meta name="tdm-reservation" content="1">'), OTHER, pr.FULLTEXT_TDM_PROHIBITED, False, "none"),
    ("tdm_text", _html("Text and data mining is not permitted without a licence."), OTHER, pr.FULLTEXT_TDM_PROHIBITED, False, "none"),
    ("noai_meta", _html("hello", head='<meta name="robots" content="noai, noimageai">'), OTHER, pr.FULLTEXT_TDM_PROHIBITED, False, "none"),
    ("reserved_foreign", _html("© 2026 Publisher. All rights reserved."), OTHER, pr.ALL_RIGHTS_RESERVED, False, "none"),
    ("reserved_ir_fa", _html("کلیه حقوق این سایت محفوظ است."), IR, pr.OWNER_RIGHTS_INDEX_ONLY, True, "short_attributed_passage"),
    ("reserved_ir_ac", _html("All rights reserved."), IR_AC, pr.OWNER_RIGHTS_INDEX_ONLY, True, "short_attributed_passage"),
    ("copyright_notice_only_ir", _html("© وزارت بهداشت"), IR, pr.OWNER_RIGHTS_INDEX_ONLY, True, "short_attributed_passage"),
    ("copyright_notice_only_foreign", _html("© 2026 Some Site"), OTHER, pr.UNKNOWN_RIGHTS, True, "passage"),
    ("silent_page", _html("hello"), OTHER, pr.UNKNOWN_RIGHTS, True, "passage"),
]


@pytest.mark.parametrize("cid,body,url,cls,allowed,mode", CASES, ids=[c[0] for c in CASES])
def test_page_rights_matrix(cid, body, url, cls, allowed, mode):
    v = pr.classify_page_rights(body, url)
    assert (v.rights_class, v.allowed, v.serve_mode) == (cls, allowed, mode), v


def test_strict_mode_blocks_a_silent_page_but_keeps_explicit_open_ones():
    assert pr.classify_page_rights(_html("hello"), OTHER, strict=True).allowed is False
    assert pr.classify_page_rights(_html("CC BY 4.0"), OTHER, strict=True).allowed is True
    assert pr.classify_page_rights(_html("hello"), OTHER, strict=False).allowed is True


def test_the_stricter_signal_always_wins_regardless_of_order():
    a = pr.classify_page_rights(_html("CC BY 4.0 and also CC BY-NC"), OTHER)
    b = pr.classify_page_rights(_html("CC BY-NC and also CC BY 4.0"), OTHER)
    assert a.allowed is False and b.allowed is False and a.rights_class == b.rights_class


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://behdasht.gov.ir/x", True),
        ("https://www.irimc.org/y", True),
        ("https://hospital.sbmu.ac.ir/z", True),
        ("https://shop.ir/book", False),  # .ir alone is NOT approved
        ("https://example.com", False),
        ("not a url", False),
        ("", False),
    ],
)
def test_only_approved_iranian_hosts_get_the_index_only_class(url, expected):
    assert pr.is_iranian_index_host(url) is expected


def test_non_approved_ir_host_with_rights_reserved_stays_blocked():
    v = pr.classify_page_rights(_html("All rights reserved"), "https://shop.ir/book")
    assert v.rights_class == pr.ALL_RIGHTS_RESERVED and v.allowed is False


def test_detector_never_raises_on_odd_input():
    for body in (b"", None, b"\xff\xfe\x00bad", "plain string", b"<" * 5000):
        v = pr.classify_page_rights(body, OTHER)
        assert isinstance(v.allowed, bool)


# ---- the gate at the fetch seam: shadow by default, enforce behind the flag ----------------------------------------------
def _env(body: bytes):
    return SimpleNamespace(body=body, charset="utf-8")


def test_shadow_mode_logs_and_never_blocks(monkeypatch, caplog):
    monkeypatch.delenv(pr.ENFORCE_ENV, raising=False)
    blocked = _env(_html('<a href="https://creativecommons.org/licenses/by-nc/4.0/">x</a>'))
    with caplog.at_level("INFO", logger=pr.logger.name):
        v = pr.apply_page_rights_gate(blocked, url=OTHER)
    assert v is not None and v.allowed is False
    assert any("i5_page_rights enforce=False" in r.getMessage() for r in caplog.records)


def test_enforce_mode_blocks_a_blocked_page_and_lets_allowed_ones_through(monkeypatch):
    monkeypatch.setenv(pr.ENFORCE_ENV, "1")
    with pytest.raises(AdapterFrameworkError) as e:
        pr.apply_page_rights_gate(_env(_html("Creative Commons Attribution-NonCommercial")), url=OTHER)
    assert e.value.category == "REVIEW_REQUIRED" and "RIGHTS_BLOCKED" in str(e.value)
    assert pr.apply_page_rights_gate(_env(_html("CC BY 4.0")), url=OTHER).allowed is True
    assert pr.apply_page_rights_gate(_env(_html("hello")), url=OTHER).allowed is True  # silent page: manifest licence stands


def test_the_gate_is_fail_open_when_the_detector_breaks(monkeypatch):
    monkeypatch.setenv(pr.ENFORCE_ENV, "1")
    monkeypatch.setattr(pr, "classify_page_rights", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert pr.apply_page_rights_gate(_env(b"<html></html>"), url=OTHER) is None
    assert pr.apply_page_rights_gate(SimpleNamespace(body=b"", charset="utf-8"), url=OTHER) is None


def test_index_only_content_is_short_at_serving_time_by_the_existing_cap():
    """Codex P2 (rejected as a code change, pinned instead): the weekly path keeps only extracted statements with a citation
    (raw retention is minimal evidence) and serving cuts every statement to MAX_SERVING_CONTEXT_CHARS, so an
    OWNER_RIGHTS_INDEX_ONLY page can only ever reach a user as a short attributed passage."""
    from backend.app.services.scis.governed_runtime_adapter import MAX_SERVING_CONTEXT_CHARS

    assert MAX_SERVING_CONTEXT_CHARS <= 600
    assert pr.classify_page_rights(_html("کلیه حقوق محفوظ است"), IR).serve_mode == "short_attributed_passage"


def test_the_fetch_adapter_calls_the_gate_after_the_envelope():
    import inspect

    from backend.app.services.i5.adapters import public_web_fetch

    src = inspect.getsource(public_web_fetch)
    assert src.index("apply_page_rights_gate(envelope") > src.rindex("build_fetch_envelope(")


def test_vocabulary_is_compatible_with_the_book_rights_classes():
    from backend.app.services.i5.enums import BookRightsClass

    known = {c.value for c in BookRightsClass}
    for cls in (pr.OPEN_AUTOMATION_ALLOWED, pr.PUBLIC_DOMAIN, pr.OPEN_LICENSE_RESTRICTED, pr.FULLTEXT_TDM_PROHIBITED, pr.UNKNOWN_RIGHTS):
        assert cls in known, cls

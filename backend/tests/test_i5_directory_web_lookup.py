"""D-019: transient web search for providers (offline, fake client). Nothing is written to the directory."""
import json
from types import SimpleNamespace

import pytest

from backend.app.services.i5 import directory_web_lookup as wl


class _FakeClient:
    def __init__(self, results):
        self.calls = []
        self.responses = SimpleNamespace(create=self._create)
        self._results = results

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(output_text=json.dumps({"results": self._results}))


def _r(**kw):
    base = {"name": "دکتر الف", "specialty": "متخصص قلب", "city": "شیراز", "address": "شیراز، خیابان زند",
            "phone": "071-32345678", "source_url": "https://www.paziresh24.com/dr/x/"}
    return {**base, **kw}


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    wl._cache.clear()
    wl._usage.clear()
    monkeypatch.delenv(wl.FLAG, raising=False)
    yield
    wl._cache.clear()
    wl._usage.clear()


def test_query_is_structured_only_and_needs_city():
    assert wl.build_query("SPECIALIST", "قلب", None, None) is None
    assert wl.build_query("SPECIALIST", "قلب", "شیراز", "فارس") == "قلب پزشک شیراز, فارس"


def test_any_real_site_is_accepted_but_trust_is_marked_and_ranked():
    items = [
        _r(name="کلینیک شخصی", source_url="https://dr-heart.ir/contact"),
        _r(name="دکتر ب", source_url="https://www.paziresh24.com/dr/b/"),
        _r(name="بیمارستان", source_url="https://hospital.sums.ac.ir/about"),
    ]
    out = wl.validate_results(items, city="شیراز")
    assert [o["trusted"] for o in out] == [True, True, False]
    assert out[2]["source_url"] == "https://dr-heart.ir/contact"


def test_validation_drops_search_engines_city_mismatch_mobile_only_and_bad_urls():
    items = [
        _r(source_url="https://www.google.com/search?q=x"),
        _r(name="ب", city="تهران", address="تهران"),
        _r(name="ج", address="", phone="09121234567"),
        _r(name="د", source_url="not a url"),
        _r(name="ه", source_url="https://clinic.example.ir/", phone="071-33334444"),
    ]
    out = wl.validate_results(items, city="شیراز")
    assert [o["name"] for o in out] == ["ه"] and out[0]["phone"] == "07133334444"


def test_flag_off_means_no_call(monkeypatch):
    c = _FakeClient([_r()])
    assert wl.search_web_providers(entity="SPECIALIST", specialty="قلب", city="شیراز", province=None, client=c) == []
    assert c.calls == []


def test_outbound_input_never_contains_user_text_and_results_are_cached(monkeypatch):
    monkeypatch.setenv(wl.FLAG, "true")
    c = _FakeClient([_r()])
    first = wl.search_web_providers(entity="SPECIALIST", specialty="قلب", city="شیراز", province=None, client=c)
    again = wl.search_web_providers(entity="SPECIALIST", specialty="قلب", city="شیراز", province=None, client=c)
    assert first == again and len(first) == 1 and len(c.calls) == 1
    assert c.calls[0]["input"] == "قلب پزشک شیراز" and c.calls[0]["tools"] == [{"type": "web_search"}]


def test_errors_never_raise_and_daily_cap(monkeypatch):
    monkeypatch.setenv(wl.FLAG, "true")
    bad = SimpleNamespace(responses=SimpleNamespace(create=lambda **k: (_ for _ in ()).throw(RuntimeError("down"))))
    assert wl.search_web_providers(entity="SPECIALIST", specialty="قلب", city="شیراز", province=None, client=bad) == []
    monkeypatch.setenv(wl.DAILY_CAP_ENV, "1")
    wl._usage.clear()
    assert wl._take_quota() is True and wl._take_quota() is False


def _facade(monkeypatch, local_rows, web_results):
    from backend.app.services.i5 import care_navigation_directory as cn

    monkeypatch.setenv(wl.FLAG, "true")
    monkeypatch.setattr(cn, "_dispatch_governed_search", lambda db, req: local_rows)
    monkeypatch.setattr(cn._web_lookup, "search_web_providers", lambda **k: web_results)
    return cn


def test_facade_adds_web_results_with_link_and_caveat_when_governed_has_none(monkeypatch):
    web = wl.validate_results([_r(name="کلینیک قلب شیراز", source_url="https://dr-heart.ir/contact")], city="شیراز")
    cn = _facade(monkeypatch, [], web)
    res = cn.query_governed_directory(None, cn.parse_care_nav_request("یه متخصص قلب در شیراز معرفی کن", language="fa"))
    assert res.status == cn.STATUS_VERIFIED and "WEB_SEARCH_ENRICHED" in res.identity_notes
    assert "کلینیک قلب شیراز" in res.user_message and "https://dr-heart.ir/contact" in res.user_message
    assert "تأیید نشده" in res.user_message  # unverified-site caveat


def test_facade_trusted_listing_has_link_without_caveat(monkeypatch):
    web = wl.validate_results([_r()], city="شیراز")
    cn = _facade(monkeypatch, [], web)
    res = cn.query_governed_directory(None, cn.parse_care_nav_request("یه متخصص قلب در شیراز معرفی کن", language="fa"))
    assert "https://www.paziresh24.com/dr/x/" in res.user_message and "تأیید نشده" not in res.user_message


def test_facade_does_not_search_when_governed_has_enough(monkeypatch):
    from backend.app.services.i5 import care_navigation_directory as cn

    rows = [{"id": i, "entity_type": "DOCTOR", "full_name": f"دکتر {i}", "specialty": "قلب", "city": "شیراز", "province": "فارس",
             "record_state": "ACTIVE", "source_system_label": "irimc_member_search", "canonical_directory_key": f"k{i}",
             "last_verified_at": None} for i in (1, 2)]
    called = []
    monkeypatch.setenv(wl.FLAG, "true")
    monkeypatch.setattr(cn, "_dispatch_governed_search", lambda db, req: rows)
    monkeypatch.setattr(cn._web_lookup, "search_web_providers", lambda **k: called.append(1) or [])
    res = cn.query_governed_directory(None, cn.parse_care_nav_request("یه متخصص قلب در شیراز", language="fa"))
    assert res.status == cn.STATUS_VERIFIED and called == []


def test_laboratory_uses_web_search_only_and_keeps_governed_gate_closed(monkeypatch):
    web = wl.validate_results([_r(name="آزمایشگاه نور", specialty="آزمایشگاه", source_url="https://noorlab.ir/")], city="شیراز")
    cn = _facade(monkeypatch, [], web)
    assert cn.LAB_POPULATION_AUTHORIZED is False
    res = cn.query_governed_directory(None, cn.parse_care_nav_request("یه آزمایشگاه در شیراز پیشنهاد بده", language="fa"))
    assert res.status == cn.STATUS_VERIFIED and "آزمایشگاه نور" in res.user_message and "WEB_SEARCH_ONLY" in res.identity_notes
    cn2 = _facade(monkeypatch, [], [])
    none = cn2.query_governed_directory(None, cn2.parse_care_nav_request("یه آزمایشگاه در شیراز پیشنهاد بده", language="fa"))
    assert none.status == cn2.STATUS_NO_VERIFIED


def test_nothing_is_written_to_the_directory(monkeypatch):
    import inspect

    src = inspect.getsource(wl)
    assert "apply_plan" not in src and "db.add" not in src and "session" not in src.lower()

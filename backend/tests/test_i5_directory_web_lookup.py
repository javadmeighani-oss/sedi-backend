"""D-016: on-demand web lookup feeding the governed directory (offline, fake client)."""
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


GOOD = {"name": "دکتر الف", "specialty": "متخصص قلب", "city": "شیراز", "address": "شیراز، خیابان زند",
        "phone": "071-32345678", "source_url": "https://www.paziresh24.com/dr/x/"}


def test_query_is_structured_only_and_needs_city():
    assert wl.build_query("SPECIALIST", "قلب", None, None) is None
    q = wl.build_query("SPECIALIST", "قلب", "شیراز", "فارس")
    assert q == "قلب پزشک شیراز, فارس"


def test_trusted_domains():
    assert wl.is_trusted_url("https://www.paziresh24.com/dr/x/")
    assert wl.is_trusted_url("https://hospital.sums.ac.ir/about")
    assert not wl.is_trusted_url("https://random-blog.ir/top-doctors")
    assert not wl.is_trusted_url("https://paziresh24.com.evil.io/x")


def test_validation_drops_untrusted_city_mismatch_and_mobile_only():
    items = [GOOD,
             {**GOOD, "source_url": "https://blog.example.com/x"},
             {**GOOD, "name": "ب", "city": "تهران", "address": "تهران"},
             {**GOOD, "name": "ج", "address": "", "phone": "09121234567"}]
    out = wl.validate_results(items, city="شیراز")
    assert [o["name"] for o in out] == ["دکتر الف"] and out[0]["phone"] == "07132345678"


def test_flag_off_means_no_call(monkeypatch):
    monkeypatch.delenv(wl.FLAG, raising=False)
    c = _FakeClient([GOOD])
    assert wl.lookup_and_store(None, entity="SPECIALIST", specialty="قلب", city="شیراز", province=None, client=c) == []
    assert c.calls == []


def test_lab_never_looked_up_and_errors_never_raise(monkeypatch):
    monkeypatch.setenv(wl.FLAG, "true")
    c = _FakeClient([GOOD])
    assert wl.lookup_and_store(None, entity="LABORATORY", specialty=None, city="شیراز", province=None, client=c) == []
    bad = SimpleNamespace(responses=SimpleNamespace(create=lambda **k: (_ for _ in ()).throw(RuntimeError("down"))))
    assert wl.lookup_and_store(None, entity="SPECIALIST", specialty="قلب", city="شیراز", province=None, client=bad) == []


def test_outbound_input_never_contains_user_text(monkeypatch):
    monkeypatch.setenv(wl.FLAG, "true")
    c = _FakeClient([])
    wl.lookup_and_store(None, entity="SPECIALIST", specialty="قلب", city="شیراز", province=None, client=c)
    assert c.calls and c.calls[0]["input"] == "قلب پزشک شیراز"
    assert c.calls[0]["tools"] == [{"type": "web_search"}]


def test_daily_cap(monkeypatch):
    monkeypatch.setenv(wl.DAILY_CAP_ENV, "1")
    wl._usage.clear()
    assert wl._take_quota() is True and wl._take_quota() is False
    wl._usage.clear()


def test_records_carry_source_domain_and_family():
    recs = wl.to_directory_records(wl.validate_results([GOOD], city="شیراز"), entity="SPECIALIST", province="فارس")
    assert recs[0]["entity_family"] == "DOCTOR" and wl.source_domain(recs[0]["canonical_directory_key"]) == "paziresh24.com"
    from backend.app.services.i5.iran_directory_normalization import normalize_records
    valid, rej = normalize_records(recs)
    assert len(valid) == 1 and not rej


def test_facade_enriches_through_governed_store(monkeypatch):
    from backend.app.services.i5 import care_navigation_directory as cn

    monkeypatch.setenv(wl.FLAG, "true")
    key = "web_lookup:paziresh24.com:abc"
    row = {"id": 9, "entity_type": "DOCTOR", "full_name": "دکتر الف", "specialty": "متخصص قلب", "city": "شیراز",
           "province": "فارس", "record_state": "ACTIVE", "source_system_label": "web_lookup",
           "canonical_directory_key": key, "address": "شیراز، خیابان زند", "phone": "07132345678",
           "last_verified_at": None}
    calls = {"n": 0}

    def dispatch(db, req):
        calls["n"] += 1
        return [] if calls["n"] == 1 else [{**row, "last_verified_at": __import__("datetime").datetime.utcnow().isoformat()}]

    monkeypatch.setattr(cn, "_dispatch_governed_search", dispatch)
    monkeypatch.setattr(cn._web_lookup, "lookup_and_store", lambda db, **k: [key])
    res = cn.query_governed_directory(None, cn.parse_care_nav_request("یه متخصص قلب در شیراز معرفی کن", language="fa"))
    assert res.status == cn.STATUS_VERIFIED and "دکتر الف" in res.user_message
    assert "WEB_LOOKUP_ENRICHED" in res.identity_notes
    assert "paziresh24" not in res.user_message  # source only on request
    asked = cn.query_governed_directory(None, cn.parse_care_nav_request("یه متخصص قلب در شیراز معرفی کن، منبعش چیه", language="fa"))
    assert "paziresh24.com" in asked.user_message


def test_stale_web_rows_are_ignored():
    from datetime import datetime, timedelta
    assert wl.is_stale_web_row("web_lookup", datetime.utcnow() - timedelta(days=40))
    assert not wl.is_stale_web_row("web_lookup", datetime.utcnow())
    assert not wl.is_stale_web_row("irimc_member_search", None)

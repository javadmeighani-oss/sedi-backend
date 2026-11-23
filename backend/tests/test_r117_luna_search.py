"""R-117 (Javad 2026-11-23): provider search + nearby geography use gpt-6-luna, inside a per-request TIME budget (Luna answers in ~25 s)."""
import json
from types import SimpleNamespace

import pytest

from backend.app.services.i5 import directory_web_lookup as web
from backend.app.services.i5 import nearby_places as nb


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv(web.FLAG, "1")
    monkeypatch.delenv(web.MODEL_ENV, raising=False)
    monkeypatch.setattr(web, "_take_quota", lambda: True)
    web._cache.clear()
    nb._cache.clear()


class _Client:
    def __init__(self, payload):
        self.kwargs = []
        self._payload = payload
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.kwargs.append(kw)
        return SimpleNamespace(output_text=self._payload)


def test_luna_is_the_default_and_the_env_can_override(monkeypatch):
    assert web.search_model() == "gpt-6-luna" == web.DEFAULT_MODEL
    monkeypatch.setenv(web.MODEL_ENV, "gpt-4o-mini")
    assert web.search_model() == "gpt-4o-mini"
    monkeypatch.setenv(web.MODEL_ENV, "   ")
    assert web.search_model() == "gpt-6-luna"                                   # a blank override is no override


def test_the_provider_search_and_the_geography_call_use_the_search_model():
    search = _Client(json.dumps({"results": []}))
    web._call_web_search("q", "IR", search)
    geo = _Client(json.dumps({"origin": {"lat": 35.73, "lon": 51.87}, "places": []}))
    nb.nearby_rings("بومهن", client=geo)
    assert search.kwargs[0]["model"] == "gpt-6-luna" and geo.kwargs[0]["model"] == "gpt-6-luna"


def test_without_a_budget_scope_the_call_has_no_extra_timeout():
    client = _Client(json.dumps({"results": []}))
    web._call_web_search("q", "IR", client)
    assert "timeout" not in client.kwargs[0] and web.call_options() == {} and web.remaining_seconds() is None and web.budget_left()


def test_inside_a_budget_the_provider_call_gets_the_seconds_left_as_its_timeout():
    client = _Client(json.dumps({"results": []}))
    with web.request_budget(8, seconds=40):
        web._call_web_search("q", "IR", client)
        assert 5.0 <= client.kwargs[0]["timeout"] <= 40.0
        geo = _Client(json.dumps({"origin": {"lat": 35.73, "lon": 51.87}, "places": []}))
        nb.nearby_rings("پردیس", client=geo)
        assert 5.0 <= geo.kwargs[0]["timeout"] <= 40.0
    with web.request_budget(8, seconds=0.01):
        assert web.call_options()["timeout"] == 5.0                              # never below a usable minimum


def test_a_request_never_runs_past_its_time_budget(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(web.time, "monotonic", lambda: clock["t"])
    calls = []
    monkeypatch.setattr(web, "_call_web_search", lambda q, c, client=None: calls.append(q) or [])
    with web.request_budget(8, seconds=60) as budget:
        web.search_web_providers(entity="SPECIALIST", specialty="گوارش", city="پردیس", province="تهران")
        first = len(calls)
        assert web.budget_left() and first >= 1
        clock["t"] += 61                                                         # a slow Luna answer used the whole minute
        assert not web.budget_left() and web.remaining_seconds() == 0.0
        web.search_web_providers(entity="SPECIALIST", specialty="پوست", city="رودهن", province="تهران")
        assert len(calls) == first and budget["queries"] == first                # no further search, no further spend


def test_the_ring_chain_stops_when_the_time_is_spent(monkeypatch):
    from backend.app.services.i5 import care_navigation_directory as cn

    clock = {"t": 0.0}
    monkeypatch.setattr(web.time, "monotonic", lambda: clock["t"])
    tried = []

    def query(db, request):
        tried.append(request.area or request.city)
        clock["t"] += 30                                                         # every ring search takes 30 s
        return cn.CareNavResult(status=cn.STATUS_NO_VERIFIED, entity=cn.CareNavEntity.SPECIALIST)

    monkeypatch.setattr(cn, "query_governed_directory", query)
    monkeypatch.setattr(nb, "nearby_rings", lambda origin, **k: [["الف", "ب", "پ"], ["ت", "ث", "ج"]])
    req = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALIST, specialty_or_service="گوارش", city="بومهن", province="تهران", language="fa")
    original = cn.CareNavResult(status=cn.STATUS_NO_VERIFIED, entity=cn.CareNavEntity.SPECIALIST)
    with web.request_budget(8, seconds=60):
        assert cn._nearest_area_result(None, req, original) is original
    assert tried == ["الف", "ب"]                                                  # two 30-second searches fit in the minute, the third does not start

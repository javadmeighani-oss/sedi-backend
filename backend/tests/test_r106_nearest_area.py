"""R-106 (Javad 2026-11-20): nothing found in the confirmed place -> Sedi finds it in the NEAREST area and says so, instead of «not found».

DB-free: the model client and the governed directory query are stubbed; the cleaning, cache, cap, order and wording run for real.
"""
import json
from types import SimpleNamespace

import pytest

from backend.app import sedi_copy
from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import directory_web_lookup as web
from backend.app.services.i5 import nearby_places as nb


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setenv(web.FLAG, "1")
    nb._cache.clear()
    monkeypatch.setattr(web, "_take_quota", lambda: True)


class _Client:
    def __init__(self, places, raises=False):
        self.calls = []
        self._places = places
        self._raises = raises
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if self._raises:
            raise RuntimeError("model down")
        return SimpleNamespace(output_text=json.dumps({"places": self._places}, ensure_ascii=False))


# --- the places ----------------------------------------------------------------------------------------------------------------------------------
def test_the_nearest_places_are_cleaned_deduplicated_and_capped_at_three():
    client = _Client(["بومهن", "پردیس", "رودهن", "بومهن", "https://x.ir", "منطقه ۸", "دماوند", "لواسان"])
    assert nb.nearby_places("پردیس", client=client) == ["بومهن", "رودهن", "دماوند"]  # origin, duplicates, URLs and digits dropped
    kw = client.calls[0]
    assert kw["input"] == "پردیس" and "nearest first" in kw["instructions"] and "tools" not in kw  # one short call, no web tool, only a place name


def test_disabled_over_cap_and_errors_return_nothing(monkeypatch):
    assert nb.nearby_places("پردیس", client=_Client(["بومهن"])) == ["بومهن"]
    nb._cache.clear()
    monkeypatch.delenv(web.FLAG)
    assert nb.nearby_places("پردیس", client=_Client(["بومهن"])) == []
    monkeypatch.setenv(web.FLAG, "1")
    monkeypatch.setattr(web, "_take_quota", lambda: False)
    assert nb.nearby_places("پردیس", client=_Client(["بومهن"])) == []
    monkeypatch.setattr(web, "_take_quota", lambda: True)
    assert nb.nearby_places("پردیس", client=_Client([], raises=True)) == [] and nb.nearby_places("", client=_Client(["x"])) == []


def test_the_answer_is_cached_per_place():
    client = _Client(["بومهن", "رودهن"])
    assert nb.nearby_places("پردیس", client=client) == nb.nearby_places("پردیس ", client=client) == ["بومهن", "رودهن"]
    assert len(client.calls) == 1  # no second paid call for the same place


# --- the fallback ----------------------------------------------------------------------------------------------------------------------------------
def _result(status, text="X", n=0):
    return cn.CareNavResult(status=status, entity=cn.CareNavEntity.SPECIALIST, identities=tuple(SimpleNamespace() for _ in range(n)), user_message=text)


def _req(**kw):
    base = dict(entity=cn.CareNavEntity.SPECIALIST, specialty_or_service="قلب", city="پردیس", language="fa")
    base.update(kw)
    return cn.CareNavRequest(**base)


def _stub(monkeypatch, places, verified_at):
    tried = []

    def query(db, request):
        tried.append(request.area or request.city)
        if (request.area or request.city) == verified_at:
            return _result(cn.STATUS_VERIFIED, "LIST", 2)
        return _result(cn.STATUS_NO_VERIFIED)

    monkeypatch.setattr(cn, "query_governed_directory", query)
    monkeypatch.setattr(nb, "nearby_places", lambda origin, **k: list(places))
    return tried


def test_nothing_in_the_place_is_found_in_the_nearest_area_and_said_so(monkeypatch):
    tried = _stub(monkeypatch, ["بومهن", "رودهن"], "رودهن")
    out = cn._nearest_area_result(None, _req(), _result(cn.STATUS_NO_VERIFIED))
    assert out.status == cn.STATUS_VERIFIED and out.user_message.endswith("LIST")
    assert out.user_message.startswith(sedi_copy.t("care_nav.nearest_found", "fa", where="پردیس", found="رودهن"))
    assert "پیدا نشد" not in out.user_message  # not «not found»
    assert tried == ["بومهن", "رودهن"]  # nearest first, stops at the first area with results


def test_at_most_three_areas_are_tried_and_the_plain_answer_remains_only_when_all_are_empty(monkeypatch):
    tried = _stub(monkeypatch, ["الف", "ب", "ج", "د"], "هیچ‌کجا")
    original = _result(cn.STATUS_NO_VERIFIED, "NOT-FOUND")
    out = cn._nearest_area_result(None, _req(), original)
    assert out is original and tried == ["الف", "ب", "ج", "د"][: len(tried)] and len(tried) <= 4  # nearby_places already caps at 3


def test_a_verified_result_or_a_request_without_a_place_is_untouched(monkeypatch):
    _stub(monkeypatch, ["بومهن"], "بومهن")
    ok = _result(cn.STATUS_VERIFIED, "OK", 1)
    assert cn._nearest_area_result(None, _req(), ok) is ok
    no_place = _result(cn.STATUS_NO_VERIFIED, "ASK")
    assert cn._nearest_area_result(None, _req(city=None, area=None), no_place) is no_place


def test_an_error_keeps_the_ordinary_answer(monkeypatch):
    monkeypatch.setattr(nb, "nearby_places", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    original = _result(cn.STATUS_NO_VERIFIED, "NOT-FOUND")
    assert cn._nearest_area_result(None, _req(), original) is original


def _searched(monkeypatch, origin_req, names):
    seen = []
    monkeypatch.setattr(cn, "query_governed_directory", lambda db, r: seen.append((r.area, r.city)) or _result(cn.STATUS_NO_VERIFIED))
    monkeypatch.setattr(nb, "nearby_places", lambda origin, **k: list(names))
    cn._nearest_area_result(None, origin_req, _result(cn.STATUS_NO_VERIFIED))
    return [(a.replace(chr(0x200c), "") if a else a, c) for a, c in seen]


def test_a_neighbourhood_keeps_its_confirmed_city_and_a_town_becomes_the_city(monkeypatch):
    seen = _searched(monkeypatch, _req(area="تهران‌پارس", city="تهران"), ["نارمک", "کرج"])
    assert seen[0] == ("نارمک", "تهران")  # a neighbouring neighbourhood stays in the confirmed city
    assert seen[1] == (None, "کرج")        # a different KNOWN city is searched as a city


def test_p2_a_neighbouring_name_that_the_gazetteer_calls_a_tehran_area_never_switches_a_mashhad_search_to_tehran(monkeypatch):
    seen = _searched(monkeypatch, _req(area="وکیل‌آباد", city="مشهد"), ["نارمک", "احمدآباد"])
    assert seen == [("نارمک", "مشهد"), ("احمدآباد", "مشهد")]  # never city «تهران»; an unknown neighbourhood stays inside Mashhad


def test_p2_a_city_origin_searches_adjacent_towns_as_cities(monkeypatch):
    seen = _searched(monkeypatch, _req(area=None, city="پردیس"), ["بومهن", "رودهن"])
    assert seen == [(None, "بومهن"), (None, "رودهن")]


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_the_wording_says_the_nearest_area_in_every_language(lang):
    text = sedi_copy.t("care_nav.nearest_found", lang, where="پردیس", found="بومهن")
    assert "بومهن" in text and "پردیس" in text and "{" not in text


# --- through the public entry point ----------------------------------------------------------------------------------------------------------------------
def test_resolve_care_navigation_returns_the_nearest_area_answer(monkeypatch):
    _stub(monkeypatch, ["بومهن"], "بومهن")
    out = cn.resolve_care_navigation(None, "یه دکتر قلب در شهر پردیس معرفی کن", language="fa")
    assert out.status == cn.STATUS_VERIFIED and "بومهن" in out.user_message and out.user_message.endswith("LIST")

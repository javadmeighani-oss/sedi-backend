"""R-114 am.1 (PR-A2b): the provider search is polished and the nearest-area fallback is a RING CHAIN (Boumehen -> Pardis -> the nearest part of
Tehran ...). DB-free: the model client, the governed directory and the page checks are stubbed; ranking, validation, rings, the specialty
filter, the budget and the wording run for real."""
import json
from types import SimpleNamespace

import pytest

from backend.app import sedi_copy
from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import directory_web_lookup as web
from backend.app.services.i5 import nearby_places as nb
from backend.app.services.i5 import specialty_lexicon as lexicon

# approximate centres (WGS84): the pilot place and its surroundings
BOUMEHEN = {"lat": 35.73, "lon": 51.87}
RUDEHEN = {"name": "رودهن", "lat": 35.74, "lon": 51.90}
PARDIS = {"name": "پردیس", "lat": 35.74, "lon": 51.77}
TEHRANPARS = {"name": "تهرانپارس", "lat": 35.74, "lon": 51.52}
SHAHRAK_GHARB = {"name": "شهرک غرب", "lat": 35.76, "lon": 51.37}
NEAR_TEHRAN = {"name": "لشکرآباد", "lat": 35.73, "lon": 51.62}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv(web.FLAG, "1")
    monkeypatch.setattr(web, "_take_quota", lambda: True)
    nb._cache.clear()
    web._cache.clear()


def _json(origin, places):
    return json.dumps({"origin": origin, "places": places}, ensure_ascii=False)


class _Client:
    def __init__(self, payload):
        self.calls = []
        self._payload = payload
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(output_text=self._payload)


# --- geography: the CODE decides nearness ----------------------------------------------------------------------------------------------------------------
def test_the_distance_is_computed_not_trusted():
    assert 2.0 < nb.haversine_km((BOUMEHEN["lat"], BOUMEHEN["lon"]), (RUDEHEN["lat"], RUDEHEN["lon"])) < 4.0
    assert 28.0 < nb.haversine_km((BOUMEHEN["lat"], BOUMEHEN["lon"]), (TEHRANPARS["lat"], TEHRANPARS["lon"])) < 34.0


def test_the_model_order_is_replaced_by_the_computed_distance_order():
    data = {"origin": BOUMEHEN, "places": [SHAHRAK_GHARB, TEHRANPARS, PARDIS, RUDEHEN]}  # the model listed the FAR ones first
    ranked, validated = nb.rank_places(data, "بومهن")
    assert validated and [n for n, _ in ranked] == ["رودهن", "پردیس", "تهرانپارس", "شهرک غرب"]
    assert [km for _, km in ranked] == sorted(km for _, km in ranked)


def test_impossible_candidates_are_rejected():
    data = {"origin": BOUMEHEN, "places": [
        {"name": "جای دور", "lat": 10.0, "lon": 51.8},       # outside Iran
        {"name": "بومهن", "lat": 35.73, "lon": 51.87},       # the origin itself
        {"name": "هم‌مرکز", "lat": 35.7301, "lon": 51.8701},   # the same spot under another name
        {"name": "x", "lat": 35.74, "lon": 51.9},            # too short a name
        {"name": "ناحیه ۸", "lat": 35.74, "lon": 51.9},      # a digit
        {"name": "https://x.ir", "lat": 35.74, "lon": 51.9},
        PARDIS, {"name": "پردیس", "lat": 35.75, "lon": 51.78},  # a duplicate name
    ]}
    ranked, validated = nb.rank_places(data, "بومهن")
    assert validated and [n for n, _ in ranked] == ["پردیس"]


def test_without_usable_origin_coordinates_the_model_order_is_kept_and_nothing_is_validated():
    ranked, validated = nb.rank_places({"origin": {"lat": 0, "lon": 0}, "places": [PARDIS, RUDEHEN]}, "بومهن")
    assert not validated and [n for n, _ in ranked] == ["پردیس", "رودهن"]
    legacy, validated = nb.rank_places({"places": ["پردیس", "رودهن", "بومهن", "دماوند", "لواسان"]}, "بومهن")
    assert not validated and [n for n, _ in legacy] == ["پردیس", "رودهن", "دماوند"]   # the old shape: at most one ring of three, origin dropped
    assert nb.build_rings(legacy, validated) == [["پردیس", "رودهن", "دماوند"]]


def test_rings_fill_in_distance_order_with_a_cap_per_ring():
    ranked = [("الف", 3.0), ("ب", 8.0), ("پ", 12.0), ("ت", 30.0), ("ث", 33.0), ("ج", 40.0), ("چ", 44.0), ("ح", 60.0), ("خ", 90.0)]
    rings = nb.build_rings(ranked, True)
    assert rings == [["الف", "ب", "پ"], ["ت", "ث", "ج"], ["چ", "ح"]]      # «خ» (90 km) is beyond the last cap and never offered
    assert all(len(r) <= nb.MAX_PLACES for r in rings) and len(rings) <= nb.MAX_RINGS


def test_a_sparse_surrounding_skips_to_the_ring_whose_cap_fits():
    assert nb.build_rings([("دور", 40.0)], True) == [["دور"]]          # nothing within ring 1's 25 km: the place still gets offered in ring 2
    assert nb.build_rings([("خیلی دور", 120.0)], True) == []


def test_the_pilot_chain_boumehen_pardis_then_the_nearest_part_of_tehran():
    client = _Client(_json(BOUMEHEN, [SHAHRAK_GHARB, NEAR_TEHRAN, PARDIS, RUDEHEN, TEHRANPARS]))
    rings = nb.nearby_rings("بومهن", client=client)
    assert rings[0] == ["رودهن", "پردیس", "لشکرآباد"]                  # ring 1: the nearest towns, then the NEAREST part of Tehran (~23 km)
    assert "تهرانپارس" in rings[1] and all("شهرک غرب" not in r for r in rings[:1])
    flat = [n for r in rings for n in r]
    assert flat.index("لشکرآباد") < flat.index("تهرانپارس") < flat.index("شهرک غرب")   # the far west of Tehran comes last, never first


def test_one_call_per_place_and_it_spends_the_request_budget(monkeypatch):
    client = _Client(_json(BOUMEHEN, [PARDIS, RUDEHEN]))
    with web.request_budget(8) as budget:
        assert nb.nearby_rings("بومهن", client=client) == nb.nearby_rings("بومهن ", client=client)
        assert budget["queries"] == 1                                  # the second call is cached: no second paid call
    assert len(client.calls) == 1 and "lat" in json.dumps(client.calls[0]["text"])   # the model is asked for coordinates


def test_a_spent_budget_or_a_failing_model_gives_no_rings():
    with web.request_budget(0):
        assert nb.nearby_rings("بومهن", client=_Client(_json(BOUMEHEN, [PARDIS]))) == []
    nb._cache.clear()

    class _Boom:
        responses = SimpleNamespace(create=lambda **k: (_ for _ in ()).throw(RuntimeError("down")))

    assert nb.nearby_rings("بومهن", client=_Boom()) == [] and nb.nearby_places("", client=_Boom()) == []


# --- the query and the results -------------------------------------------------------------------------------------------------------------------------
def test_a_doctor_query_reads_like_the_booking_sites_and_an_area_alone_is_a_place():
    assert web.build_query("SPECIALIST", "گوارش", "بومهن", "تهران") == "متخصص گوارش در بومهن, تهران"
    assert web.build_query("SPECIALIST", "گوارش", None, None, area="بومهن") == "متخصص گوارش در بومهن"     # used to skip the search
    assert web.build_query("SPECIALIST", "گوارش", None, None) is None                                       # no place at all: still no lookup
    assert web.build_query("SPECIALIST", None, "شیراز", "فارس") == "پزشک شیراز, فارس"                      # no specialty: unchanged
    assert web.build_query("LABORATORY", None, "اصفهان", None) == "آزمایشگاه اصفهان"                       # other entities: unchanged


def test_the_booking_sites_are_the_second_attempt_for_a_doctor_and_still_last_for_others():
    doctor = web._query_variants("q", "SPECIALIST", "IR")
    assert "پذیرش۲۴" in doctor[1] and doctor[2].endswith("آدرس و تلفن")
    lab = web._query_variants("q", "LABORATORY", "IR")
    assert "پذیرش۲۴" in lab[-1] and "تشخیص" not in lab[1]


def test_an_area_only_search_keeps_only_results_that_name_the_area():
    rows = [
        {"name": "دکتر الف", "city": "تهران", "address": "بومهن، خیابان اصلی", "phone": "02112345678", "source_url": "https://www.paziresh24.com/dr/a"},
        {"name": "دکتر ب", "city": "تهران", "address": "ونک", "phone": "02187654321", "source_url": "https://www.paziresh24.com/dr/b"},
    ]
    out = web.validate_results(rows, city=None, area="بومهن")
    assert [r["name"] for r in out] == ["دکتر الف"]


@pytest.mark.parametrize("specialty,spec_field,name,expected", [
    ("گوارش", "متخصص گوارش و کبد", "دکتر الف", True),
    ("گوارش", "متخصص کودکان", "دکتر ب", False),
    ("روانپزشکی", "روانشناس بالینی", "دکتر ج", False),
    ("گوش و حلق و بینی", "گوش، حلق و بینی", "دکتر د", True),
    ("گوش و حلق و بینی", "Dentist", "Dr X", False),
    ("پوست", "", "دکتر پوست و مو علوی", True),
    ("برچسب ناشناخته", "هر چیزی", "دکتر ه", True),         # an unknown label has no vocabulary: never filters
])
def test_a_result_must_be_the_requested_specialty(specialty, spec_field, name, expected):
    assert lexicon.result_matches_specialty(specialty, spec_field, name) is expected


def test_the_wrong_specialty_is_dropped_counted_and_never_shown(monkeypatch):
    rows = [{"name": "دکتر الف", "specialty": "متخصص گوارش", "city": "پردیس", "address": "پردیس، خیابان ۱", "phone": "02112345678", "source_url": "https://www.drdr.ir/a"},
            {"name": "دکتر ب", "specialty": "کودکان", "city": "پردیس", "address": "پردیس، خیابان ۲", "phone": "02187654321", "source_url": "https://www.drdr.ir/b"}]
    monkeypatch.setattr(web, "_call_web_search", lambda q, c, client=None: rows)
    monkeypatch.setattr(web, "verify_and_rank", lambda results, **k: results)
    with web.request_budget(8) as budget:
        out = web.search_web_providers(entity="SPECIALIST", specialty="گوارش", city="پردیس", province="تهران")
    assert [r["name"] for r in out] == ["دکتر الف"] and budget["dropped"] == 1 and budget["queries"] == 1


def test_the_specialty_filter_has_a_kill_switch_and_spares_other_entities(monkeypatch):
    rows = [{"name": "دکتر ب", "specialty": "کودکان"}]
    assert web._only_the_specialty(rows, "SPECIALIST", "گوارش") == []
    assert web._only_the_specialty(rows, "LABORATORY", "گوارش") == rows and web._only_the_specialty(rows, "SPECIALIST", None) == rows
    monkeypatch.setenv(web.SPEC_FILTER_DISABLED_ENV, "1")
    assert web._only_the_specialty(rows, "SPECIALIST", "گوارش") == rows


def test_one_request_never_spends_more_than_its_budget(monkeypatch):
    calls = []
    monkeypatch.setattr(web, "_call_web_search", lambda q, c, client=None: calls.append(q) or [])
    with web.request_budget(2) as budget:
        web.search_web_providers(entity="SPECIALIST", specialty="گوارش", city="پردیس", province="تهران")   # up to 3 wordings: only 2 allowed
        web.search_web_providers(entity="SPECIALIST", specialty="پوست", city="رودهن", province="تهران")    # nothing left
    assert len(calls) == 2 and budget["queries"] == 2
    with web.request_budget(1) as one:
        assert web.budget_left() and web._take_request_budget() and not web.budget_left() and one["queries"] == 1


def test_the_rating_counts_by_how_many_reviews_back_it():
    few = {"rating_avg": 5.0, "rating_count": 2, "page_read": True}
    many = {"rating_avg": 4.7, "rating_count": 400, "page_read": True}
    assert web._score(many, specialty=None, area=None, qualifiers=()) > web._score(few, specialty=None, area=None, qualifiers=())
    assert web._score({"rating_avg": 4.8, "rating_count": 50}, specialty=None, area=None, qualifiers=()) > web._score({}, specialty=None, area=None, qualifiers=())


# --- the chain through the directory facade ----------------------------------------------------------------------------------------------------------------
def _result(status, text="X", n=0):
    return cn.CareNavResult(status=status, entity=cn.CareNavEntity.SPECIALIST, identities=tuple(SimpleNamespace() for _ in range(n)), user_message=text)


def _req(**kw):
    base = dict(entity=cn.CareNavEntity.SPECIALIST, specialty_or_service="گوارش", city="بومهن", province="تهران", language="fa")
    base.update(kw)
    return cn.CareNavRequest(**base)


def _chain(monkeypatch, rings, verified_at):
    tried = []

    def query(db, request):
        tried.append(request.area or request.city)
        return _result(cn.STATUS_VERIFIED, "LIST", 2) if (request.area or request.city) == verified_at else _result(cn.STATUS_NO_VERIFIED)

    monkeypatch.setattr(cn, "query_governed_directory", query)
    monkeypatch.setattr(nb, "nearby_rings", lambda origin, **k: [list(r) for r in rings])
    return tried


def test_the_chain_goes_ring_by_ring_and_says_what_was_not_found_where(monkeypatch):
    tried = _chain(monkeypatch, [["رودهن", "پردیس"], ["لشکرآباد", "تهرانپارس"]], "لشکرآباد")
    out = cn._nearest_area_result(None, _req(), _result(cn.STATUS_NO_VERIFIED))
    assert out.status == cn.STATUS_VERIFIED and out.user_message.endswith("LIST")
    assert tried == ["رودهن", "پردیس", "لشکرآباد"]                      # nearest first, stops at the first place with a suitable result
    assert out.user_message.startswith(sedi_copy.t("care_nav.nearest_chain", "fa", tried="بومهن، رودهن، پردیس", found="لشکرآباد"))
    assert "RING_2" in out.identity_notes


def test_found_in_the_very_first_neighbour_keeps_the_short_wording(monkeypatch):
    _chain(monkeypatch, [["پردیس", "رودهن"]], "پردیس")
    out = cn._nearest_area_result(None, _req(), _result(cn.STATUS_NO_VERIFIED))
    assert out.user_message.startswith(sedi_copy.t("care_nav.nearest_found", "fa", where="بومهن", found="پردیس")) and "RING_1" in out.identity_notes


def test_nothing_in_any_ring_gives_the_honest_ordinary_answer(monkeypatch):
    tried = _chain(monkeypatch, [["الف", "ب", "پ"], ["ت", "ث", "ج"], ["چ"]], "هیچ‌جا")
    original = _result(cn.STATUS_NO_VERIFIED, "NOT FOUND")
    assert cn._nearest_area_result(None, _req(), original) is original and len(tried) == 7


def test_the_chain_stops_when_the_request_budget_is_spent(monkeypatch):
    tried = []

    def query(db, request):
        tried.append(request.area or request.city)
        with_budget = web._take_request_budget()      # what one real search would spend
        return _result(cn.STATUS_NO_VERIFIED)

    monkeypatch.setattr(cn, "query_governed_directory", query)
    monkeypatch.setattr(nb, "nearby_rings", lambda origin, **k: [["الف", "ب", "پ"], ["ت", "ث", "ج"]])
    original = _result(cn.STATUS_NO_VERIFIED)
    with web.request_budget(3):
        assert cn._nearest_area_result(None, _req(), original) is original
    assert len(tried) == 3                                              # not six: the budget decided


def test_the_whole_request_reports_its_search_counters(monkeypatch):
    monkeypatch.setattr(cn, "query_governed_directory", lambda db, r: _result(cn.STATUS_VERIFIED, "LIST", 1))
    out = cn.resolve_care_navigation(None, "یه دکتر گوارش در شهر پردیس معرفی کن", language="fa")
    assert out.status == cn.STATUS_VERIFIED and "WEB_QUERIES_0" in out.identity_notes and "SPEC_DROPPED_0" in out.identity_notes


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_the_chain_wording_exists_in_every_language(lang):
    text = sedi_copy.t("care_nav.nearest_chain", lang, tried="A، B", found="C")
    assert "A" in text and "C" in text and "{" not in text


# --- Codex round 1 on PR 213 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("requested,spec_field,name,expected", [
    ("جراحی عمومی", "جراح مغز و اعصاب", "دکتر الف", False),          # a neurosurgeon is not a general surgeon
    ("مغز و اعصاب", "متخصص اعصاب و روان", "دکتر ب", False),         # a psychiatrist is not a neurologist
    ("مغز و اعصاب", "متخصص مغز و اعصاب", "دکتر ج", True),
    ("جراحی عمومی", "جراح عمومی", "دکتر د", True),
    ("گوارش", "کودکان", "دکتر گوارش علوی", False),                  # the specialty FIELD decides before the name
    ("گوارش", "", "دکتر گوارش علوی", True),                         # no field: the name is the evidence
    ("گوارش", "", "دکتر علوی", False),                             # nothing names a specialty: no evidence
])
def test_p2_the_result_text_decides_by_the_longest_specialty_it_names(requested, spec_field, name, expected):
    assert lexicon.result_matches_specialty(requested, spec_field, name) is expected


def test_p2_wrong_specialties_cannot_use_up_the_candidate_slots(monkeypatch):
    def doc(i, spec):
        return {"name": f"دکتر {i}", "specialty": spec, "city": "پردیس", "address": f"پردیس، خیابان {i}", "phone": f"02112345{i:03d}", "source_url": f"https://www.drdr.ir/{i}"}

    rows = [doc(i, "کودکان") for i in range(1, 7)] + [doc(7, "متخصص گوارش")]          # six pediatricians first, the gastro doctor last
    monkeypatch.setattr(web, "_call_web_search", lambda q, c, client=None: rows)
    monkeypatch.setattr(web, "verify_and_rank", lambda results, **k: results)
    with web.request_budget(8) as budget:
        out = web.search_web_providers(entity="SPECIALIST", specialty="گوارش", city="پردیس", province="تهران")
    assert [r["name"] for r in out] == ["دکتر 7"] and budget["dropped"] == 6

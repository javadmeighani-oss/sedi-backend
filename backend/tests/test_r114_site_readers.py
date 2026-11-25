"""R-114 am.1 / R-116 am.1: Sedi reads the booking sites' public listing pages (real, structured data) and ranks the most credible FIVE.

The pages here are synthetic but shaped exactly like the live ones (Next.js ``__NEXT_DATA__`` of Doctoreto and Paziresh24, checked 2026-11-23).
DB-free, network-free: the page fetcher is injected."""
import json
from types import SimpleNamespace

import pytest

from backend.app.services.i5 import site_readers as sr


def _page(next_data: dict) -> bytes:
    return ("<html><head></head><body><script id=\"__NEXT_DATA__\" type=\"application/json\">" + json.dumps(next_data, ensure_ascii=False) + "</script></body></html>").encode("utf-8")


def _p24_item(name, rate_count, star, sat, lat=35.7, lon=51.4, expertise="متخصص گوارش", address="خیابان ولیعصر", city="تهران", **extra):
    item = {"type": "doctor", "record_type": "doctor", "prefix": "دکتر", "display_name": name, "display_expertise": expertise, "satisfaction": sat,
            "rates_count": rate_count, "star": star, "number_of_visits": 1200, "waiting_time": "۲۰ دقیقه", "url": "/dr/" + name.replace(" ", "-") + "/",
            "centers": [{"address": address, "city_name": city, "map": {"lat": lat, "lon": lon}}]}
    item.update(extra)
    return item


def _p24_page(items):
    return _page({"props": {"pageProps": {"dehydratedState": {"queries": [{"queryKey": ["search"], "state": {"data": {"search": {"result": items, "total": len(items)}}}}]}}}})


def _doctoreto_item(name, count, avg, percent, lat=35.72, lon=51.40, route=None):
    return {"fullName": name, "profileRoute": route or "/doctor/" + name.replace(" ", "-") + "/AbC", "specialityLabel": "فوق تخصص گوارش",
            "places": [{"address": "تهران، سعادت‌آباد", "city": {"name": "تهران", "slug": "tehran"}, "coordinates": {"latitude": lat, "longitude": lon}}],
            "rate": {"count": count, "rateAverage": avg, "percent": percent, "recommend": 90},
            "nextFreeTimes": {"general": {"fullTextDisplay": "فردا ساعت ۱۰"}}}


def _doctoreto_page(items, nearby=("پردیس", "رودهن")):
    queries = [
        {"queryKey": ["doctors", "list", "plp", {"specialitySlug": "gastroenterologist"}], "state": {"data": {"data": items, "pagination": {"total": len(items)}}}},
        {"queryKey": ["doctors", "nearbyNeighborhood", "tehran", True, "gastroenterologist"],
         "state": {"data": {"nearbyCities": [{"name": n} for n in nearby], "nearbyNeighborhoods": [{"name": "شهرک غرب"}]}}},
        {"queryKey": ["faq", "doctors"], "state": {"data": []}},
    ]
    return _page({"props": {"pageProps": {"dehydratedState": {"queries": queries}}}})


# --- parsing the live shapes -----------------------------------------------------------------------------------------------------------------------
def test_paziresh24_listing_becomes_normalised_providers():
    out = sr.parse_paziresh24(_p24_page([_p24_item("علی علوی", 155, 4.0, 80), _p24_item("سارا رضایی", 976, 4.8, 96, lat=None, lon=None)]))
    assert [p.name for p in out] == ["دکتر علی علوی", "دکتر سارا رضایی"]
    a, b = out
    assert (a.site, a.specialty, a.city, a.rating, a.rating_count, a.satisfaction_percent) == ("paziresh24.com", "متخصص گوارش", "تهران", 4.0, 155, 80)
    assert a.url == "https://www.paziresh24.com/dr/علی-علوی/" and a.address == "خیابان ولیعصر" and (a.lat, a.lon) == (35.7, 51.4) and a.visits == 1200
    assert (b.lat, b.lon) == (None, None) and b.rating == 4.8                                                   # a missing map is not an error


def test_a_paziresh24_provider_without_reviews_has_no_rating_not_a_fake_one():
    out = sr.parse_paziresh24(_p24_page([_p24_item("بدون نظر", 0, None, None)]))
    assert out[0].rating is None and out[0].rating_count == 0 and out[0].satisfaction_percent is None


def test_non_doctor_records_and_junk_are_ignored():
    items = [_p24_item("الف", 10, 4.0, 80), {"type": "center", "record_type": "center", "display_name": "کلینیک"}, "junk", _p24_item("", 3, 4.0, 80)]
    assert [p.name for p in sr.parse_paziresh24(_p24_page(items))] == ["دکتر الف"]
    assert sr.parse_paziresh24(b"<html>no data</html>") == [] and sr.parse_paziresh24(b"") == []
    assert sr.parse_paziresh24(b'<script id="__NEXT_DATA__">{broken') == []


def test_doctoreto_listing_gives_providers_and_the_sites_own_nearby_places():
    providers, nearby = sr.parse_doctoreto(_doctoreto_page([_doctoreto_item("دکتر الف", 200, 4.6, 92), _doctoreto_item("دکتر ب", 0, None, None)]))
    a, b = providers
    assert (a.site, a.rating, a.rating_count, a.satisfaction_percent, a.city, a.next_free) == ("doctoreto.com", 4.6, 200, 92, "تهران", "فردا ساعت ۱۰")
    assert a.url == "https://doctoreto.com/doctor/دکتر-الف/AbC" and (a.lat, a.lon) == (35.72, 51.40)
    assert b.rating is None and b.satisfaction_percent is None                                                  # no reviews: no rating
    assert nearby == ["پردیس", "رودهن", "شهرک غرب"]                                                              # real geography from the site itself
    assert sr.parse_doctoreto(b"<html></html>") == ([], [])


def test_coordinates_outside_iran_are_dropped():
    out = sr.parse_paziresh24(_p24_page([_p24_item("الف", 5, 4.0, 80, lat=10.0, lon=51.0)]))
    assert (out[0].lat, out[0].lon) == (None, None)


# --- the URLs (slugs verified against the live sites) ---------------------------------------------------------------------------------------------
def test_listing_urls_use_each_sites_own_slugs():
    urls = dict(sr.listing_urls("گوارش", "تهران"))
    assert urls == {"paziresh24.com": "https://www.paziresh24.com/s/tehran/gastroenterology/",
                    "doctoreto.com": "https://doctoreto.com/doctors/speciality/gastroenterologist/city/tehran"}
    assert dict(sr.listing_urls("پوست", "شیراز")) == {"paziresh24.com": "https://www.paziresh24.com/s/shiraz/dermatology/"}   # Doctoreto slug not verified: skipped
    assert sr.listing_urls("گوارش", "جای ناشناخته") == [] and sr.listing_urls("برچسب ناشناخته", "تهران") == [] and sr.listing_urls(None, "تهران") == []


# --- ranking: the patients' ratings, shrunk by how few reviews back them -----------------------------------------------------------------------
def _p(name, rating, count, lat=None, lon=None, city="تهران", site="paziresh24.com"):
    return sr.SiteProvider(site=site, name=name, city=city, rating=rating, rating_count=count, lat=lat, lon=lon)


def test_five_stars_from_two_reviews_do_not_beat_a_solid_record():
    ranked = sr.rank([_p("دو نظر", 5.0, 2), _p("سابقه دار", 4.7, 400), _p("بدون نظر", None, 0)])
    assert [p.name for p in ranked] == ["سابقه دار", "دو نظر", "بدون نظر"]
    assert sr.trust_score(_p("x", None, 0)) == sr.RATING_PRIOR                                                  # no reviews = the prior, never a perfect score


def test_closer_providers_lift_but_a_much_better_record_still_wins():
    here = (35.74, 51.87)                                                                                       # Boumehen
    near_ok = _p("نزدیک", 4.4, 300, lat=35.75, lon=51.88)
    near_weak = _p("نزدیک ضعیف", 3.8, 300, lat=35.75, lon=51.88)
    far_best = _p("دور", 4.9, 900, lat=35.70, lon=51.35)                                                         # ~47 km away
    far_poor = _p("دورضعیف", 4.0, 50, lat=35.70, lon=51.35)
    assert [p.name for p in sr.rank([far_best, near_ok], origin=here)] == ["نزدیک", "دور"]                        # a half-star edge does not cost a 47 km trip
    assert [p.name for p in sr.rank([far_best, near_weak], origin=here)] == ["دور", "نزدیک ضعیف"]                  # a >1-star edge does
    assert [p.name for p in sr.rank([far_poor, near_ok], origin=here)] == ["نزدیک", "دورضعیف"]
    assert [p.name for p in sr.rank([near_ok, far_best])] == ["دور", "نزدیک"]                                     # no origin: ratings alone


def test_the_same_doctor_on_two_sites_is_one_entry_with_the_larger_review_count():
    a = _p("دکتر الف", 4.5, 100, site="paziresh24.com")
    b = _p("دکتر الف", 4.6, 250, site="doctoreto.com")
    ranked = sr.rank([a, b, _p("دکتر ب", 4.0, 10)])
    assert [(p.name, p.site) for p in ranked] == [("دکتر الف", "doctoreto.com"), ("دکتر ب", "paziresh24.com")]


def test_pages_of_five_and_the_next_five_exclude_what_was_shown():
    many = [_p(f"دکتر {i:02d}", 4.5 - i * 0.01, 100) for i in range(12)]
    ranked = sr.rank(many)
    first = sr.page(ranked, 1)
    assert [p.name for p in first] == [f"دکتر {i:02d}" for i in range(5)] and sr.PAGE_SIZE == 5
    second_by_page = sr.page(ranked, 2)
    second_by_exclusion = sr.page(sr.rank(many, exclude=[p.key for p in first]), 1)                              # the stateless «next five» flow
    assert [p.name for p in second_by_page] == [p.name for p in second_by_exclusion] == [f"دکتر {i:02d}" for i in range(5, 10)]
    assert len(sr.page(ranked, 3)) == 2 and sr.page(ranked, 4) == [] and sr.page(ranked, 0)[0].name == "دکتر 00"


# --- reading (parallel, fail-open, cached) -------------------------------------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    sr._cache.clear()
    monkeypatch.setattr(sr, "MIN_GAP_SECONDS", 0.0)  # no real waiting in tests (the pacing test sets its own gap)
    yield
    sr._cache.clear()


def _fetcher(pages):
    calls = []

    def fetch(url):
        calls.append(url)
        value = pages.get(url)
        if isinstance(value, BaseException):
            raise value
        if value is None:
            return SimpleNamespace(ok=False, reason="http_404", body=b"")
        return SimpleNamespace(ok=True, reason="", body=value)

    fetch.calls = calls
    return fetch


def test_both_sites_are_read_and_a_blocked_one_is_reported_not_fatal():
    urls = dict(sr.listing_urls("گوارش", "تهران"))
    fetch = _fetcher({urls["paziresh24.com"]: _p24_page([_p24_item("الف", 100, 4.5, 90)]), urls["doctoreto.com"]: SimpleNamespace}.copy())
    # the second entry is not bytes: treat as a raising fetcher instead
    fetch = _fetcher({urls["paziresh24.com"]: _p24_page([_p24_item("الف", 100, 4.5, 90)]), urls["doctoreto.com"]: RuntimeError("down")})
    report = sr.read_sites("گوارش", "تهران", fetch=fetch)
    assert [p.name for p in report.providers] == ["دکتر الف"]
    assert report.sites["paziresh24.com"]["ok"] and report.sites["paziresh24.com"]["count"] == 1
    assert report.sites["doctoreto.com"] == {"ok": False, "reason": "RuntimeError", "count": 0, "seconds": report.sites["doctoreto.com"]["seconds"]}


def test_robots_or_http_failures_are_reasons_not_exceptions():
    report = sr.read_sites("گوارش", "تهران", fetch=_fetcher({}))
    assert report.providers == [] and {s["reason"] for s in report.sites.values()} == {"http_404"}


def test_a_listing_is_read_once_within_the_cache_window():
    urls = dict(sr.listing_urls("پوست", "شیراز"))
    fetch = _fetcher({urls["paziresh24.com"]: _p24_page([_p24_item("الف", 10, 4.0, 80)])})
    first = sr.read_sites("پوست", "شیراز", fetch=fetch)
    second = sr.read_sites("پوست", "شیراز", fetch=fetch)
    assert len(fetch.calls) == 1 and second.sites["paziresh24.com"]["reason"] == "cache" and len(second.providers) == len(first.providers) == 1


def test_an_unknown_specialty_or_city_reads_nothing():
    fetch = _fetcher({})
    report = sr.read_sites("برچسب ناشناخته", "تهران", fetch=fetch)
    assert report.providers == [] and report.sites == {} and fetch.calls == []


def test_the_reader_uses_the_safe_fetcher_by_default():
    import inspect

    assert "safe_fetch.fetch_page" in inspect.getsource(sr.read_sites)                                           # public https only, robots honoured, size/time capped


def test_an_empty_page_is_not_cached_so_the_next_read_retries():
    urls = dict(sr.listing_urls("پوست", "شیراز"))
    fetch = _fetcher({urls["paziresh24.com"]: _p24_page([])})                                                    # 200 but no listing: challenge/temporary page
    sr.read_sites("پوست", "شیراز", fetch=fetch)
    sr.read_sites("پوست", "شیراز", fetch=fetch)
    assert len(fetch.calls) == 2 and not sr._cache


# --- wiring into the chat (R-114 / R-116: five per introduction, flag-gated, fail-open, paced) ----------------------------------------------------
def _shiraz_fetch(count=8, bad=False):
    urls = dict(sr.listing_urls("پوست", "شیراز"))
    items = [_p24_item(f"{i:02d}", 50 + i, 4.0 + i / 20, 80, expertise="متخصص پوست", address=("خیابان معالی‌آباد" if i == 7 else "خیابان زند"), city="شیراز") for i in range(count)]
    return _fetcher({urls["paziresh24.com"]: (RuntimeError("down") if bad else _p24_page(items))})


def test_provider_rows_are_five_chat_rows_with_the_sites_own_rating_and_link():
    rows = sr.provider_rows("پوست", "شیراز", fetch=_shiraz_fetch())
    assert len(rows) == 5 and all(r["trusted"] and r["source_url"].startswith("https://www.paziresh24.com/") for r in rows)
    assert all(r["rating_avg"] and r["rating_count"] and r["phone"] is None and r["checked_on"] for r in rows)
    assert rows[0]["rating_avg"] >= rows[-1]["rating_avg"]                                                        # most credible first
    assert [r["name"] for r in sr.provider_rows("پوست", "شیراز", number=2, fetch=_shiraz_fetch())] == ["دکتر 02", "دکتر 01", "دکتر 00"]  # the next five


def test_the_neighbourhood_the_user_named_comes_first():
    rows = sr.provider_rows("پوست", "شیراز", area="معالی آباد", fetch=_shiraz_fetch())
    assert rows[0]["name"] == "دکتر 07" and len(rows) == 5                                                       # half-space / space tolerant; the rest keep their order


def test_provider_rows_fail_open_and_an_unmapped_place_reads_nothing():
    assert sr.provider_rows("پوست", "شیراز", fetch=_shiraz_fetch(bad=True)) == []
    fetch = _shiraz_fetch()
    assert sr.provider_rows("پوست", "رودهن", fetch=fetch) == [] and fetch.calls == []                            # no slug for the city: no request at all


def test_live_requests_are_paced_and_cache_hits_never_wait(monkeypatch):
    monkeypatch.setattr(sr, "MIN_GAP_SECONDS", 1.5)
    sr._last_live_fetch[0] = 0.0
    waits = []
    monkeypatch.setattr(sr.time, "sleep", lambda s: waits.append(s))
    fetch = _shiraz_fetch()
    sr.provider_rows("پوست", "شیراز", fetch=fetch)
    sr.provider_rows("پوست", "شیراز", fetch=fetch)                                                               # cached: no second live request
    sr._last_live_fetch[0] = sr.time.time()
    sr._cache.clear()
    sr.provider_rows("پوست", "شیراز", fetch=fetch)                                                               # live again right after the last one: waits
    assert len(fetch.calls) == 2 and len(waits) == 1 and 0 < waits[0] <= 1.5


def _nav(monkeypatch, fetch, flag="1"):
    from backend.app.services.i5 import care_navigation_directory as cn

    monkeypatch.setenv(sr.ENABLED_ENV, flag)
    monkeypatch.setattr(cn._web_lookup, "web_lookup_enabled", lambda: False)
    monkeypatch.setattr(cn, "_dispatch_governed_search", lambda db, request: [])
    monkeypatch.setattr(sr.safe_fetch, "fetch_page", fetch)
    request = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALIST, specialty_or_service="پوست", city="شیراز", province="فارس", language="fa")
    return cn, cn.query_governed_directory(None, request)


def test_the_chat_introduces_five_doctors_from_the_booking_site_when_the_flag_is_on(monkeypatch):
    cn, result = _nav(monkeypatch, _shiraz_fetch())
    assert result.status == cn.STATUS_VERIFIED and len(result.identities) == 5 and "SITE_READERS" in result.identity_notes
    assert all(i.source_url.startswith("https://www.paziresh24.com/") and i.web_trusted and i.rating_avg for i in result.identities)
    assert result.identities[0].canonical_name in result.user_message


def test_the_flag_off_or_a_down_site_leaves_the_older_answer_untouched(monkeypatch):
    cn, off = _nav(monkeypatch, _shiraz_fetch(), flag="0")
    assert off.status == cn.STATUS_NO_VERIFIED and "SITE_READERS" not in off.identity_notes
    cn, down = _nav(monkeypatch, _shiraz_fetch(bad=True))
    assert down.status == cn.STATUS_NO_VERIFIED


def test_a_doctor_of_another_specialty_never_takes_one_of_the_five_places(monkeypatch):
    urls = dict(sr.listing_urls("پوست", "شیراز"))
    items = [_p24_item("الف", 500, 4.9, 90, expertise="متخصص گوارش", city="شیراز"), _p24_item("ب", 400, 4.8, 90, expertise="متخصص پوست", city="شیراز"),
             _p24_item("ج", 300, 4.7, 90, expertise="دکترای حرفه‌ای پزشکی", city="شیراز")]                          # a gastroenterologist, a dermatologist, a degree only
    rows = sr.provider_rows("پوست", "شیراز", fetch=_fetcher({urls["paziresh24.com"]: _p24_page(items)}))
    assert [r["name"] for r in rows] == ["دکتر ب"]                                                                  # the gastro doctor AND the degree-only entry are out (accuracy)


def test_when_every_listed_doctor_is_another_specialty_the_chat_falls_back_to_the_older_path(monkeypatch):
    urls = dict(sr.listing_urls("پوست", "شیراز"))
    items = [_p24_item(f"{i:02d}", 50 + i, 4.5, 80, expertise="متخصص گوارش", city="شیراز") for i in range(6)]
    assert sr.provider_rows("پوست", "شیراز", fetch=_fetcher({urls["paziresh24.com"]: _p24_page(items)})) == []


def test_a_doctor_whose_clinic_is_in_another_city_never_takes_one_of_the_five_places():
    urls = dict(sr.listing_urls("پوست", "شیراز"))
    items = [_p24_item("الف", 500, 4.9, 90, expertise="متخصص پوست", city="تهران"), _p24_item("ب", 400, 4.8, 90, expertise="متخصص پوست", city="شیراز"),
             _p24_item("ج", 300, 4.7, 90, expertise="متخصص پوست", city="")]                                         # another city, the asked city, no city text
    rows = sr.provider_rows("پوست", "شیراز", fetch=_fetcher({urls["paziresh24.com"]: _p24_page(items)}))
    assert [r["name"] for r in rows] == ["دکتر ب", "دکتر ج"]
    only_other = _fetcher({urls["paziresh24.com"]: _p24_page(items[:1])})
    sr._cache.clear()
    assert sr.provider_rows("پوست", "شیراز", fetch=only_other) == []                                              # nothing left: the older path answers


def test_a_request_for_a_doctor_by_name_does_not_use_the_top_five(monkeypatch):
    from backend.app.services.i5 import care_navigation_directory as cn

    monkeypatch.setenv(sr.ENABLED_ENV, "1")
    monkeypatch.setattr(sr.safe_fetch, "fetch_page", _shiraz_fetch())
    request = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALIST, specialty_or_service="پوست", city="شیراز", province="فارس", language="fa", name_hint="احمدی")
    assert cn._reader_identities(request) == ()


def test_work_whose_caller_gave_up_never_starts_a_live_request(monkeypatch):
    monkeypatch.setattr(sr, "MIN_GAP_SECONDS", 1.5)
    sr._last_live_fetch[0] = sr.time.time()                                                                      # a live request just happened
    fetch = _shiraz_fetch()
    out = sr._read_one("paziresh24.com", "https://www.paziresh24.com/s/shiraz/dermatology/", fetch, deadline=sr.time.time() + 0.5)
    assert out[3]["ok"] is False and out[3]["reason"] == "deadline" and fetch.calls == []                      # waiting 1.5 s would pass the 0.5 s deadline
    monkeypatch.setattr(sr, "MIN_GAP_SECONDS", 0.0)
    out = sr._read_one("paziresh24.com", "https://www.paziresh24.com/s/shiraz/dermatology/", fetch, deadline=sr.time.time() + 5)
    assert out[3]["ok"] is True and len(fetch.calls) == 1                                                       # with time left it reads as before

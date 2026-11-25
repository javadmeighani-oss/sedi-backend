"""R-116 / R-119 (Javad 2026-11-25): (1) every doctor shown has had HIS PROFILE PAGE checked (opens, carries the listed name) and the result is kept 24 h
(option C: slow only the first time); (2) more than the first listing page is read when too few qualified doctors are found (Karaj gynaecology: page 1 =
0 gynaecologists, pages 2-3 = 17); (3) physiotherapists come from Doctoreto's own list. Pages are synthetic but shaped like the live ones."""
import json
from types import SimpleNamespace

import pytest

from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import site_readers as sr


def _page(next_data: dict) -> bytes:
    return ("<html><head><title>x</title></head><body><script id=\"__NEXT_DATA__\" type=\"application/json\">" + json.dumps(next_data, ensure_ascii=False) + "</script></body></html>").encode("utf-8")


def _p24(items):
    return _page({"props": {"pageProps": {"dehydratedState": {"queries": [{"queryKey": ["search"], "state": {"data": {"search": {"result": items, "total": len(items)}}}}]}}}})


def _item(i, expertise="متخصص زنان و زایمان", city="کرج", name=None):
    name = name or f"پزشک {i:02d}"
    return {"type": "doctor", "record_type": "doctor", "prefix": "دکتر", "display_name": name, "display_expertise": expertise, "satisfaction": 80,
            "rates_count": 100 + i, "star": 4.0 + i / 100, "number_of_visits": 900, "waiting_time": "۱۰ دقیقه", "url": f"/dr/doc-{i:03d}/",
            "centers": [{"address": f"{city}، خیابان {i}", "city_name": city, "map": {"lat": 35.8, "lon": 51.0}}]}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    sr._cache.clear()
    sr._verified.clear()
    monkeypatch.setattr(sr, "MIN_GAP_SECONDS", 0.0)
    monkeypatch.delenv(sr.VERIFY_ENV, raising=False)  # the check is ON by default
    yield
    sr._cache.clear()
    sr._verified.clear()


class _Site:
    """A fake site: listing pages by URL, profile pages by URL (a missing profile = 404), a call log."""

    def __init__(self, listings, profiles=None, profile_default="ok"):
        self.listings, self.profiles, self.profile_default, self.calls = listings, profiles or {}, profile_default, []

    def __call__(self, url):
        self.calls.append(url)
        if url in self.listings:
            return SimpleNamespace(ok=True, reason="", body=self.listings[url])
        if "/dr/" in url or "/doctor/" in url:
            kind = self.profiles.get(url, self.profile_default)
            if kind == "ok":
                n = int(url.rstrip("/").rsplit("-", 1)[-1]) if "/dr/doc-" in url else 0
                return SimpleNamespace(ok=True, reason="", body=_profile_page(f"دکتر پزشک {n:02d}"))
            if kind == "404":
                return SimpleNamespace(ok=False, reason="http_404", body=b"")
            if kind == "blocked":
                return SimpleNamespace(ok=False, reason="http_429", body=b"")
        return SimpleNamespace(ok=False, reason="http_404", body=b"")


def _profile_page(name):
    return ("<html><head><title>" + name + " | پذیرش24</title></head><body><h1>" + name + "</h1></body></html>").encode("utf-8")


# --- (1) the profile check ----------------------------------------------------------------------------------------------------------------------
def test_a_shown_doctor_whose_page_is_gone_is_replaced_by_the_next_candidate():
    urls = dict(sr.listing_urls("زنان", "کرج"))
    items = [_item(i) for i in range(1, 10)]
    top_url = "https://www.paziresh24.com/dr/doc-009/"
    site = _Site({urls["paziresh24.com"]: _p24(items)}, profiles={top_url: "404"})
    rows = sr.provider_rows("زنان", "کرج", fetch=site)
    assert len(rows) == 5 and all(r["source_url"] != top_url for r in rows)                                    # the dead page never reaches the user
    assert rows[0]["name"] == "پزشک 08" or rows[0]["name"].endswith("08")                                     # the next most credible took its place


def test_a_page_that_does_not_carry_the_listed_name_is_not_introduced():
    urls = dict(sr.listing_urls("زنان", "کرج"))
    items = [_item(i) for i in range(1, 8)]

    class Mixed(_Site):
        def __call__(self, url):
            if url.endswith("/doc-007/"):
                self.calls.append(url)
                return SimpleNamespace(ok=True, reason="", body=_profile_page("یک پزشک کاملا دیگر"))           # the page shows ANOTHER person
            if "/dr/doc-" in url:
                self.calls.append(url)
                n = int(url.rstrip("/").rsplit("-", 1)[-1])
                return SimpleNamespace(ok=True, reason="", body=_profile_page(f"دکتر پزشک {n:02d}"))
            return super().__call__(url)

    rows = sr.provider_rows("زنان", "کرج", fetch=Mixed({urls["paziresh24.com"]: _p24(items)}))
    assert "https://www.paziresh24.com/dr/doc-007/" not in [r["source_url"] for r in rows] and all(r["link_checked"] for r in rows)


def test_a_blocked_or_slow_site_never_makes_the_answer_worse_the_doctor_is_shown_unchecked():
    urls = dict(sr.listing_urls("زنان", "کرج"))
    items = [_item(i) for i in range(1, 8)]
    rows = sr.provider_rows("زنان", "کرج", fetch=_Site({urls["paziresh24.com"]: _p24(items)}, profile_default="blocked"))
    assert len(rows) == 5 and not any(r["link_checked"] for r in rows)                                          # 429 = unknown, not bad
    assert not sr._verified                                                                                    # unknown results are never cached


def test_the_check_result_is_kept_for_a_day_so_only_the_first_request_is_slow():
    urls = dict(sr.listing_urls("زنان", "کرج"))
    site = _Site({urls["paziresh24.com"]: _p24([_item(i) for i in range(1, 9)])})
    sr.provider_rows("زنان", "کرج", fetch=site)
    profile_calls = [u for u in site.calls if "/dr/doc-" in u]
    sr._cache.clear()                                                                                          # the listing cache expired, the profile cache did not
    site.calls.clear()
    again = sr.provider_rows("زنان", "کرج", fetch=site)
    assert len(profile_calls) >= 5 and not [u for u in site.calls if "/dr/doc-" in u] and all(r["link_checked"] for r in again)
    for key in list(sr._verified):                                                                              # a day later the pages are checked again
        sr._verified[key] = (sr._verified[key][0] - sr.VERIFY_TTL_SECONDS - 1, sr._verified[key][1])
    site.calls.clear()
    sr._cache.clear()
    sr.provider_rows("زنان", "کرج", fetch=site)
    assert [u for u in site.calls if "/dr/doc-" in u]


def test_the_check_can_be_switched_off_and_never_blocks_beyond_its_budget(monkeypatch):
    urls = dict(sr.listing_urls("زنان", "کرج"))
    site = _Site({urls["paziresh24.com"]: _p24([_item(i) for i in range(1, 9)])})
    monkeypatch.setenv(sr.VERIFY_ENV, "false")
    rows = sr.provider_rows("زنان", "کرج", fetch=site)
    assert len(rows) == 5 and not [u for u in site.calls if "/dr/doc-" in u]
    monkeypatch.delenv(sr.VERIFY_ENV)
    monkeypatch.setattr(sr, "VERIFY_BUDGET_SECONDS", -1.0)                                                      # no time at all: everything is shown unchecked
    sr._cache.clear()
    site.calls.clear()
    rows = sr.provider_rows("زنان", "کرج", fetch=site)
    assert len(rows) == 5 and not [u for u in site.calls if "/dr/doc-" in u] and not any(r["link_checked"] for r in rows)


# --- (2) more than the first listing page --------------------------------------------------------------------------------------------------------
def test_more_pages_are_read_when_the_first_has_too_few_qualified_doctors():
    first = [_item(i, expertise="کارشناس مامایی") for i in range(1, 21)]                                      # page 1: all midwives (Karaj)
    second = [_item(i, expertise="کارشناس مامایی") for i in range(21, 31)] + [_item(i) for i in range(31, 41)]  # page 2: ten gynaecologists
    third = [_item(i) for i in range(41, 51)]
    base = dict(sr.listing_urls("زنان", "کرج"))["paziresh24.com"]
    site = _Site({base: _p24(first), base + "?page=2": _p24(second), base + "?page=3": _p24(third)})
    rows = sr.provider_rows("زنان", "کرج", fetch=site)
    assert len(rows) == 5 and all("زنان" in r["specialty"] for r in rows)
    assert [u for u in site.calls if "?page=" in u] == [base + "?page=2"]                                      # page 3 not needed: enough qualified already


def test_reading_stops_at_the_page_limit_and_a_missing_page_ends_it():
    base = dict(sr.listing_urls("زنان", "کرج"))["paziresh24.com"]
    only_midwives = {base: _p24([_item(i, expertise="کارشناس مامایی") for i in range(1, 21)]),
                     base + "?page=2": _p24([_item(i, expertise="کارشناس مامایی") for i in range(21, 41)])}                # page 3 does not exist
    site = _Site(only_midwives)
    assert sr.provider_rows("زنان", "کرج", fetch=site) == []                                                    # nothing qualified: the older paths answer
    assert len([u for u in site.calls if "?page=" in u or u == base]) == 3                                        # pages 1, 2 and the failed 3 - never more than MAX_PAGES


def test_the_next_five_reads_deeper_when_the_first_pages_are_exhausted():
    base = dict(sr.listing_urls("زنان", "کرج"))["paziresh24.com"]
    pages = {base: _p24([_item(i) for i in range(1, 11)]), base + "?page=2": _p24([_item(i) for i in range(11, 21)])}
    site = _Site(pages)
    first = sr.provider_rows("زنان", "کرج", fetch=site)
    again = sr.provider_rows("زنان", "کرج", exclude=[r["_key"] for r in first], fetch=site)
    assert len(first) == 5 and len(again) == 5 and not {r["name"] for r in first} & {r["name"] for r in again}


# --- (3) physiotherapy from Doctoreto -----------------------------------------------------------------------------------------------------------
def _doctoreto(items):
    queries = [{"queryKey": ["doctors", "list", "plp", {"specialitySlug": "physiotherapist"}], "state": {"data": {"data": items, "pagination": {"total": len(items)}}}}]
    return _page({"props": {"pageProps": {"dehydratedState": {"queries": queries}}}})


def _physio(i, city="تهران"):
    return {"fullName": f"فیزیوتراپ {i:02d}", "profileRoute": f"/doctor/physio-{i:02d}/AbC", "specialityLabel": "تخصص فیزیوتراپی",
            "places": [{"address": f"{city}، خیابان {i}", "city": {"name": city, "slug": "tehran"}, "coordinates": {"latitude": 35.7, "longitude": 51.4}}],
            "rate": {"count": 50 + i, "rateAverage": 4.5, "percent": 90, "recommend": 90}, "nextFreeTimes": {"general": {"fullTextDisplay": "فردا ساعت ۱۰"}}}


def test_physiotherapy_has_a_doctoreto_listing_for_the_cities_where_it_exists():
    urls = sr.listing_urls("فیزیوتراپی", "تهران")
    assert urls == [("doctoreto.com", "https://doctoreto.com/doctors/speciality/physiotherapist/city/tehran")]
    assert sr.listing_urls("فیزیوتراپی", "تهران", page=2)[0][1].endswith("/city/tehran?page=2")
    site = _Site({urls[0][1]: _doctoreto([_physio(i) for i in range(1, 9)])}, profile_default="blocked")
    rows = sr.provider_rows("فیزیوتراپی", "تهران", fetch=site)
    assert len(rows) == 5 and all(r["source_url"].startswith("https://doctoreto.com/doctor/") and "فیزیوتراپی" in r["specialty"] for r in rows)


def test_the_chat_answers_a_physiotherapy_request_from_the_readers_with_people_not_hospitals(monkeypatch):
    urls = sr.listing_urls("فیزیوتراپی", "تهران")
    site = _Site({urls[0][1]: _doctoreto([_physio(i) for i in range(1, 9)])}, profile_default="blocked")
    monkeypatch.setenv(sr.ENABLED_ENV, "1")
    monkeypatch.setattr(sr.safe_fetch, "fetch_page", site)
    monkeypatch.setattr(cn._web_lookup, "web_lookup_enabled", lambda: False)
    monkeypatch.setattr(cn, "_dispatch_governed_search", lambda db, request: [])
    req = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALTY_CENTER, specialty_or_service="فیزیوتراپی", city="تهران", province="تهران", language="fa")
    out = cn.query_governed_directory(None, req)
    assert "SITE_READERS" in out.identity_notes and len(out.identities) == 5
    assert all(i.entity_type == "DOCTOR" and i.source_url.startswith("https://doctoreto.com/doctor/") for i in out.identities)
    assert out.intro_state and out.intro_state["entity"] == "SPECIALTY_CENTER" and len(out.intro_state["keys"]) == 5                       # the next five works for it too


# --- Codex round 1 on PR 226 ----------------------------------------------------------------------------------------------------------------------
def test_p2_a_profile_known_to_be_bad_stays_out_even_when_the_budget_is_spent(monkeypatch):
    urls = dict(sr.listing_urls("زنان", "کرج"))
    items = [_item(i) for i in range(1, 10)]
    dead = "https://www.paziresh24.com/dr/doc-009/"
    site = _Site({urls["paziresh24.com"]: _p24(items)}, profiles={dead: "404"})
    first = sr.provider_rows("زنان", "کرج", fetch=site)
    assert dead not in [r["source_url"] for r in first]
    sr._cache.clear()
    monkeypatch.setattr(sr, "VERIFY_BUDGET_SECONDS", -1.0)                                                      # no time left: only the cache can answer
    second = sr.provider_rows("زنان", "کرج", fetch=site)
    assert dead not in [r["source_url"] for r in second] and len(second) == 5                                   # the cached «bad» still removes it


def test_p2_a_slow_page_cannot_extend_the_request_beyond_the_verification_budget(monkeypatch):
    import threading
    import time as _time

    urls = dict(sr.listing_urls("زنان", "کرج"))
    items = [_item(i) for i in range(1, 10)]
    release = threading.Event()

    class Slow(_Site):
        def __call__(self, url):
            if "/dr/doc-" in url:
                release.wait(3.0)                                                                              # the page reader hangs (its own timeout is 8 s)
                return SimpleNamespace(ok=True, reason="", body=_profile_page("x"))
            return super().__call__(url)

    monkeypatch.setattr(sr, "VERIFY_BUDGET_SECONDS", 0.4)
    started = _time.time()
    rows = sr.provider_rows("زنان", "کرج", fetch=Slow({urls["paziresh24.com"]: _p24(items)}))
    elapsed = _time.time() - started
    release.set()
    assert len(rows) == 5 and not any(r["link_checked"] for r in rows)                                          # shown unchecked, nothing dropped
    assert elapsed < 1.5                                                                                       # bounded by the budget, not by 5 x the reader's timeout


# --- Codex round 2 on PR 226 ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("listed,owner,same", [
    ("دکتر علی احمدی", "علی احمدی", True), ("علی احمدی", "دکتر علی احمدی", True), ("علی احمدی", "علی رضا احمدی", True),            # a prefix / one more component
    ("علی احمدی", "علیرضا احمدیان", False),                                                                         # substrings are not the same person
    ("علی احمدی", "احمدی", False), ("علی احمدی", "رضا احمدی", False), ("دکتر نسرین عطایی هاشم پور", "نسرین عطایی هاشم پور", True),
    ("محمدحسین فرودی جهرمی", "محمد‌حسین فرودی‌ جهرمی", True),                                                     # half-spaces do not matter
    ("", "علی", False),
])
def test_p2_the_page_owner_must_be_the_listed_person_component_by_component(listed, owner, same):
    assert sr._same_person(listed, owner) is same


def test_p2_a_challenge_or_empty_shell_is_unknown_not_bad_and_never_cached():
    urls = dict(sr.listing_urls("زنان", "کرج"))
    items = [_item(i) for i in range(1, 8)]

    class Shell(_Site):
        def __call__(self, url):
            if "/dr/doc-" in url:
                self.calls.append(url)
                return SimpleNamespace(ok=True, reason="", body=b"<html><body>Just a moment... verify you are human</body></html>")
            return super().__call__(url)

    rows = sr.provider_rows("زنان", "کرج", fetch=Shell({urls["paziresh24.com"]: _p24(items)}))
    assert len(rows) == 5 and not any(r["link_checked"] for r in rows) and not sr._verified                    # shown, unchecked, nothing cached


def test_p2_a_page_naming_a_similar_but_different_person_is_rejected():
    urls = dict(sr.listing_urls("زنان", "کرج"))
    items = [_item(i, name="علی احمدی") if i == 7 else _item(i) for i in range(1, 8)]

    class Similar(_Site):
        def __call__(self, url):
            if "/dr/doc-" in url:
                self.calls.append(url)
                n = int(url.rstrip("/").rsplit("-", 1)[-1])
                owner = "دکتر علیرضا احمدیان" if n == 7 else f"دکتر پزشک {n:02d}"
                return SimpleNamespace(ok=True, reason="", body=("<html><title>x</title><h1>" + owner + "</h1><p>علی احمدی در لیست دیگر</p></html>").encode("utf-8"))
            return super().__call__(url)

    rows = sr.provider_rows("زنان", "کرج", fetch=Similar({urls["paziresh24.com"]: _p24(items)}))
    assert "https://www.paziresh24.com/dr/doc-007/" not in [r["source_url"] for r in rows]


def test_the_doctoreto_name_block_is_read_piece_by_piece():
    html = ('<html><h1><span>نوبت اینترنتی </span><div><div>امین میرزابیگی</div></div><div>کارشناسی فیزیوتراپی</div>'
            '<svg><path d="M2.5"></path></svg><span>تهران</span></h1></html>')
    pieces = sr._page_owner(html)
    assert "امین میرزابیگی" in pieces and any(sr._same_person("دکتر امین میرزابیگی", x) for x in pieces)
    assert not any(sr._same_person("امین میرزایی", x) for x in pieces)                                          # a different person is not matched by a piece
    assert sr._page_owner("<html>no heading</html>") == []


# --- Codex round 3 on PR 226 ----------------------------------------------------------------------------------------------------------------------
def test_p2_the_verdict_belongs_to_the_listed_name_not_only_to_the_url():
    urls = dict(sr.listing_urls("زنان", "کرج"))
    one, two = _item(1, name="علی احمدی"), _item(2, name="رضا حسینی")
    one["url"] = two["url"] = "/dr/shared-page/"                                                               # two listings point at the SAME page
    one["star"], one["rates_count"], two["star"], two["rates_count"] = 5.0, 900, 4.99, 899                         # both rank at the top

    class Shared(_Site):
        def __call__(self, url):
            if url.endswith("/dr/shared-page/"):
                self.calls.append(url)
                return SimpleNamespace(ok=True, reason="", body=_profile_page("دکتر علی احمدی"))
            return super().__call__(url)

    rows = sr.provider_rows("زنان", "کرج", fetch=Shared({urls["paziresh24.com"]: _p24([one, two] + [_item(i) for i in range(3, 9)])}))
    names = [r["name"] for r in rows]
    assert "دکتر علی احمدی" in names and "دکتر رضا حسینی" not in names                                                      # the page shows ONE person; the other listing is not verified by it

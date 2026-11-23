"""R-089 (D-381): finding a doctor / lab by neighbourhood never gives up.

Matrix: place spellings (joined / space / half-space / Arabic letters / English) x entity (doctor / lab) x language.
Offline: web search is faked, the governed directory search is stubbed. Nothing is written anywhere.
"""
import pytest

from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import directory_web_lookup as wl
from backend.app.services.i5 import iran_places as ip

ZW = "‌"
TEHRANPARS = "تهران" + ZW + "پارس"


@pytest.fixture(autouse=True)
def _reset():
    wl._cache.clear()
    wl._usage.clear()


@pytest.mark.parametrize(
    "text, city, area",
    [
        ("یه دکتر قلب خوب در تهرانپارس معرفی کن", "تهران", TEHRANPARS),
        ("دکتر در منطقه " + TEHRANPARS, "تهران", TEHRANPARS),
        ("آزمایشگاه نزدیک تهران پارس", "تهران", TEHRANPARS),
        ("يک دكتر در نارمك", "تهران", "نارمک"),  # Arabic Yeh / Kaf
        ("متخصص پوست در منطقه ۸", "تهران", "منطقه 8"),
        ("دکتر خوب در سعادت آباد", "تهران", "سعادت" + ZW + "آباد"),
        ("دندانپزشک در اصفهان", "اصفهان", None),
        ("a cardiologist in Tehranpars", "Tehran", TEHRANPARS),  # English request keeps English city
        ("heart doctor in Shiraz", "Shiraz", None),
        ("دکتر قلب در منطقه تهرانپارس، کسی را می‌شناسی؟", "تهران", TEHRANPARS),  # «،» right after the name (Codex P2)
        ("آزمایشگاه نارمک؟", "تهران", "نارمک"),
        ("طبيب في تهرانپارس", "تهران", TEHRANPARS),
        ("دکتر خوب معرفی کن", None, None),
    ],
)
def test_place_matrix(text, city, area):
    place = ip.find_place(text)
    assert (place.city, place.area) == (city, area)


def test_neighbourhood_word_is_never_taken_as_the_city():
    req = cn.parse_care_nav_request("یه دکتر قلب خوب در منطقه تهرانپارس معرفی کن", language="fa")
    assert req.city == "تهران" and req.area == TEHRANPARS
    req2 = cn.parse_care_nav_request("دکتر خوب در منطقه معرفی کن", language="fa")
    assert req2.city is None  # «منطقه» alone is not a city


def test_neighbourhood_counts_as_a_real_location_for_the_detector():
    assert cn._has_real_location("متخصص پوست تهرانپارس")
    assert cn.is_care_navigation_query("یه متخصص پوست خوب تهرانپارس معرفی کن")


def test_query_carries_the_neighbourhood():
    assert wl.build_query("SPECIALIST", "قلب", "تهران", None, area=TEHRANPARS) == "متخصص قلب در " + TEHRANPARS + ", تهران"
    assert wl.build_query("SPECIALIST", "قلب", "شیراز", "فارس") == "متخصص قلب در شیراز, فارس"  # unchanged without area


@pytest.mark.parametrize(
    "address, item_city",
    [
        ("تهرانپارس، خیابان فرجام", ""),  # neighbourhood only, joined spelling
        ("تهران، تهران پارس، فلکه دوم", "تهران"),
        ("تهران" + ZW + "پارس، بلوار تیرانداز", None),
    ],
)
def test_validation_accepts_neighbourhood_spellings(address, item_city):
    item = {"name": "دکتر ب", "specialty": "قلب", "city": item_city or "", "address": address,
            "phone": "021-77889900", "source_url": "https://www.paziresh24.com/dr/b/"}
    out = wl.validate_results([item], city="تهران", area=TEHRANPARS)
    assert len(out) == 1 and out[0]["trusted"]


def test_validation_still_drops_other_cities():
    item = {"name": "دکتر ج", "specialty": "قلب", "city": "شیراز", "address": "شیراز، خیابان زند",
            "phone": "071-32345678", "source_url": "https://www.paziresh24.com/dr/c/"}
    assert wl.validate_results([item], city="تهران", area=TEHRANPARS) == []


def test_web_search_sends_the_neighbourhood_and_tries_booking_sites_last(monkeypatch):
    monkeypatch.setenv(wl.FLAG, "true")
    calls = []

    def fake(query, country, client=None):
        calls.append(query)
        return []

    monkeypatch.setattr(wl, "_call_web_search", fake)
    wl.search_web_providers(entity="SPECIALIST", specialty="قلب", city="تهران", province=None, area=TEHRANPARS)
    assert calls and all(TEHRANPARS in q for q in calls)
    assert "پذیرش۲۴" in calls[1]  # R-114: the booking sites come second for a doctor


def _no_web(monkeypatch):
    monkeypatch.setenv(wl.FLAG, "false")
    monkeypatch.setattr(cn, "_dispatch_governed_search", lambda db, req: [])


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
@pytest.mark.parametrize("message", ["یه دکتر قلب خوب در تهرانپارس معرفی کن", "آزمایشگاه نزدیک تهرانپارس پیدا کن"])
def test_nothing_found_gives_links_and_one_question_never_cannot(monkeypatch, lang, message):
    _no_web(monkeypatch)
    req = cn.parse_care_nav_request(message, language=lang)
    res = cn.query_governed_directory(None, req)
    msg = res.user_message
    assert "https://www.paziresh24.com/s/tehran/?text=" in msg
    assert "https://doctoreto.com/search?q=" in msg
    assert msg.count("?") + msg.count("؟") >= 1
    for banned in ("نمی‌توانم", "نمیتونم", "cannot help", "can't help", "لا أستطيع"):
        assert banned not in msg
    if lang == "en":
        assert "verified" in msg  # never claims an unverified listing as verified


@pytest.mark.parametrize("lang, needle", [("fa", "کدام شهر"), ("ar", "أي مدينة"), ("en", "which city")])
def test_no_place_asks_one_question(monkeypatch, lang, needle):
    _no_web(monkeypatch)
    req = cn.parse_care_nav_request("یه متخصص قلب خوب معرفی کن", language=lang)
    res = cn.query_governed_directory(None, req)
    assert needle in res.user_message.lower() and "http" not in res.user_message


def test_city_without_verified_slug_uses_the_general_search_page(monkeypatch):
    _no_web(monkeypatch)
    req = cn.parse_care_nav_request("دکتر قلب در کرمانشاه معرفی کن", language="fa")
    msg = cn.query_governed_directory(None, req).user_message
    assert "https://www.paziresh24.com/s/?text=" in msg


def test_generic_fail_safe_never_says_cannot():
    for lang in ("fa", "ar", "en"):
        msg = cn.fail_safe_user_message(cn.CareNavEntity.SPECIALIST, lang)
        assert "نمی‌توانم" not in msg and "cannot" not in msg.lower()


def test_explicit_city_beats_the_tehran_guess():
    # a city outside the gazetteer + a Tehran-like neighbourhood word: the named city wins (Codex P2)
    req = cn.parse_care_nav_request("دکتر قلب در بروجرد نزدیک نارمک معرفی کن", language="fa")
    assert req.city == "بروجرد"
    # shared street names are not Tehran neighbourhoods at all
    assert ip.find_place("دکتر در خیابان شریعتی").area is None


def test_result_naming_another_city_is_rejected_even_with_the_same_district():
    item = {"name": "دکتر د", "specialty": "قلب", "city": "شیراز", "address": "شیراز، منطقه 8، خیابان زند",
            "phone": "071-32345678", "source_url": "https://www.paziresh24.com/dr/d/"}
    assert wl.validate_results([item], city="تهران", area="منطقه 8") == []


def test_english_and_persian_city_names_are_the_same_city():
    item = {"name": "دکتر ه", "specialty": "قلب", "city": "شیراز", "address": "شیراز، خیابان زند",
            "phone": "071-32345678", "source_url": "https://www.paziresh24.com/dr/e/"}
    assert len(wl.validate_results([item], city="Shiraz")) == 1
    assert ip.slug_for("Shiraz") == "shiraz" and ip.slug_for("تهران") == "tehran" and ip.slug_for("بروجرد") is None

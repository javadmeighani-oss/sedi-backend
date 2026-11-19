"""J3-a (D-405): one specialty lexicon (fa/en/ar), qualifiers, the pharmacy entity and the online-search query."""
import pytest

from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import directory_web_lookup as wl
from backend.app.services.i5 import specialty_lexicon as sl

CASES = [  # words -> canonical specialty
    ("نورولوژی", "مغز و اعصاب"), ("نورولوژیست", "مغز و اعصاب"), ("neurologist", "مغز و اعصاب"), ("طبيب أعصاب", "مغز و اعصاب"),
    ("کاردیولوژیست", "قلب"), ("cardiologist", "قلب"), ("heart doctor", "قلب"), ("طبيب قلب", "قلب"), ("متخصص قلب و عروق", "قلب"),
    ("دندانپزشک", "دندانپزشکی"), ("دندان‌پزشک", "دندانپزشکی"), ("dentist", "دندانپزشکی"), ("طبيب أسنان", "دندانپزشکی"),
    ("اورولوژی", "اورولوژی"), ("urologist", "اورولوژی"), ("کلیه و مجاری ادرار", "اورولوژی"), ("نفرولوژی", "کلیه"),
    ("pediatrician", "اطفال"), ("پزشک کودکان", "اطفال"), ("طبيب أطفال", "اطفال"),
    ("زنان و زایمان", "زنان"), ("gynecologist", "زنان"), ("طبيبة نسائية", "زنان"),
    ("dermatologist", "پوست"), ("متخصص پوست و مو", "پوست"), ("orthopedic", "ارتوپدی"), ("چشم‌پزشک", "چشم"), ("ENT", "گوش و حلق و بینی"),
    ("psychiatrist", "روانپزشکی"), ("psychologist", "روان‌شناسی"), ("endocrinologist", "غدد"), ("متخصص تغذیه", "تغذیه"),
    ("فیزیوتراپی", "فیزیوتراپی"), ("oncologist", "انکولوژی"), ("internist", "داخلی"),
]


@pytest.mark.parametrize("text, expected", CASES)
def test_every_wording_maps_to_one_canonical_specialty(text, expected):
    assert sl.find_specialty(f"یه {text} خوب لازم دارم") == expected or sl.find_specialty(text) == expected


@pytest.mark.parametrize("text", ["امروز هوا خوبه", "thanks a lot", "سلام", "", "تشکر می‌کنم از کمکت"])
def test_ordinary_words_name_no_specialty(text):
    assert sl.find_specialty(text) is None


def test_the_longest_wording_wins():
    assert sl.find_specialty("کلیه و مجاری ادرار") == "اورولوژی"  # not «کلیه»
    assert sl.find_specialty("گوش و حلق و بینی") == "گوش و حلق و بینی"


@pytest.mark.parametrize("text", ["کاردیولوژیست", "a pediatrician", "dentist", "طبيب أسنان"])
def test_a_practitioner_is_recognised_without_the_word_doctor(text):
    assert sl.has_practitioner_word(text)


def test_legacy_governed_stems_are_kept_for_old_rows():
    assert sl.governed_stem("دندانپزشکی") == "دندان" and sl.governed_stem("ارتوپدی") == "ارتوپد" and sl.governed_stem("روانپزشکی") == "روان"
    assert sl.governed_stem("ناشناخته") == "ناشناخته" and sl.governed_stem(None) is None


@pytest.mark.parametrize("text, expected", [
    ("یه داروخانه شبانه‌روزی نزدیک پاسداران", ("24h",)), ("a 24 hour pharmacy in Tehran", ("24h",)),
    ("یه پزشک زنان با رضایت بالا", ("high_rating",)), ("a highly rated dentist", ("high_rating",)),
    ("یه دکتر قلب", ()), ("a doctor", ())])
def test_qualifiers_are_read_from_the_users_words(text, expected):
    assert sl.qualifiers(text) == expected


@pytest.mark.parametrize("msg, lang", [
    ("یه داروخانه شبانه‌روزی نزدیک پاسداران پیدا کن", "fa"), ("find a pharmacy in Shiraz", "en"), ("أحتاج صيدلية في طهران", "ar")])
def test_a_pharmacy_request_is_a_care_navigation_request_with_its_own_entity(msg, lang):
    assert cn.is_care_navigation_query(msg)
    assert cn.parse_care_nav_request(msg, language=lang).entity is cn.CareNavEntity.PHARMACY


@pytest.mark.parametrize("msg", ["کاردیولوژیست خوب در کرج می‌خوام", "a pediatrician in Shiraz", "أحتاج طبيب قلب في طهران"])
def test_a_request_naming_a_practitioner_or_specialty_is_understood_as_a_find_request(msg):
    assert cn.is_care_navigation_query(msg)


@pytest.mark.parametrize("msg", ["قلبم برات می‌تپه", "my heart is broken", "پزشکی رشته‌ی سختیه"])
def test_ordinary_chat_is_not_a_find_request(msg):
    assert not cn.is_care_navigation_query(msg)


def test_the_online_query_carries_the_specialty_the_area_and_the_qualifiers():
    q = wl.build_query("PHARMACY", None, "تهران", None, "IR", area="پاسداران", qualifiers=("24h",))
    assert q == "داروخانه شبانه‌روزی پاسداران, تهران".replace(", ", ", ") or "داروخانه" in q and "شبانه‌روزی" in q and "پاسداران" in q
    q2 = wl.build_query("SPECIALIST", "زنان", "تهران", None, "IR", area="سعادت‌آباد", qualifiers=("high_rating",))
    assert "زنان" in q2 and "امتیاز بالا" in q2 and "سعادت" in q2
    assert wl.build_query("SPECIALIST", "قلب", "تهران", None, "IR") == "قلب پزشک تهران"  # unchanged when no qualifiers


def test_pharmacy_no_result_message_offers_a_map_search_not_booking_sites():
    req = cn.parse_care_nav_request("یه داروخانه شبانه‌روزی نزدیک پاسداران پیدا کن", language="fa")
    links = cn.directory_search_links(req)
    assert len(links) == 1 and "google.com/maps" in links[0][1] and "paziresh24" not in links[0][1]


def test_pharmacy_never_touches_the_governed_directory(monkeypatch):
    calls = []
    monkeypatch.setattr(cn._governed_directory, "search_doctors", lambda *a, **k: calls.append("doctors") or [])
    monkeypatch.setattr(cn, "_web_identities", lambda req: ())
    monkeypatch.setattr(cn._web_lookup, "web_lookup_enabled", lambda: False)
    req = cn.parse_care_nav_request("find a pharmacy in Shiraz", language="en")
    res = cn.query_governed_directory(None, req)
    assert calls == [] and res.status == cn.STATUS_NO_VERIFIED


# --- Codex review of PR 189 -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["یه دکتر زنان، در تهران معرفی کن", "دکتر زنان؟", "(زنان)", "«زنان»"])
def test_p2_arabic_script_punctuation_is_a_word_boundary(text):
    assert sl.find_specialty(text) == "زنان"


def test_p2_legacy_governed_rows_with_english_specialties_still_match(monkeypatch):
    seen = []

    def fake_search(db, *, name=None, city=None, province=None, specialty=None, include_inactive=False, limit=5):
        seen.append(specialty)
        return [{"canonical_directory_key": "k1"}] if specialty == "Neurology" else []

    monkeypatch.setattr(cn._governed_directory, "search_doctors", fake_search)
    req = cn.parse_care_nav_request("Find a neurologist in Tehran", language="en")
    assert req.specialty_or_service == "مغز و اعصاب"
    rows = cn._dispatch_governed_search(None, req)
    assert seen == ["اعصاب", "Neurology"] and len(rows) == 1


def test_p2_the_governed_search_deduplicates_and_respects_the_limit(monkeypatch):
    rows = [{"canonical_directory_key": f"k{i}"} for i in range(5)]
    monkeypatch.setattr(cn._governed_directory, "search_doctors", lambda db, **k: rows)
    req = cn.parse_care_nav_request("Find a cardiologist in Tehran", language="en")
    assert len(cn._dispatch_governed_search(None, req)) == 5


@pytest.mark.parametrize("msg", ["My psychiatrist changed my meds", "I do not need a therapist", "I don't want a pediatrician",
                                 "روانپزشکم دارویم را عوض کرد", "لا أحتاج طبيب أسنان"])
def test_p2_a_practitioner_mention_without_a_request_is_not_a_find_request(msg):
    assert not cn.is_care_navigation_query(msg)


@pytest.mark.parametrize("msg", ["I need a therapist in Tehran", "looking for a psychiatrist", "یه روانشناس می‌خوام", "find a dentist"])
def test_p2_a_real_request_for_a_practitioner_still_routes(msg):
    assert cn.is_care_navigation_query(msg)


@pytest.mark.parametrize("text, expected", [("Find an eye surgeon in Tehran", "چشم"), ("a heart surgeon", "قلب"), ("جراح مغز", "مغز و اعصاب"),
                                            ("a surgeon in Shiraz", "جراحی عمومی"), ("جراح عمومی", "جراحی عمومی")])
def test_p2_a_generic_surgeon_never_overrides_a_named_specialty(text, expected):
    assert sl.find_specialty(text) == expected


def test_p2_the_legacy_persian_neurology_alias_still_matches_old_rows():
    assert "اعصاب" in sl.governed_terms("مغز و اعصاب") and "Neurology" in sl.governed_terms("مغز و اعصاب")
    assert "اعصاب" in "مغز و اعصاب"  # the stem is a substring of both legacy spellings


@pytest.mark.parametrize("text, expected", [
    ("Find a dentist for my child with diabetes in Tehran", "دندانپزشکی"), ("a cardiologist for my mother with kidney problems", "قلب"),
    ("دندانپزشک برای بچه‌ام که دیابت دارد", "دندانپزشکی"), ("a doctor for diabetes", "غدد"), ("diabetes", "غدد")])
def test_p2_the_requested_practitioner_beats_condition_words(text, expected):
    assert sl.find_specialty(text) == expected


@pytest.mark.parametrize("msg", ["I don't want surgery, find a cardiologist in Tehran", "I do not need pills but find a dentist in Shiraz"])
def test_p2_declining_a_treatment_does_not_decline_the_provider_request(msg):
    assert cn.is_care_navigation_query(msg)


@pytest.mark.parametrize("msg", ["I do not need a therapist", "I don't want a doctor", "I don't need a dentist anymore"])
def test_p2_declining_a_provider_still_declines(msg):
    assert not cn.is_care_navigation_query(msg)


def test_p2_arabic_city_spellings_validate_web_results():
    items = [{"name": "عيادة الشفاء", "specialty": "قلب", "city": "طهران", "address": "طهران، شارع ولي عصر", "phone": "02112345678",
              "source_url": "https://www.paziresh24.com/dr/x"}]
    out = wl.validate_results(items, city="تهران", country="IR")
    assert len(out) == 1 and out[0]["name"] == "عيادة الشفاء"

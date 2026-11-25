"""R-116 am.1 (Javad 2026-11-25): «the NEXT FIVE» + accurate doctor links (name AND specialty in the link, profile page of the doctor).

Real session (in-memory SQLite harness of test_r108_care_loop_e2e): the doctor introduction stores what it covered with its turn; «پنج تای بعدی» /
«مناسب نیست» continues from it, never repeats a doctor, and says plainly when nothing is left. Pages are synthetic but shaped like Paziresh24's."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.app import models, sedi_copy
from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import provider_links as pl
from backend.app.services.i5 import provider_next as pn
from backend.app.services.i5 import site_readers as sr
from backend.app.services.i7 import governed_raw
from backend.tests.test_r108_care_loop_e2e import _fixed_timezone, db, user  # noqa: F401  (real-session fixtures)


def _page(items):
    data = {"props": {"pageProps": {"dehydratedState": {"queries": [{"queryKey": ["search"], "state": {"data": {"search": {"result": items, "total": len(items)}}}}]}}}}
    return ("<html><body><script id=\"__NEXT_DATA__\" type=\"application/json\">" + json.dumps(data, ensure_ascii=False) + "</script></body></html>").encode("utf-8")


def _item(i, expertise="متخصص پوست", city="شیراز"):
    name = f"{i:02d}"
    return {"type": "doctor", "record_type": "doctor", "prefix": "دکتر", "display_name": name, "display_expertise": expertise, "satisfaction": 80,
            "rates_count": 100 + i, "star": 4.0 + i / 20, "number_of_visits": 900, "waiting_time": "۱۰ دقیقه", "url": f"/dr/doc-{i:02d}/",
            "centers": [{"address": f"شیراز، خیابان {i}", "city_name": city, "map": {"lat": 29.6, "lon": 52.5}}]}


@pytest.fixture(autouse=True)
def _readers(monkeypatch):
    sr._cache.clear()
    monkeypatch.setattr(sr, "MIN_GAP_SECONDS", 0.0)
    monkeypatch.setenv(sr.ENABLED_ENV, "1")
    urls = dict(sr.listing_urls("پوست", "شیراز"))
    page = _page([_item(i) for i in range(1, 9)])                                                               # eight dermatologists in Shiraz
    monkeypatch.setattr(sr.safe_fetch, "fetch_page", lambda url: SimpleNamespace(ok=url == urls["paziresh24.com"], reason="", body=page))
    monkeypatch.setattr(cn._web_lookup, "web_lookup_enabled", lambda: False)
    monkeypatch.setattr(cn, "_dispatch_governed_search", lambda db_, request: [])
    yield
    sr._cache.clear()


@pytest.fixture
def orch(db, monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator

    monkeypatch.setattr(IntelligenceOrchestrator, "_journey_intake", lambda self, *a, **k: None)  # the care-journey interview is its own flow (R-109)
    return IntelligenceOrchestrator(db=db, legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)


def _turn(orch, user, text):
    return orch.process(authenticated_user_id=user.id, message=text, language="fa")


def _names(out):
    return [str(link["label"]).split(" — ")[0] for link in (out.links or ())]


# --- the request wording (matrix: phrasing x language; and what must NOT trigger) --------------------------------------------------------------------
@pytest.mark.parametrize("message", [
    "پنج تای بعدی", "۵ تای بعدی رو نشون بده", "بعدی", "یه دکتر دیگه", "پزشک دیگه ای هست؟", "بقیه رو نشون بده", "اینها مناسب نیست", "مناسب نبود",
    "نتونستم نوبت بگیرم", "نوبت نداره", "نوبت نمیده",
    "next five", "show me more", "show me the next five doctors", "these are not suitable", "I couldn't get an appointment", "another doctor please",
    "الخمسة التالية", "أريد طبيب آخر", "غير مناسب", "لم أستطع الحجز",
])
def test_next_five_phrasing_is_recognised_in_three_languages(message):
    assert pn.wants_next(message), message


@pytest.mark.parametrize("message", [
    "سلام", "ممنون", "فردا بعدی ظهر بهم یادآوری کن", "یه دکتر دیگه در تهران پیدا کن که نزدیک پارک باشه و حتما صبح ها وقت بده و خوب باشه ممنون ازت", "", None,
    "I need a new prescription", "how are you today",
])
def test_ordinary_messages_are_not_next_five_requests(message):
    assert not pn.wants_next(message), message


# --- the whole conversation ----------------------------------------------------------------------------------------------------------------------
def test_first_five_then_the_next_three_then_nothing_left(db, user, orch):
    first = _turn(orch, user, "یک متخصص پوست در شیراز معرفی کن")
    assert len(first.links) == 5
    shown = _names(first)
    assert all(label.startswith("دکتر ") for label in shown)
    # every link carries the doctor's NAME and SPECIALTY, and is the page of that doctor on the site
    for link in first.links:
        assert link["kind"] == "provider" and link["url"].startswith("https://www.paziresh24.com/dr/doc-") and "پوست" in link["label"] and "پذیرش۲۴" in link["label"]
    state = governed_raw.provider_intro_of_turn(db.query(models.Memory).filter(models.Memory.user_id == user.id).order_by(models.Memory.id.desc()).first())
    assert state and state["specialty"] == "پوست" and state["city"] == "شیراز" and len(state["names"]) == 5 and len(state["keys"]) == 5

    second = _turn(orch, user, "پنج تای بعدی")
    nxt = _names(second)
    assert len(nxt) == 3 and not set(nxt) & set(shown)                                                       # the remaining three, never a repeat
    assert second.message.startswith(sedi_copy.t("care_nav.next.intro", "fa"))
    assert all("پوست" in link["label"] for link in second.links)

    third = _turn(orch, user, "هنوز مناسب نیست")
    assert third.message.startswith("در همان فهرست") and "بگو" in third.message                              # honest: nothing left, one concrete next step
    assert all(link["kind"] == "search" for link in third.links)                                              # at most the booking sites' own search pages, never a doctor again


def test_not_suitable_after_an_introduction_also_continues(db, user, orch):
    first = _turn(orch, user, "یک متخصص پوست در شیراز معرفی کن")
    again = _turn(orch, user, "نتونستم نوبت بگیرم")
    assert not set(_names(again)) & set(_names(first)) and len(_names(again)) == 3


def test_without_an_earlier_introduction_the_phrase_is_not_special(db, user, orch):
    out = _turn(orch, user, "پنج تای بعدی")
    assert not out.links and "R116_NEXT_FIVE" not in str(getattr(out, "reason_codes", ""))


def test_a_new_place_in_the_request_is_a_new_search_not_the_next_five(db, user, orch):
    _turn(orch, user, "یک متخصص پوست در شیراز معرفی کن")
    assert pn.next_request(db, user.id, "یه دکتر دیگه در شیراز", "fa") is None


def test_an_old_introduction_is_not_continued(db, user, orch):
    _turn(orch, user, "یک متخصص پوست در شیراز معرفی کن")
    row = db.query(models.Memory).filter(models.Memory.user_id == user.id).order_by(models.Memory.id.desc()).first()
    assert pn.latest_state(db, user.id, now=row.created_at + timedelta(hours=13)) is None
    assert pn.latest_state(db, user.id, now=row.created_at + timedelta(hours=1)) is not None


# --- the link text (Javad: the doctor's name AND specialty are in the link) ------------------------------------------------------------------------
def test_the_link_label_has_name_specialty_and_site_without_repeating_the_specialty():
    ident = SimpleNamespace(source_url="https://www.paziresh24.com/dr/x/", canonical_name="دکتر الف", specialty_or_service="متخصص پوست")
    assert pl.links_for_identities([ident], "fa")[0]["label"] == "دکتر الف — متخصص پوست — پذیرش۲۴"
    assert pl.links_for_identities([ident], "en")[0]["label"] == "دکتر الف — متخصص پوست — Paziresh24"
    no_spec = SimpleNamespace(source_url="https://www.paziresh24.com/dr/y/", canonical_name="دکتر ب", specialty_or_service=None)
    assert pl.links_for_identities([no_spec], "fa", specialty="پوست")[0]["label"] == "دکتر ب — پوست — پذیرش۲۴"          # the requested specialty fills the gap
    echo = SimpleNamespace(source_url="https://www.paziresh24.com/dr/z/", canonical_name="دکتر پوست ج", specialty_or_service="پوست")
    assert pl.links_for_identities([echo], "fa")[0]["label"] == "دکتر پوست ج — پذیرش۲۴"                                    # name already says it


@pytest.mark.parametrize("url,ok", [
    ("https://www.paziresh24.com/dr/doc-01/", True), ("https://doctoreto.com/doctor/x/AbC", True), ("https://doctoreto.com/doctors/speciality/x", False),
    ("https://www.paziresh24.com/s/shiraz/dermatology/", False), ("http://www.paziresh24.com/dr/x/", False), ("https://evil.example/dr/x/", False),
    ("https://www.paziresh24.com.evil.example/dr/x/", False), ("javascript:alert(1)", False), ("", False),
])
def test_only_the_page_of_one_doctor_on_its_own_site_is_a_link(url, ok):
    assert sr.profile_url_ok(url) is ok


# --- accuracy (found on the LIVE pages 2026-11-25) ------------------------------------------------------------------------------------------------
def test_a_profile_link_with_a_persian_slug_is_percent_encoded_so_every_client_opens_it():
    raw = "https://www.paziresh24.com/dr/دکتر-حسن-چراغی/"
    enc = sr.encode_url(raw)
    assert enc == "https://www.paziresh24.com/dr/%D8%AF%DA%A9%D8%AA%D8%B1-%D8%AD%D8%B3%D9%86-%DA%86%D8%B1%D8%A7%D8%BA%DB%8C/"
    assert sr.encode_url(enc) == enc                                                                           # idempotent
    assert sr.profile_url_ok(raw) and sr.profile_url_ok(enc) and pl.safe_url(enc) == enc


def test_the_rows_carry_the_encoded_link_and_the_doctors_own_specialty_text(monkeypatch):
    urls = dict(sr.listing_urls("پوست", "شیراز"))
    item = _item(1)
    item["url"] = "/dr/دکتر-الف-ب/"
    monkeypatch.setattr(sr.safe_fetch, "fetch_page", lambda url: SimpleNamespace(ok=url == urls["paziresh24.com"], reason="", body=_page([item])))
    sr._cache.clear()
    rows = sr.provider_rows("پوست", "شیراز")
    assert rows[0]["source_url"].startswith("https://www.paziresh24.com/dr/%D8%AF") and rows[0]["specialty"] == "متخصص پوست"


def test_midwives_fellowships_and_other_specialties_are_never_introduced_as_the_requested_specialist(monkeypatch):
    urls = dict(sr.listing_urls("زنان", "شیراز"))
    items = [_item(1, expertise="کارشناس مامایی"), _item(2, expertise="فلوشیپ پیوند کبد"),
             _item(3, expertise="متخصص زنان و زایمان"), _item(4, expertise="فوق تخصص روماتولوژی"), _item(5, expertise="متخصص زنان")]
    monkeypatch.setattr(sr.safe_fetch, "fetch_page", lambda url: SimpleNamespace(ok=url == urls["paziresh24.com"], reason="", body=_page(items)))
    sr._cache.clear()
    names = [r["name"] for r in sr.provider_rows("زنان", "شیراز")]
    assert sorted(names) == ["دکتر 03", "دکتر 05"]                                                          # only those whose own text names the specialty


# --- Codex round 1 on PR 225 ----------------------------------------------------------------------------------------------------------------------
def test_p1_a_revoked_memory_consent_leaves_no_previous_five_to_continue_from(db, user, orch):
    from backend.app.services.i6 import consent_service as consent

    _turn(orch, user, "یک متخصص پوست در شیراز معرفی کن")
    assert pn.next_request(db, user.id, "پنج تای بعدی", "fa") is not None
    consent.revoke_memory_consent(db, user.id)
    assert pn.latest_state(db, user.id) is None and pn.next_request(db, user.id, "پنج تای بعدی", "fa") is None


def test_p2_naming_another_specialty_or_kind_is_a_new_request_not_the_next_five(db, user, orch):
    _turn(orch, user, "یک متخصص پوست در شیراز معرفی کن")
    assert pn.next_request(db, user.id, "another doctor, a cardiologist please", "en") is None
    assert pn.next_request(db, user.id, "یه دکتر دیگه، قلب", "fa") is None
    assert pn.next_request(db, user.id, "یه آزمایشگاه دیگه", "fa") is None
    assert pn.next_request(db, user.id, "یه دکتر پوست دیگه", "fa") is not None                                 # the SAME specialty named again still continues


def test_p2_the_governed_directory_is_fetched_wide_enough_for_the_second_batch(monkeypatch):
    monkeypatch.setenv(sr.ENABLED_ENV, "0")
    seen = []
    rows = [{"canonical_directory_key": f"k{i}", "id": i, "record_state": "ACTIVE", "canonical_name": f"دکتر {i:02d}", "entity_type": "DOCTOR"} for i in range(12)]

    def search_doctors(db_, **k):
        seen.append(k["limit"])
        return rows[: k["limit"]]

    monkeypatch.undo()                                                                                         # keep the module fixtures' stubs out of this unit
    monkeypatch.setattr(cn._governed_directory, "search_doctors", search_doctors)
    monkeypatch.setattr(cn, "_map_backend_row", lambda item: cn.VerifiedDirectoryIdentity(
        directory_record_id=item["id"], entity_type="DOCTOR", canonical_name=item["canonical_name"], canonical_directory_key=item["canonical_directory_key"],
        specialty_or_service="پوست", city="شیراز", province="فارس", source_system_label="GOVERNED", record_state="ACTIVE", last_verified_at=None,
        endorsement_disclaimer=""))
    monkeypatch.setattr(cn._web_lookup, "web_lookup_enabled", lambda: False)
    first = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALIST, specialty_or_service="پوست", city="شیراز", province="فارس", language="fa")
    one = cn.query_governed_directory(None, first)
    shown = [i.canonical_name for i in one.identities]
    second = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALIST, specialty_or_service="پوست", city="شیراز", province="فارس", language="fa",
                               exclude_names=tuple(one.intro_state["names"]))
    two = cn.query_governed_directory(None, second)
    assert len(shown) == 5 and seen[-1] >= 10
    assert len(two.identities) == 5 and not {i.canonical_name for i in two.identities} & set(shown)         # a real second batch, never a repeat


def test_p2_the_qualifiers_of_the_first_search_survive_into_the_next_five(db, user, orch):
    req = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALIST, specialty_or_service="پوست", city="شیراز", province="فارس", language="fa",
                            qualifiers=("high_rating", "urgent"))
    ident = SimpleNamespace(canonical_name="دکتر الف")
    state = cn._intro_state(req, [ident], ["k1"])
    assert state["qualifiers"] == ["high_rating", "urgent"]
    again = pn.request_from_state({**state, "v": 1}, "fa", user.id)
    assert again.qualifiers == ("high_rating", "urgent") and again.exclude_names == ("دکتر الف",)


@pytest.mark.parametrize("message", ["I don't need another doctor", "دکتر دیگه نمی‌خوام", "no more doctors, thanks, I don't want another doctor"])
def test_p2_a_refusal_is_not_a_continuation(db, user, orch, message):
    _turn(orch, user, "یک متخصص پوست در شیراز معرفی کن")
    assert pn.next_request(db, user.id, message, "fa") is None

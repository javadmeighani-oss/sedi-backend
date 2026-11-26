"""R-120 am.1/am.2 (Javad 2026-11-26, re-test of the Tehranpars cardiology chat):
a place question stands alone; a request without a place uses the place he already gave; care AFTER the list is built from what he said;
the close says «مرا در جریان قرار بده»; in TEHRAN the neighbourhood decides (its doctors, then the nearest, one clearly better farther doctor
with why; «only my neighbourhood» = only there); other cities are city-wide; each doctor's line travels with its own link."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app import sedi_copy
from backend.app.services.care_journey import followup_questions as fq
from backend.app.services.care_journey import journey as j
from backend.app.services.care_journey import personal_care as pc
from backend.app.services.i5 import care_nav_interview as ci
from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import provider_links as pl
from backend.app.services.i5 import site_readers as sr
from backend.app.services.i5 import specialty_lexicon as sl

PILOT = "میخوام برم یه دکتر متخصص قلب پیدا کنی تو تهرانپارس"


# --- a place question stands alone ------------------------------------------------------------------------------------------------------------
def test_a_place_question_never_carries_the_care_block(monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator

    monkeypatch.setattr(j, "results_block", lambda *a, **k: "CARE BLOCK")
    orch = IntelligenceOrchestrator(db=MagicMock(), legacy_generator=lambda *a, **k: {"message": "GEN"}, structured_mode=False)
    for q in (sedi_copy.t("care_nav.ask_place_missing", "fa"), ci.first_question(PILOT, "fa"), sedi_copy.t("care_nav.ask_place", "en", place="x")):
        out, started = orch._with_care_journey(q, PILOT, "fa", 7)
        assert out == q and not started
    out, started = orch._with_care_journey("LIST", PILOT, "fa", 7)
    assert out.endswith("CARE BLOCK") and started                                                                # after a real list it stays


# --- the place he already gave ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("rows,expected", [
    ([SimpleNamespace(user_message="تهرانپارس هستم", sedi_response="LIST"), SimpleNamespace(user_message="یه دکتر قلب معرفی کن", sedi_response=sedi_copy.t("care_nav.ask_place_missing", "fa"))], "تهران"),
    ([SimpleNamespace(user_message="اره", sedi_response="LIST"), SimpleNamespace(user_message=PILOT, sedi_response=ci.first_question(PILOT, "fa"))], "تهران"),
    ([SimpleNamespace(user_message="یه دکتر پوست در شیراز معرفی کن", sedi_response="LIST")], "شیراز"),
])
def test_a_request_without_a_place_uses_the_place_he_gave(rows, expected):
    got = ci.last_known_place(rows)
    assert got and expected in got


def test_without_any_place_or_residence_it_is_asked():
    assert ci.last_known_place([SimpleNamespace(user_message="سلام", sedi_response="سلام")]) is None
    assert ci.last_known_place([], home=("تهرانپارس", "تهران")) == "تهرانپارس تهران"


# --- care after the list, from his own words ------------------------------------------------------------------------------------------------------
class _Client:
    def __init__(self, payload=None, boom=False):
        self.payload, self.boom, self.kw = payload, boom, []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.kw.append(kw)
        if self.boom:
            raise TimeoutError("slow")
        return SimpleNamespace(output_text=json.dumps(self.payload, ensure_ascii=False))


def test_personal_care_is_built_from_what_he_said_inside_the_guards(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.delenv(fq.DISABLED_ENV, raising=False)
    good = ["تا روز ویزیت از بالا رفتن سریع پله‌ها پرهیز کن و آرام راه برو.", "زمان و شدت سنگینی قفسه‌ی سینه را هر روز یادداشت کن تا به پزشک نشان بدهی."]
    bad = ["یک قرص آسپرین بخور.", "نگران نباش، چیزی نیست.", "آیا شب‌ها بدتر است؟", "https://x.ir را ببین."]
    client = _Client({"suggestions": bad + good})
    block = pc.personal_care_block(["موقع بالا رفتن از پله قفسه‌ی سینه‌ام سنگین می‌شود", "شب‌ها هم کم می‌خوابم"], "fa", "chest", "قلب", client=client)
    assert block.startswith(sedi_copy.t("journey.care.personal.lead", "fa")) and all(g in block for g in good) and not any(b in block for b in bad)
    assert block.endswith(sedi_copy.t("journey.care.emergency.chest", "fa"))                                     # the emergency line is fixed, never the model's
    assert "سؤال" not in block and "؟" not in block.split("\n\n")[0]
    assert client.kw[0]["input"].startswith("موقع بالا رفتن")


@pytest.mark.parametrize("client", [_Client(boom=True), _Client({"suggestions": ["فقط یکی."]}), _Client({"suggestions": ["قرص بخور.", "دوز را کم کن."]})])
def test_without_two_usable_lines_the_catalog_block_stays(monkeypatch, client):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert pc.personal_care_block(["درد دارم از دیروز"], "fa", "chest", client=client) is None


def test_results_block_prefers_the_personal_care_and_drops_the_generic_status_question(monkeypatch):
    monkeypatch.setattr(j, "_journey_open", lambda *a, **k: True)
    monkeypatch.setattr(pc, "personal_care_block", lambda *a, **k: "PERSONAL")
    assert j.results_block(MagicMock(), 7, PILOT, "fa", explanations=["از دیروز درد دارم"]) == "PERSONAL"
    monkeypatch.setattr(pc, "personal_care_block", lambda *a, **k: None)
    fallback = j.results_block(MagicMock(), 7, PILOT, "fa", explanations=["از دیروز درد دارم"])
    assert fallback.startswith(sedi_copy.t("journey.care.chest", "fa"))                                          # fail-open: the catalog block


def test_the_close_asks_to_be_kept_informed():
    assert "مرا در جریان قرار بده" in sedi_copy.t("care_nav.intro.close", "fa")


# --- Tehran: the neighbourhood decides ------------------------------------------------------------------------------------------------------------
def _page(next_data):
    return ("<html><body><script id=\"__NEXT_DATA__\" type=\"application/json\">" + json.dumps(next_data, ensure_ascii=False) + "</script></body></html>").encode("utf-8")


def _p24(items, areas=None):
    data = {"props": {"pageProps": {"dehydratedState": {"queries": [{"queryKey": ["search"], "state": {"data": {"search": {"result": items, "total": len(items)}}}}]},
                                    "filters": ([{"title": "محله و خیابان", "name": "area", "items": areas}] if areas else [])}}}
    return _page(data)


def _doc(i, address, lat, lon, star=4.5, count=50, expertise="متخصص بیماری‌های قلب و عروق", city="تهران"):
    return {"type": "doctor", "record_type": "doctor", "prefix": "دکتر", "display_name": f"قلب {i:02d}", "display_expertise": expertise, "satisfaction": 90,
            "rates_count": count, "star": star, "number_of_visits": 100, "waiting_time": "", "url": f"/dr/doc-{i:02d}/",
            "centers": [{"address": address, "city_name": city, "map": {"lat": lat, "lon": lon}}]}


TP = (35.73, 51.53)       # Tehranpars
NEAR = (35.72, 51.51)     # a few km away
FAR = (35.76, 51.37)      # Shahrak-e Gharb


def _tehran_site(only_city_top=True, star_far=4.95, count_far=900, city_star=None):
    base = "https://www.paziresh24.com/s/tehran/cardiovascular/"
    city = [_doc(1, "خیابان پیروزی", *NEAR, star=city_star or 4.9, count=300), _doc(2, "شهرک غرب", *FAR, star=star_far, count=count_far),
            _doc(3, "ونک", 35.76, 51.41, star=city_star or 4.8, count=200), _doc(4, "نارمک", 35.74, 51.50, star=city_star or 4.6, count=120)]
    area_page = [_doc(10, "تهرانپارس، خیابان ۱۹۶", *TP, star=4.4, count=40), _doc(11, "تهرانپارس، فلکه دوم", 35.735, 51.535, star=4.3, count=30)]
    text_page = [_doc(12, "تهران‌پارس، بلوار جشنواره", 35.728, 51.528, star=4.5, count=60), _doc(13, "ونک، خیابان ملاصدرا", 35.76, 51.41)]
    pages = {base: _p24(city, areas=[{"title": "تهرانپارس غربی", "value": "west-tehranpars", "count": 2, "href": "/s/tehran/cardiovascular/west-tehranpars/"},
                                     {"title": "ونک", "value": "vanak", "count": 5, "href": "/s/tehran/cardiovascular/vanak/"}]),
             "https://www.paziresh24.com/s/tehran/cardiovascular/west-tehranpars/": _p24(area_page),
             base + "?text=" + sr.quote("تهرانپارس"): _p24(text_page)}
    return lambda url: SimpleNamespace(ok=url in pages, reason="" if url in pages else "http_404", body=pages.get(url, b""))


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    sr._cache.clear(), sr._areas.clear(), sr._verified.clear()
    monkeypatch.setattr(sr, "MIN_GAP_SECONDS", 0.0)
    monkeypatch.setenv(sr.VERIFY_ENV, "false")
    yield
    sr._cache.clear(), sr._areas.clear(), sr._verified.clear()


def test_in_tehran_the_neighbourhood_doctors_come_first_then_the_nearest_then_one_worth_the_trip():
    rows = sr.provider_rows("قلب", "تهران", area="تهرانپارس", fetch=_tehran_site())
    names = [r["name"] for r in rows]
    assert names[:3] == ["دکتر قلب 12", "دکتر قلب 10", "دکتر قلب 11"]                                           # the neighbourhood's own doctors
    assert names[3:5] == ["دکتر قلب 01", "دکتر قلب 04"]                                                         # then the nearest (Pirouzi, Narmak)
    assert "دکتر قلب 13" not in names                                                                             # ?text hit outside Tehranpars is dropped
    worth = [r for r in rows if r.get("worth_far")]
    assert [r["name"] for r in worth] == ["دکتر قلب 02"] and len(rows) == 6                                      # one clearly better doctor farther away


def test_only_my_neighbourhood_means_only_there():
    rows = sr.provider_rows("قلب", "تهران", area="تهرانپارس", fetch=_tehran_site(), only_area=True)
    assert [r["name"] for r in rows] == ["دکتر قلب 12", "دکتر قلب 10", "دکتر قلب 11"] and not any(r.get("worth_far") for r in rows)


def test_no_farther_doctor_when_he_is_not_clearly_better():
    rows = sr.provider_rows("قلب", "تهران", area="تهرانپارس", fetch=_tehran_site(star_far=4.5, count_far=900, city_star=4.4))
    assert not any(r.get("worth_far") for r in rows) and len(rows) == 5


@pytest.mark.parametrize("text", ["یه متخصص قلب فقط در محله خودم پیدا کن", "فقط نزدیک خونه باشه", "only in my neighbourhood please", "فقط همین محله"])
def test_only_area_is_understood(text):
    assert "only_area" in sl.qualifiers(text)


@pytest.mark.parametrize("text", ["یه متخصص قلب خوب پیدا کن", "نزدیک‌ترین آزمایشگاه", "only the best doctor"])
def test_ordinary_requests_are_not_only_area(text):
    assert "only_area" not in sl.qualifiers(text)


def test_other_cities_are_city_wide():
    items = [_doc(1, "شیراز، معالی آباد", 29.6, 52.5, star=4.2, city="شیراز"), _doc(2, "شیراز، زند", 29.61, 52.53, star=4.9, count=400, city="شیراز")]
    url = dict(sr.listing_urls("قلب", "شیراز"))["paziresh24.com"]
    fetch = lambda u: SimpleNamespace(ok=u == url, reason="", body=_p24(items))  # noqa: E731
    rows = sr.provider_rows("قلب", "شیراز", area="معالی آباد", fetch=fetch)
    assert [r["name"] for r in rows][0] == "دکتر قلب 02"                                                          # the better one first: the area does not decide


# --- one bubble: each doctor's line travels with its own link -------------------------------------------------------------------------------------
def test_each_doctor_link_carries_his_title_place_note_and_link_text():
    ident = SimpleNamespace(source_url="https://www.paziresh24.com/dr/a/", canonical_name="دکتر الف", specialty_or_service="متخصص قلب",
                            address="تهرانپارس، خیابان ۱۹۶", city="تهران", note="از محله‌ات دورتر است…")
    link = pl.links_for_identities([ident], "fa")[0]
    assert link["title"] == "دکتر الف — متخصص قلب" and link["location"] == "تهرانپارس، خیابان ۱۹۶" and link["note"].startswith("از محله")
    assert link["link_text"] == sedi_copy.t("care_nav.links.open_on", "fa", site="پذیرش۲۴") and link["url"].endswith("/dr/a/")


def test_the_worth_note_reaches_the_identity_in_the_users_language(monkeypatch):
    monkeypatch.setenv(sr.ENABLED_ENV, "1")
    monkeypatch.setattr(sr.safe_fetch, "fetch_page", _tehran_site())
    monkeypatch.setattr(cn._web_lookup, "web_lookup_enabled", lambda: False)
    monkeypatch.setattr(cn, "_dispatch_governed_search", lambda db, r: [])
    out = cn.query_governed_directory(None, cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALIST, specialty_or_service="قلب", city="تهران", area="تهرانپارس", language="fa"))
    noted = [i for i in out.identities if i.note]
    assert len(out.identities) == 6 and len(noted) == 1 and "ارزش ویزیت" in noted[0].note


def test_an_open_explanation_is_recorded_in_memory(monkeypatch):
    stored = []
    monkeypatch.setattr(j, "_store_episode", lambda db, uid, text: stored.append(text) or True)
    ask = sedi_copy.t("journey.interview.chest", "fa")
    assert j.record_answer(MagicMock(), 7, "نه درد ندارم فقط می‌خواهم چکاپ کنم", ask) and stored
    assert not j.record_answer(MagicMock(), 7, "ممنون", ask)


def test_replay_a_second_request_without_a_place_uses_tehranpars_and_asks_nothing(monkeypatch):
    from datetime import datetime

    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    import backend.app.services.i6.consent_service as consent
    import backend.app.services.i7.retention as retention
    from backend.app.services.i10 import commitment_followup as cf

    monkeypatch.setenv(fq.DISABLED_ENV, "1")
    monkeypatch.setenv(sr.ENABLED_ENV, "0")
    monkeypatch.setattr(consent, "has_permission", lambda *a, **k: True)
    monkeypatch.setattr(cf, "open_journey_count", lambda *a, **k: 1)
    monkeypatch.setattr(IntelligenceOrchestrator, "_memory_first_request", lambda self, *a, **k: None)
    searched, rows = [], []
    monkeypatch.setattr(retention, "query_eligible_raw", lambda *a, limit=None, **k: list(rows)[: (limit or 60)])
    monkeypatch.setattr(cn._governed_directory, "search_doctors", lambda db_, **k: searched.append(k) or [])
    orch = IntelligenceOrchestrator(db=MagicMock(), legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)

    def say(text):
        out = orch.process(authenticated_user_id=42, message=text, language="fa")
        rows.insert(0, SimpleNamespace(id=len(rows) + 1, user_message=text, sedi_response=out.message, created_at=datetime.utcnow()))
        return out

    for text in (PILOT, "اره", "از دیروز موقع پله قفسه سینه‌ام سنگین می‌شود", "شب‌ها بدتر است"):
        say(text)
    first = len(searched)
    assert first and searched[-1]["city"] == "تهران"
    again = say("یه دکتر قلب خوب به من معرفی کن")
    assert len(searched) > first and searched[-1]["city"] == "تهران"                                              # no place question this time
    assert not ci.is_place_question(again.message) and "تهران" in again.message and "R120_LAST_PLACE_USED" in again.reason_codes


# --- Codex round 1 on PR 228 ------------------------------------------------------------------------------------------------------------------
def test_p2_only_my_neighbourhood_holds_for_the_whole_answer(monkeypatch):
    monkeypatch.setenv(sr.ENABLED_ENV, "1")
    monkeypatch.setattr(sr.safe_fetch, "fetch_page", _tehran_site())
    monkeypatch.setattr(cn._web_lookup, "web_lookup_enabled", lambda: False)
    governed = [{"canonical_directory_key": "g1", "id": 1, "record_state": "ACTIVE", "canonical_name": "دکتر ونک", "address": "ونک"}]
    monkeypatch.setattr(cn, "_dispatch_governed_search", lambda db, r: governed)
    monkeypatch.setattr(cn, "_map_backend_row", lambda item: cn.VerifiedDirectoryIdentity(
        directory_record_id=1, entity_type="DOCTOR", canonical_name=item["canonical_name"], canonical_directory_key=item["id"],
        specialty_or_service="قلب", city="تهران", province="تهران", source_system_label="GOVERNED", record_state="ACTIVE",
        last_verified_at=None, endorsement_disclaimer="", address=item["address"]))
    req = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALIST, specialty_or_service="قلب", city="تهران", area="تهرانپارس", language="fa",
                            qualifiers=("only_area",))
    out = cn.query_governed_directory(None, req)
    assert out.identities and "دکتر ونک" not in [i.canonical_name for i in out.identities]
    nearest = cn._nearest_area_result(None, req, cn.CareNavResult(status=cn.STATUS_NO_VERIFIED, entity=req.entity, user_message="x"))
    assert nearest.user_message == "x"                                                                           # never widened to other places


def test_p2_the_answers_to_both_interview_steps_reach_the_personal_care(monkeypatch):
    from datetime import datetime

    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    import backend.app.services.i6.consent_service as consent
    import backend.app.services.i7.retention as retention

    first_q = sedi_copy.t("journey.intake.lead", "fa") + "\n\n" + sedi_copy.t("journey.interview.chest", "fa")
    follow_q = fq.followup_message("x", "fa")
    rows = [SimpleNamespace(user_message="موقع پله درد دارم", sedi_response=follow_q, created_at=datetime.utcnow()),
            SimpleNamespace(user_message="اره", sedi_response=first_q, created_at=datetime.utcnow())]
    monkeypatch.setattr(consent, "has_permission", lambda *a, **k: True)
    monkeypatch.setattr(retention, "query_eligible_raw", lambda *a, **k: rows)
    orch = IntelligenceOrchestrator(db=MagicMock(), legacy_generator=lambda *a, **k: {"message": "GEN"}, structured_mode=False)
    assert orch._interview_explanations(42, "شب‌ها بدتر است") == ["موقع پله درد دارم", "شب‌ها بدتر است"]


# --- Codex round 2 on PR 228 ------------------------------------------------------------------------------------------------------------------
def test_p2_an_earlier_interview_about_another_complaint_never_feeds_this_care(monkeypatch):
    from datetime import datetime

    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    import backend.app.services.i6.consent_service as consent
    import backend.app.services.i7.retention as retention

    first_q = sedi_copy.t("journey.intake.lead", "fa") + "\n\n" + sedi_copy.t("journey.interview.generic", "fa")
    now = datetime.utcnow()
    rows = [SimpleNamespace(user_message="یه دکتر پوست در شیراز معرفی کن", sedi_response=first_q, created_at=now),  # the current (skin) interview
            SimpleNamespace(user_message="شب‌ها بدتر است", sedi_response="LIST OF HEART DOCTORS", created_at=now),     # the end of the heart chain
            SimpleNamespace(user_message="درد قفسه سینه دارم", sedi_response=first_q, created_at=now)]
    monkeypatch.setattr(consent, "has_permission", lambda *a, **k: True)
    monkeypatch.setattr(retention, "query_eligible_raw", lambda *a, **k: rows)
    orch = IntelligenceOrchestrator(db=MagicMock(), legacy_generator=lambda *a, **k: {"message": "GEN"}, structured_mode=False)
    assert orch._interview_explanations(42, "پوستم خارش دارد") == ["پوستم خارش دارد"]


def test_p2_only_area_keeps_the_city_listing_doctors_who_are_in_the_neighbourhood():
    base = "https://www.paziresh24.com/s/tehran/cardiovascular/"
    city = [_doc(1, "تهرانپارس، خیابان ۲۰۰", *TP, star=4.6, count=80), _doc(2, "ونک", 35.76, 51.41, star=4.9, count=300)]
    pages = {base: _p24(city)}  # no neighbourhood page, the text search fails
    fetch = lambda url: SimpleNamespace(ok=url in pages, reason="" if url in pages else "http_404", body=pages.get(url, b""))  # noqa: E731
    rows = sr.provider_rows("قلب", "تهران", area="تهرانپارس", fetch=fetch, only_area=True)
    assert [r["name"] for r in rows] == ["دکتر قلب 01"]

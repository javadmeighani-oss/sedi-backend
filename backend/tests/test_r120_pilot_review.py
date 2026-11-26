"""R-120 (Javad 2026-11-26, pilot chat «دکتر متخصص قلب در تهرانپارس»): fixed as classes (R-065).

(1) the opener's «last topic» is the REAL last conversation; (2) the place is asked once, short, and never again once given;
(3) the interview asks the REASON openly and the next questions come from the user's explanation; (4) a doctor search never runs
without a place (no nationwide list without links); (5) no «only information, not advice» line - the verified header + the visit close."""
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app import sedi_copy
from backend.app.services.care_journey import followup_questions as fq
from backend.app.services.care_journey import journey as j
from backend.app.services.i5 import care_nav_interview as ci
from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i7 import conversation_recap as recap

PILOT = "میخوام برم یه دکتر متخصص قلب پیدا کنی تو تهرانپارس"


# --- (1) the opener: the newest meaningful turn decides ------------------------------------------------------------------------------------
def _recap(monkeypatch, *messages):
    import backend.app.services.i6.consent_service as consent
    import backend.app.services.i7.retention as retention

    rows = [SimpleNamespace(user_id=7, user_message=m) for m in messages]  # NEWEST FIRST
    monkeypatch.setattr(consent, "has_permission", lambda *a, **k: True)
    monkeypatch.setattr(retention, "query_eligible_raw", lambda *a, **k: rows)
    monkeypatch.setattr(recap, "_disease_label", lambda *a, **k: None)
    monkeypatch.setattr(recap, "_lexicon_condition", lambda *a, **k: None)
    return recap.recap_topic(MagicMock(), 7, "fa")


@pytest.mark.parametrize("newest,expected_key", [
    (PILOT, "doctor"), ("یه دکتر خوب در شیراز معرفی کن", "doctor"), ("find me a doctor in Tehran", "doctor"),
    ("قرص فشارم را دیروز نخوردم", "medication"), ("از دیروز سرم درد می‌کند", "symptoms"),
])
def test_the_newest_turn_is_the_topic_not_an_older_reminder_turn(monkeypatch, newest, expected_key):
    lang = "en" if newest.isascii() else "fa"
    got = _recap(monkeypatch, newest, "فردا ساعت ۹ یادم بنداز", "این اعلان‌ها خیلی زیاده")
    assert got == sedi_copy.t(f"recap.phrase_in_app.{expected_key}", "fa"), (newest, lang)
    assert got != sedi_copy.t("recap.phrase_in_app.reminders", "fa")


def test_a_more_specific_topic_of_the_newest_turn_still_wins(monkeypatch):
    got = _recap(monkeypatch, "یه دکتر پوست در شیراز معرفی کن", "فردا ساعت ۹ یادم بنداز")
    assert got and got != sedi_copy.t("recap.phrase_in_app.reminders", "fa")                                    # «skin care», never the old reminder


def test_an_unnamed_newest_turn_gives_the_warm_generic_opener_never_an_older_topic(monkeypatch):
    assert _recap(monkeypatch, "امروز رفتم بیرون و هوا خوب بود", "فردا ساعت ۹ یادم بنداز") is None


# --- (2) the place: short, once --------------------------------------------------------------------------------------------------------------
def test_the_place_question_is_one_short_question():
    q = ci.first_question(PILOT, "fa")
    assert q == "محلهٔ «تهران‌پارس» در شهر تهران را می‌گویی؟" and ci.is_place_question(q)
    assert ci.is_place_question(sedi_copy.t("care_nav.ask_place", "en", place="x")) and ci.is_place_question(sedi_copy.t("care_nav.ask_place_missing", "fa"))


def test_a_place_already_given_is_never_asked_again():
    asked = ci.first_question(PILOT, "fa")
    earlier_yes = [SimpleNamespace(user_message="اره", sedi_response="لیست"), SimpleNamespace(user_message=PILOT, sedi_response=asked)]
    assert ci.place_already_known("یه دکتر پوست در تهرانپارس پیدا کن", earlier_yes) == "تهران‌پارس تهران"     # (b) confirmed before
    said_fully = [SimpleNamespace(user_message="من در تهرانپارس تهران زندگی می‌کنم", sedi_response="ممنون")]
    assert ci.place_already_known(PILOT, said_fully) == "تهران‌پارس تهران"                                       # (c) he named it with its city
    assert ci.place_already_known(PILOT, [], home=("تهرانپارس", "تهران")) == "تهران‌پارس تهران"                  # (a) stored residence
    assert ci.place_already_known(PILOT, [], home=("پردیس", "پردیس")) is None                                    # another residence: ask
    assert ci.place_already_known(PILOT, [SimpleNamespace(user_message="نه", sedi_response=asked)]) is None       # «no» is not a confirmation
    assert ci.place_already_known("یه دکتر قلب در شهر تهران پیدا کن", []) is None                                # nothing to confirm


# --- (3) the interview: open reason, then questions FROM the explanation --------------------------------------------------------------------
def test_the_interview_asks_the_reason_openly_no_symptom_checklist():
    for area in ("chest", "generic"):
        for lang in ("fa", "ar", "en"):
            text = sedi_copy.t(f"journey.interview.{area}", lang)
            assert j.is_interview_reply(text)
            for checklist in ("تنگی نفس", "عرق سرد", "shortness of breath", "cold sweat", "ضيق نفس"):
                assert checklist not in text


@pytest.mark.parametrize("answer", ["نه درد ندارم فقط میخوام چکاپ کنم", "چکاپ", "خودم هم نمی‌دانم، دکترم گفت برو", "just a check-up"])
def test_any_answer_to_the_interview_keeps_the_place_and_the_specialty(answer):
    done = ci.request_for_answer(PILOT + " در تهران‌پارس تهران", sedi_copy.t("journey.interview.chest", "fa"), answer, "fa")
    req = cn.parse_care_nav_request(done, language="fa")
    assert req.specialty_or_service == "قلب" and req.city == "تهران" and req.area                                   # the pilot lost its city here


class _Client:
    def __init__(self, payload=None, boom=False):
        self.payload, self.boom, self.kw = payload, boom, []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.kw.append(kw)
        if self.boom:
            raise TimeoutError("slow")
        return SimpleNamespace(output_text=json.dumps(self.payload, ensure_ascii=False))


def test_the_follow_up_questions_come_from_the_explanation_inside_the_guards(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.delenv(fq.DISABLED_ENV, raising=False)
    good = ["این درد بیشتر موقع فعالیت است یا در استراحت هم می‌آید؟", "روی خوابت اثر گذاشته است؟"]
    bad = ["آسپرین ۸۰ میلی‌گرم مصرف کن؟", "نگران نباش، چیزی نیست؟", "https://x.ir را ببین؟", "بدون علامت سؤال"]
    client = _Client({"questions": bad + good})
    msg = fq.followup_message("از دیروز موقع بالا رفتن از پله قفسه‌ی سینه‌ام سنگین می‌شود", "fa", "قلب", client=client)
    assert msg.startswith(sedi_copy.t("journey.followup.lead", "fa")) and j.is_followup_reply(msg) and j.is_interview_reply(msg)
    assert all(q in msg for q in good) and not any(b in msg for b in bad)
    sent = client.kw[0]
    assert sent["input"].startswith("از دیروز") and "قلب" in sent["instructions"] and "no diagnosis" in sent["instructions"]


@pytest.mark.parametrize("client", [_Client(boom=True), _Client({"questions": []}), _Client({"nope": 1})])
def test_any_model_failure_falls_back_to_the_catalog_question(monkeypatch, client):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    msg = fq.followup_message("درد دارم", "fa", None, client=client)
    assert msg.endswith(sedi_copy.t("journey.followup.fallback", "fa")) and j.is_followup_reply(msg)


def test_without_a_key_or_with_the_switch_no_model_is_called(monkeypatch):
    client = _Client({"questions": ["سؤال؟"]})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    fq.followup_message("درد دارم", "en", None, client=client)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv(fq.DISABLED_ENV, "1")
    fq.followup_message("درد دارم", "en", None, client=client)
    assert client.kw == []


# --- (4) never a doctor list without a place ---------------------------------------------------------------------------------------------------
def test_a_doctor_search_without_a_place_asks_the_place_and_lists_nobody(monkeypatch):
    called = []
    monkeypatch.setattr(cn, "_dispatch_governed_search", lambda db, r: called.append(r) or [])
    for entity, spec in ((cn.CareNavEntity.SPECIALIST, "قلب"), (cn.CareNavEntity.SPECIALTY_CENTER, "فیزیوتراپی")):
        out = cn.query_governed_directory(None, cn.CareNavRequest(entity=entity, specialty_or_service=spec, language="fa"))
        assert out.status == cn.STATUS_NO_VERIFIED and out.reason_code == "PLACE_MISSING" and not out.identities
        assert out.user_message == sedi_copy.t("care_nav.ask_place_missing", "fa") and ci.is_place_question(out.user_message)
    assert called == []                                                                                          # the nationwide list is never fetched
    named = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALIST, name_hint="احمدی", language="fa")
    cn.query_governed_directory(None, named)
    assert called                                                                                               # a doctor BY NAME may still be looked up


# --- (5) the wording around the list ------------------------------------------------------------------------------------------------------------
def _ident(**kw):
    base = dict(directory_record_id=0, entity_type="DOCTOR", canonical_name="دکتر الف", canonical_directory_key="k", specialty_or_service="متخصص قلب",
                city="تهران", province=None, source_system_label="WEB", record_state="ACTIVE", last_verified_at=None, endorsement_disclaimer="",
                source_url="https://www.paziresh24.com/dr/a/", web_trusted=True)
    base.update(kw)
    return cn.VerifiedDirectoryIdentity(**base)


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_verified_doctors_get_the_verified_header_and_the_visit_close_never_the_disclaimer(lang):
    msg = cn._serialize_hits_message([_ident()], lang)
    assert msg.startswith(sedi_copy.t("care_nav.intro.head_verified", lang)) and msg.endswith(sedi_copy.t("care_nav.intro.close", lang))
    for disclaimer in ("فقط اطلاعات", "رتبه‌بندی", "information only", "not a recommendation", "معلومات فقط"):
        assert disclaimer not in msg
    plain = cn._serialize_hits_message([_ident(source_url=None, web_trusted=None)], lang)
    assert plain.startswith(sedi_copy.t("care_nav.intro.head", lang))                                         # not claimed verified without a site page
    assert "information only" not in cn.source_info_message("en") and "فقط اطلاعات" not in cn.source_info_message("fa")


# --- the pilot chat, replayed through the real orchestrator --------------------------------------------------------------------------------------
def test_replay_the_tehranpars_chat_place_once_open_reason_followups_then_the_search_in_tehran(monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    import backend.app.services.i6.consent_service as consent
    import backend.app.services.i7.retention as retention
    from backend.app.services.i10 import commitment_followup as cf

    monkeypatch.setenv(fq.DISABLED_ENV, "1")
    monkeypatch.setattr(consent, "has_permission", lambda *a, **k: True)
    monkeypatch.setattr(cf, "open_journey_count", lambda *a, **k: 1)
    monkeypatch.setattr(IntelligenceOrchestrator, "_known_place", lambda self, *a, **k: None)
    searched, rows = [], []
    monkeypatch.setattr(retention, "query_eligible_raw", lambda *a, **k: list(rows))
    monkeypatch.setattr(cn._governed_directory, "search_doctors", lambda db_, **k: searched.append(k) or [])
    orch = IntelligenceOrchestrator(db=MagicMock(), legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)

    def say(text):
        out = orch.process(authenticated_user_id=42, message=text, language="fa")
        rows.insert(0, SimpleNamespace(user_message=text, sedi_response=out.message, created_at=datetime.utcnow()))
        return out

    place_q = say(PILOT)
    assert place_q.message == "محلهٔ «تهران‌پارس» در شهر تهران را می‌گویی؟" and not searched
    reason = say("اره")
    assert j.is_interview_reply(reason.message) and "تنگی نفس" not in reason.message and not searched
    follow = say("نه درد ندارم فقط میخوام چکاپ کنم")
    assert j.is_followup_reply(follow.message) and not searched
    say("خوابم خوب نیست و کمی نگرانم")
    assert searched and searched[-1]["city"] == "تهران"                                                          # never a nationwide list


# --- Codex round 1 on PR 227 ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("other", ["How do I change my password?", "رمز عبورم را چطور عوض کنم؟", "امروز هوا چطوره؟", "كيف أغير كلمة المرور؟"])
def test_p2_another_subject_after_the_interview_is_not_turned_into_the_doctor_search(other):
    assert ci.request_for_answer(PILOT + " در تهران‌پارس تهران", sedi_copy.t("journey.interview.chest", "fa"), other, "fa") is None


def test_p2_an_earlier_yes_counts_only_for_the_same_city():
    asked = ci.first_question(PILOT, "fa")
    earlier_yes = [SimpleNamespace(user_message="اره", sedi_response="لیست"), SimpleNamespace(user_message=PILOT, sedi_response=asked)]
    pardis_q = ci.first_question("یه دکتر قلب در پردیس پیدا کن", "fa")
    if pardis_q:  # Pardis is confirmed with the user (no verified directory slug) - Tehranpars' «yes» must not answer it
        assert ci.place_already_known("یه دکتر قلب در پردیس پیدا کن", earlier_yes) is None


@pytest.mark.parametrize("short", ["Yesterday", "دو ساعت", "دیروز", "از صبح", "سه روز پیش"])
def test_p2_a_short_time_answer_still_answers_the_interview(short):
    done = ci.request_for_answer(PILOT + " در تهران‌پارس تهران", sedi_copy.t("journey.followup.lead", "fa") + " " + sedi_copy.t("journey.followup.marker", "fa") + " از کی؟", short, "fa")
    assert done and cn.parse_care_nav_request(done, language="fa").city == "تهران", short

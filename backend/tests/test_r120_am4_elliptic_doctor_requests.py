"""R-120 am.4 (Javad's phone test 2026-11-28, prod 017aa1c9): Sedi opened with «last time we talked about finding the right doctor for you»;
«معرفی کن برام» got HER introduction, «منظورم پزشک بود» a single old doctor from the free model, «برام چندتای دیگه معرفی کن» her introduction again.
Class fix (R-065): a bare «introduce» is not a question about her; a short follow-up of an open doctor conversation is that doctor request,
completed from memory; «the next ones» continue an introduction for a week. Matrix: wording x language x turn pattern + a replay of the chat."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app import sedi_copy
from backend.app.core.conversation.prompts import ConversationPrompts
from backend.app.services.care_journey import followup_questions as fq
from backend.app.services.care_journey import journey as j
from backend.app.services.i5 import care_nav_memory as mem
from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import provider_next as pn
from backend.app.services.i5 import site_readers as sr
from backend.app.services.intelligence.about_sedi import about_sedi_reply, is_about_sedi_question

REQ = "برام یه متخصص قلب تو تهرانپارس تهران پیدا کن"
ASK = sedi_copy.t("journey.intake.lead", "fa") + "\n\n" + sedi_copy.t("journey.interview.chest", "fa")


# --- 1. a bare «introduce» is not a question about Sedi -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["معرفی کن برام", "برام چندتای دیگه معرفی کن", "یکی معرفی کن", "معرفی کن", "یه دکتر معرفی کن", "چند تا دیگه معرفی کن لطفا",
                                  "introduce me a doctor", "introduce me some more", "رشح لي طبيباً"])
def test_a_bare_introduce_is_not_about_her(text):
    assert not is_about_sedi_question(text)


@pytest.mark.parametrize("text", ["خودت را معرفی کن", "خودتو معرفی کن", "خودت رو برام معرفی کن", "معرفی کن خودتو", "یه معرفی از خودت بکن", "تو کی هستی",
                                  "introduce yourself", "who are you", "عرفني بنفسك", "من أنت"])
def test_introduce_yourself_still_gets_her_introduction(text):
    assert is_about_sedi_question(text)


@pytest.mark.parametrize("lang,text", [("fa", "معرفی کن برام"), ("fa", "یه دکتر قلب معرفی کن"), ("en", "introduce me a cardiologist"), ("ar", "قدم لي طبيب قلب")])
def test_the_model_prompt_gets_no_introduce_yourself_order_for_a_doctor_request(lang, text):
    built = ConversationPrompts(language=lang)._build_user_prompt(text, MagicMock(), {}, [])
    assert "[" not in built[len(text):len(text) + 4], built  # no injected self-introduction directive


@pytest.mark.parametrize("lang,text", [("fa", "خودت رو معرفی کن"), ("en", "introduce yourself"), ("ar", "عرفني بنفسك")])
def test_the_model_prompt_keeps_the_order_for_introduce_yourself(lang, text):
    assert ConversationPrompts(language=lang)._build_user_prompt(text, MagicMock(), {}, []) != text


# --- 2. a short follow-up of the doctor conversation ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["معرفی کن برام", "منظورم پزشک بود", "منظورم دکتر بود", "برام چندتای دیگه معرفی کن", "پیدا کن", "لطفا نشون بده",
                                  "یکی دیگه معرفی کن", "find me some", "I meant a doctor", "show me more please", "أقصد طبيب", "رشح لي"])
def test_a_short_follow_up_is_recognised(text):
    assert mem.asks_doctor_ellipsis(text)


@pytest.mark.parametrize("text", ["یه برنامه غذایی معرفی کن", "یه فیلم خوب معرفی کن", "رمزم را پیدا کن", "ممنون", "باشه", "show me my reminders",
                                  "introduce yourself", "find a recipe for dinner", "ابحث عن وصفة", "خوابم نمی‌بره"])
def test_a_request_with_its_own_subject_is_not_a_follow_up(text):
    assert not mem.asks_doctor_ellipsis(text)


def _row(user_message, sedi_response, hours_ago):
    return SimpleNamespace(user_message=user_message, sedi_response=sedi_response, created_at=datetime.utcnow() - timedelta(hours=hours_ago), provenance_json=None)


def test_the_doctor_topic_is_open_for_the_newest_doctor_conversation():
    now = datetime.utcnow()
    yesterday = [_row("هیچ مشکلی ندارم", "پزشکان…", 14), _row("چیز مهمی نیست فقط چک اپ", ASK, 14.1), _row(REQ, ASK, 14.2)]
    assert mem.doctor_topic_open(yesterday, now)
    assert mem.doctor_topic_open([_row("ممنون", "خواهش می‌کنم", 1)] + yesterday, now)  # «thanks» never closes it
    assert not mem.doctor_topic_open([_row("دیشب خیلی بد خوابیدم و خسته‌ام", "…", 1)] + yesterday, now)  # a newer subject closes it
    old = [_row(REQ, ASK, 24 * 8)]
    assert not mem.doctor_topic_open(old, now)  # a week later it is not «the last topic» any more


def test_the_follow_up_completes_the_open_request_from_memory(monkeypatch):
    import backend.app.services.care_state as care_state

    monkeypatch.setattr(care_state, "get_care_state", lambda *a, **k: None)
    monkeypatch.setattr(pn, "latest_state", lambda *a, **k: None)
    rows = [_row("هیچ مشکلی ندارم", "پزشکان…", 14), _row("چیز مهمی نیست فقط چک اپ", ASK, 14.1), _row(REQ, ASK, 14.2)]
    for text in ("معرفی کن برام", "منظورم پزشک بود", "برام چندتای دیگه معرفی کن"):
        out = mem.complete_request(MagicMock(), 7, text, "fa", rows=list(rows))
        assert out is not None and "R120_DOCTOR_ELLIPSIS_BOUND" in out.reason_codes, text
        req = cn.parse_care_nav_request(out.text, language="fa")
        assert req.specialty_or_service == "قلب" and "تهرانپارس" in out.text.replace("‌", ""), out.text
    # no open doctor conversation: the same words stay what they were
    assert mem.complete_request(MagicMock(), 7, "معرفی کن برام", "fa", rows=[_row("دیشب بد خوابیدم و خسته‌ام", "…", 1)]) is None


def test_the_next_five_keep_their_own_path_when_an_introduction_exists(monkeypatch):
    import backend.app.services.care_state as care_state

    monkeypatch.setattr(care_state, "get_care_state", lambda *a, **k: None)
    monkeypatch.setattr(pn, "latest_state", lambda *a, **k: {"v": 1, "specialty": "قلب"})
    rows = [_row("هیچ مشکلی ندارم", "پزشکان…", 14), _row(REQ, ASK, 14.2)]
    assert mem.complete_request(MagicMock(), 7, "برام چندتای دیگه معرفی کن", "fa", rows=rows) is None  # provider_next continues the list
    assert mem.complete_request(MagicMock(), 7, "معرفی کن برام", "fa", rows=rows) is not None


def test_yesterdays_introduction_is_still_continued():
    assert pn.MAX_AGE >= timedelta(days=7)


# --- 3. replay of the phone test -------------------------------------------------------------------------------------------------------------------
def test_replay_phone_test_every_turn_reaches_the_doctor_search_never_her_introduction(monkeypatch):
    from backend.app.services.i10 import commitment_followup as cf
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    import backend.app.services.care_state as care_state
    import backend.app.services.i6.consent_service as consent
    import backend.app.services.i7.retention as retention

    monkeypatch.setenv(fq.DISABLED_ENV, "1")
    monkeypatch.setenv(sr.ENABLED_ENV, "0")
    monkeypatch.setattr(cf, "open_journey_count", lambda *a, **k: 1)
    monkeypatch.setattr(care_state, "get_care_state", lambda *a, **k: None)
    monkeypatch.setattr(pn, "latest_state", lambda *a, **k: None)
    monkeypatch.setattr(consent, "has_permission", lambda *a, **k: True)
    monkeypatch.setattr(consent, "has_permission_readonly", lambda *a, **k: True)
    rows = [_row("هیچ مشکلی ندارم", "پزشکان…", 14), _row("چیز مهمی نیست فقط میخوام چک اپ بشم", fq.followup_message("x", "fa"), 14.1), _row(REQ, ASK, 14.2)]
    monkeypatch.setattr(retention, "query_eligible_raw", lambda *a, limit=None, **k: list(rows)[: (limit or 60)])
    searched = []
    monkeypatch.setattr(cn._governed_directory, "search_doctors", lambda db_, **k: searched.append(k) or [])
    orch = IntelligenceOrchestrator(db=MagicMock(), legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)
    about = about_sedi_reply("خودت را معرفی کن", "fa")

    for text in ("معرفی کن برام", "منظورم پزشک بود", "برام چندتای دیگه معرفی کن"):
        before = len(searched)
        out = orch.process(authenticated_user_id=42, message=text, language="fa")
        rows.insert(0, SimpleNamespace(user_message=text, sedi_response=out.message, created_at=datetime.utcnow(), provenance_json=None))
        assert out.message not in (about, "GEN") and not j.is_interview_reply(out.message), (text, out.message[:120])
        assert len(searched) > before and searched[-1]["city"] == "تهران", text


# --- Codex round 1 (PR 230) ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["I meant a doctor, but I don't need another doctor", "منظورم دکتر بود ولی دیگه دکتر نمی‌خوام", "معرفی کن، ولی دکتر لازم ندارم",
                                  "أقصد طبيب لكن لا أريد طبيباً"])
def test_p2_a_refusal_is_never_turned_back_into_the_search(text):
    assert not mem.asks_doctor_ellipsis(text)


@pytest.mark.parametrize("text", ["معرفی کنید", "پیدا کنید", "لطفا معرفی کنید", "نشان بدهید", "برام پیدا کنید"])
def test_p2_polite_full_verb_forms_are_follow_ups_too(text):
    assert mem.asks_doctor_ellipsis(text)


@pytest.mark.parametrize("text", ["introduce me some more", "find me some more", "recommend some more", "show me another", "چندتای دیگه معرفی کن",
                                  "بیشتر معرفی کن", "رشح لي المزيد"])
def test_p2_asking_for_more_goes_to_the_next_five_with_its_exclusions(text, monkeypatch):
    import backend.app.services.care_state as care_state

    assert pn.wants_next(text), text
    monkeypatch.setattr(care_state, "get_care_state", lambda *a, **k: None)
    monkeypatch.setattr(pn, "latest_state", lambda *a, **k: {"v": 1, "specialty": "قلب", "names": ["دکتر الف"]})
    rows = [_row(REQ, ASK, 3)]
    assert mem.complete_request(MagicMock(), 7, text, "fa", rows=rows) is None  # the next-five path keeps the shown names out


@pytest.mark.parametrize("text", ["معرفی کن برام", "پیدا کنید", "I meant a doctor"])
def test_a_follow_up_without_more_is_not_the_next_five(text):
    assert not pn.wants_next(text)

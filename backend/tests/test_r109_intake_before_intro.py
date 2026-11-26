"""R-109 (Javad 2026-11-20): the doctor is introduced AFTER Sedi has gathered what she wants to know, so the most suitable option is chosen.

Reason + place settled -> the grouped interview (up to three questions) comes FIRST, with no search; the answer completes the request
(qualifiers such as «urgent» survive) and only then the introduction + stabilising care + «how are you now?» are sent.
DB-free: owners are stubbed; the orchestrator branch, the answer binding and the wording run for real.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app import sedi_copy
from backend.app.services.care_journey import journey as j
from backend.app.services.i5 import care_nav_interview as cni
from backend.app.services.i10 import commitment_followup as cf

REQUEST = "یه دکتر قلب در شهر پردیس معرفی کن"


def _owners(monkeypatch, *, open_count=0, created=True):
    calls = []
    monkeypatch.setattr(cf, "open_journey_count", lambda db, uid: open_count)
    monkeypatch.setattr(cf, "create_journey_followup", lambda db, uid, step, tier: calls.append(tier) or (SimpleNamespace(id=9) if created else None))
    return calls


# --- the intake message -----------------------------------------------------------------------------------------------------------------------
def test_the_intake_is_a_lead_plus_up_to_three_grouped_questions_and_tracks_the_journey(monkeypatch):
    calls = _owners(monkeypatch)
    db = MagicMock()
    text = j.intake_message(db, 1, REQUEST, "fa", intake_done=False)
    assert text.startswith(sedi_copy.t("journey.intake.lead", "fa")) and j.is_interview_reply(text)
    assert "فعالیت سنگین نکن" not in text  # the care block follows the introduction, not the questions
    assert calls == ["acute"] and db.commit.call_count == 1


@pytest.mark.parametrize("lang,req", [("fa", REQUEST), ("en", "find a heart doctor in Shiraz"), ("ar", "أحتاج طبيب قلب في شيراز")])
def test_the_intake_exists_in_every_language(monkeypatch, lang, req):
    _owners(monkeypatch)
    text = j.intake_message(MagicMock(), 1, req, lang, intake_done=False)
    assert text and j.is_interview_reply(text) and "{" not in text


def test_an_open_journey_is_not_created_twice_but_the_interview_is_still_asked(monkeypatch):
    calls = _owners(monkeypatch, open_count=1)
    assert j.intake_message(MagicMock(), 1, REQUEST, "fa", intake_done=False) and calls == []


@pytest.mark.parametrize("kw", [dict(intake_done=True)])
def test_nothing_is_asked_once_it_was_asked(monkeypatch, kw):
    _owners(monkeypatch)
    assert j.intake_message(MagicMock(), 1, REQUEST, "fa", **kw) is None


def test_no_consent_no_question_and_an_emergency_goes_to_the_safety_path(monkeypatch):
    _owners(monkeypatch, created=False)
    assert j.intake_message(MagicMock(), 1, REQUEST, "fa", intake_done=False) is None  # nothing tracked -> nothing asked
    _owners(monkeypatch)
    assert j.intake_message(MagicMock(), 1, "قفسه سینه‌ام درد می‌کند و نفسم تنگ است، دکتر قلب", "fa", intake_done=False) is None
    assert j.intake_message(None, 1, REQUEST, "fa", intake_done=False) is None


def test_the_kill_switch_removes_the_intake(monkeypatch):
    _owners(monkeypatch)
    monkeypatch.setenv(j.DISABLED_ENV, "1")
    assert j.intake_message(MagicMock(), 1, REQUEST, "fa", intake_done=False) is None


def test_the_results_block_is_care_plus_the_status_question_only_while_a_journey_is_open(monkeypatch):
    _owners(monkeypatch, open_count=1)
    block = j.results_block(MagicMock(), 1, REQUEST, "fa")
    assert "فعالیت سنگین نکن" in block and "الان وضعیتت چطور است" in block and not j.is_interview_reply(block)
    _owners(monkeypatch, open_count=0)
    assert j.results_block(MagicMock(), 1, REQUEST, "fa") is None


# --- the answer completes the request ---------------------------------------------------------------------------------------------------------
def _interview_reply():
    return sedi_copy.t("journey.intake.lead", "fa") + "\n\n" + sedi_copy.t("journey.interview.chest", "fa")


def test_the_interview_answer_completes_the_pending_request_and_urgency_survives():
    out = cni.request_for_answer(REQUEST, _interview_reply(), "از دو روز پیش شروع شده و قبلاً نداشتم", "fa")
    assert out and "پردیس" in out and "قلب" in out
    urgent = cni.request_for_answer(REQUEST, _interview_reply(), "تب بالا و سرفه دارم از دیروز", "fa")
    assert urgent and "پردیس" in urgent


def test_never_mind_a_red_flag_or_a_new_complete_request_is_not_an_interview_answer():
    assert cni.request_for_answer(REQUEST, _interview_reply(), "ولش کن", "fa") is None
    assert cni.request_for_answer(REQUEST, _interview_reply(), "قفسه سینه‌ام درد می‌کند و نفسم تنگ شده", "fa") is None
    assert cni.request_for_answer(REQUEST, _interview_reply(), "یه دکتر پوست در شیراز معرفی کن", "fa") is None


def test_an_ordinary_reply_is_not_treated_as_an_interview():
    assert cni.request_for_answer(REQUEST, "یه جواب معمولی", "از دو روز پیش", "fa") is None


# --- through the real orchestrator -------------------------------------------------------------------------------------------------------------
def _orch(monkeypatch, rows=()):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    import backend.app.services.i6.consent_service as consent
    import backend.app.services.i7.retention as retention
    from backend.app.services.i5 import care_navigation_directory as cn

    searched = []
    monkeypatch.setenv("SEDI_CARE_FOLLOWUP_MODEL_DISABLED", "1")  # R-120 second step: the deterministic catalog question in tests
    monkeypatch.setattr(consent, "has_permission", lambda *a, **k: True)
    monkeypatch.setattr(retention, "query_eligible_raw", lambda *a, **k: list(rows))
    monkeypatch.setattr(cn._governed_directory, "search_doctors", lambda db_, **k: searched.append(k) or [])
    orch = IntelligenceOrchestrator(db=MagicMock(), legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)
    return orch, searched


def test_a_doctor_request_gets_the_interview_first_and_no_search(monkeypatch):
    _owners(monkeypatch)
    orch, searched = _orch(monkeypatch)
    out = orch.process(authenticated_user_id=42, message=REQUEST, language="fa")
    assert "R109_CARE_JOURNEY_INTAKE" in out.reason_codes
    assert j.is_interview_reply(out.message) and out.message.startswith(sedi_copy.t("journey.intake.lead", "fa"))
    assert searched == []  # nothing is introduced before Sedi has understood the situation


def test_the_answer_triggers_the_search_and_the_introduction_carries_care_and_status(monkeypatch):
    _owners(monkeypatch, open_count=1)
    asked = SimpleNamespace(user_message=REQUEST, sedi_response=_interview_reply(), created_at=datetime.utcnow())
    orch, searched = _orch(monkeypatch, rows=[asked])
    explained = "از دو روز پیش شروع شده و قبلاً نداشتم"
    follow = orch.process(authenticated_user_id=42, message=explained, language="fa")
    # R-120: the explanation first gets questions built FROM it (second interview step), still no search
    assert follow.message.startswith(sedi_copy.t("journey.followup.lead", "fa")) and j.is_followup_reply(follow.message) and searched == []
    second = SimpleNamespace(user_message=explained, sedi_response=follow.message, created_at=datetime.utcnow())
    orch, searched = _orch(monkeypatch, rows=[second, asked])
    out = orch.process(authenticated_user_id=42, message="خوابم کم شده و کمی نگرانم", language="fa")
    assert searched, "the search runs after the interview is answered"
    assert "R109_CARE_JOURNEY_INTAKE" not in out.reason_codes and "R109_CARE_JOURNEY" in out.reason_codes
    assert "الان وضعیتت چطور است" in out.message and not j.is_interview_reply(out.message)  # no second interview


def test_the_interview_is_not_repeated_when_the_request_comes_again(monkeypatch):
    _owners(monkeypatch, open_count=1)
    asked = SimpleNamespace(user_message=REQUEST, sedi_response=_interview_reply(), created_at=datetime.utcnow())
    orch, searched = _orch(monkeypatch, rows=[asked])
    out = orch.process(authenticated_user_id=42, message="یه دکتر قلب دیگه در شهر پردیس معرفی کن", language="fa")
    assert "R109_CARE_JOURNEY_INTAKE" not in out.reason_codes and searched


def test_a_pharmacy_request_is_never_interviewed(monkeypatch):
    _owners(monkeypatch)
    orch, _ = _orch(monkeypatch)
    out = orch.process(authenticated_user_id=42, message="یه داروخانه شبانه‌روزی در شهر شیراز", language="fa")
    assert "R109_CARE_JOURNEY_INTAKE" not in out.reason_codes


def test_without_memory_consent_the_user_gets_the_search_not_a_question_that_cannot_be_kept(monkeypatch):
    import backend.app.services.i6.consent_service as consent

    _owners(monkeypatch, created=False)
    orch, searched = _orch(monkeypatch)
    out = orch.process(authenticated_user_id=42, message=REQUEST, language="fa")
    assert "R109_CARE_JOURNEY_INTAKE" not in out.reason_codes and searched
    assert consent is not None


# --- Codex round 1 on PR 198 ------------------------------------------------------------------------------------------------------------------
def test_p2_an_unrelated_message_after_the_interview_is_not_bound_to_the_doctor_request():
    reply = _interview_reply()
    assert cni.request_for_answer(REQUEST, reply, "فردا ساعت ۸ یادم بنداز قرصم را بخورم", "fa") is None
    assert cni.request_for_answer(REQUEST, reply, "remind me to take my medicine tomorrow", "en") is None
    assert cni.request_for_answer(REQUEST, reply, "یه دندانپزشک پیدا کن", "fa") is None


def test_p2_a_skip_phrase_still_proceeds_to_the_introduction():
    reply = _interview_reply()
    for phrase in ("فقط معرفی کن", "بدون سوال همین الان معرفی کن", "just introduce someone"):
        out = cni.request_for_answer(REQUEST, reply, phrase, "fa" if phrase[0] != "j" else "en")
        assert out and "پردیس" in out, phrase


def test_p2_the_earlier_heart_interview_does_not_excuse_a_skin_request(monkeypatch):
    _owners(monkeypatch)
    asked = SimpleNamespace(user_message=REQUEST, sedi_response=_interview_reply(), created_at=datetime.utcnow())
    orch, searched = _orch(monkeypatch, rows=[asked])
    out = orch.process(authenticated_user_id=42, message="یه دکتر پوست در شهر شیراز معرفی کن", language="fa")
    assert "R109_CARE_JOURNEY_INTAKE" in out.reason_codes and searched == []  # a new complaint gets its own intake


# --- Codex round 2 on PR 198 ------------------------------------------------------------------------------------------------------------------
def test_p2_a_lab_request_without_a_specialty_is_not_interviewed_twice(monkeypatch):
    _owners(monkeypatch, open_count=1)
    lab = "یه آزمایشگاه در شهر شیراز معرفی کن"
    orch, searched = _orch(monkeypatch)
    first = orch.process(authenticated_user_id=42, message=lab, language="fa")
    assert "R109_CARE_JOURNEY_INTAKE" in first.reason_codes
    asked = SimpleNamespace(user_message=lab, sedi_response=first.message, created_at=datetime.utcnow())
    orch2, searched2 = _orch(monkeypatch, rows=[asked])
    second = orch2.process(authenticated_user_id=42, message="فقط معرفی کن", language="fa")
    assert "R109_CARE_JOURNEY_INTAKE" not in second.reason_codes and "آزمایشگاه" in second.message and not j.is_interview_reply(second.message)  # the skip reaches the directory (lab path)
    third = orch2.process(authenticated_user_id=42, message=lab, language="fa")
    assert "R109_CARE_JOURNEY_INTAKE" not in third.reason_codes


# --- Codex round 3 on PR 198 ------------------------------------------------------------------------------------------------------------------
def test_p2_the_reason_flow_does_not_ask_the_intake_twice(monkeypatch):
    """«a good doctor in Pardis» -> «my heart hurts sometimes» (reason flow) -> intake -> answer: the raw turns carry no specialty."""
    _owners(monkeypatch, open_count=1)
    rows = [
        SimpleNamespace(user_message="گاهی قلبم درد می‌کند", sedi_response=_interview_reply(), created_at=datetime.utcnow()),
        SimpleNamespace(user_message="یه دکتر خوب در شهر پردیس معرفی کن", sedi_response=cni.reason_question("یه دکتر خوب در شهر پردیس معرفی کن", "fa"), created_at=datetime.utcnow()),
    ]
    orch, searched = _orch(monkeypatch, rows=rows)
    explained = "از دو روز پیش شروع شده و قبلاً نداشتم"
    follow = orch.process(authenticated_user_id=42, message=explained, language="fa")
    assert j.is_followup_reply(follow.message) and not searched                                                  # R-120: questions built from the explanation
    rows = [SimpleNamespace(user_message=explained, sedi_response=follow.message, created_at=datetime.utcnow())] + rows
    orch, searched = _orch(monkeypatch, rows=rows)
    out = orch.process(authenticated_user_id=42, message="شب‌ها بدتر است", language="fa")
    assert "R109_CARE_JOURNEY_INTAKE" not in out.reason_codes and searched


def test_p2_another_kind_or_specialty_still_gets_its_own_intake(monkeypatch):
    _owners(monkeypatch)
    heart = SimpleNamespace(user_message=REQUEST, sedi_response=_interview_reply(), created_at=datetime.utcnow())
    orch, searched = _orch(monkeypatch, rows=[heart])
    assert "R109_CARE_JOURNEY_INTAKE" in orch.process(authenticated_user_id=42, message="یه آزمایشگاه در شهر شیراز معرفی کن", language="fa").reason_codes
    assert "R109_CARE_JOURNEY_INTAKE" in orch.process(authenticated_user_id=42, message="یه دکتر پوست در شهر شیراز معرفی کن", language="fa").reason_codes
    assert searched == []

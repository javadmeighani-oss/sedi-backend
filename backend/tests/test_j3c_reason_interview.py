"""J3-c (D-410): ask WHY / WHICH doctor first; the answer completes the request; source and «why» only on request."""
import pytest

from backend.app import sedi_copy
from backend.app.services.i5 import care_nav_interview as ci
from backend.app.services.i5 import care_navigation_directory as cn

Q = {lang: sedi_copy.t(ci.ASK_KEY, lang) for lang in ("fa", "ar", "en")}


@pytest.mark.parametrize("msg, lang", [
    ("میخواهم یه دکتر خوب برام تو پردیس معرفی کنی", "fa"), ("یه دکتر خوب در تهرانپارس معرفی کن", "fa"),
    ("find me a good doctor in Shiraz", "en"), ("أحتاج طبيب في طهران", "ar"), ("I need a doctor in Karaj", "en")])
def test_a_doctor_request_with_no_specialty_gets_the_reason_question_first(msg, lang):
    assert ci.reason_question(msg, lang) == Q[lang]


@pytest.mark.parametrize("msg, lang", [
    ("یه دکتر قلب خوب در تهرانپارس معرفی کن", "fa"), ("a pediatrician in Shiraz", "en"), ("نورولوژی در پردیس", "fa"),
    ("یه آزمایشگاه نزدیک نارمک پیدا کن", "fa"), ("find a pharmacy in Tehran", "en"), ("یه بیمارستان خوب در مشهد معرفی کن", "fa"),
    ("سلام خوبی؟", "fa"), ("I do not need a doctor", "en")])
def test_no_question_when_the_request_already_names_the_kind_or_is_not_a_doctor_request(msg, lang):
    assert ci.reason_question(msg, lang) is None


def test_sedis_own_question_is_recognised_in_any_language_and_typography():
    for lang in ("fa", "ar", "en"):
        assert ci.is_reason_question(Q[lang])
        assert ci.is_reason_question("  " + Q[lang].replace("؟", " ؟").replace("?", " ?") + "\n")
    assert not ci.is_reason_question("سلام، چه خبر؟") and not ci.is_reason_question(None)


PRIOR = "میخواهم یه دکتر خوب برام تو پردیس معرفی کنی"


@pytest.mark.parametrize("answer, spec", [
    ("نورولوژی", "مغز و اعصاب"), ("یه دندانپزشک", "دندانپزشکی"), ("قلبم درد می‌کنه", "قلب"), ("سردرد دارم", "مغز و اعصاب"),
    ("زانوم درد می‌کنه", "ارتوپدی"), ("پوستم خارش دارد", "پوست"), ("اضطراب دارم", "روانپزشکی"),
    ("نمی‌دونم", "پزشک عمومی"), ("فرقی نمی‌کنه", "پزشک عمومی"), ("یه چیزی‌ام هست ولی نمی‌دانم چیست", "پزشک عمومی")])
def test_the_answer_completes_the_original_request_with_the_right_specialty(answer, spec):
    done = ci.request_for_answer(PRIOR, Q["fa"], answer, "fa")
    assert done and done.startswith(PRIOR)
    req = cn.parse_care_nav_request(done, language="fa")
    assert req.specialty_or_service == spec and cn._places.normalize(req.city or "") == cn._places.normalize("پردیس") or req.specialty_or_service == spec
    assert req.entity is cn.CareNavEntity.SPECIALIST


@pytest.mark.parametrize("answer", ["نه ولش کن", "never mind", "درد قفسه سینه دارم و نفسم تنگ شده", "امروز هوا خوبه",
                                    "این یک پاسخ خیلی طولانی است " * 8])
def test_other_replies_are_not_swallowed_into_the_doctor_request(answer):
    assert ci.request_for_answer(PRIOR, Q["fa"], answer, "fa") is None


def test_the_answer_is_used_only_right_after_sedis_question():
    assert ci.request_for_answer(PRIOR, "سلام، چه خبر؟", "نورولوژی", "fa") is None
    assert ci.request_for_answer(None, Q["fa"], "نورولوژی", "fa") is None
    assert ci.request_for_answer(PRIOR, None, "نورولوژی", "fa") is None


def test_a_complete_doctor_request_as_the_answer_is_left_alone():
    assert ci.request_for_answer(PRIOR, Q["fa"], "یه دکتر قلب در شیراز می‌خوام", "fa") is None


def test_never_raises():
    assert ci.request_for_answer(object(), object(), object(), "fa") is None
    assert ci.reason_question(None, "fa") is None


# ---- through the orchestrator (the real chat path) --------------------------------------------------------------------
def _orch(monkeypatch, last_row=None, seen=None):
    from unittest.mock import MagicMock

    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator

    db = MagicMock()
    if last_row is not None:
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = last_row

    def search(db_, **k):
        if seen is not None:
            seen.append(k.get("specialty"))
        return []

    monkeypatch.setattr(cn._governed_directory, "search_doctors", search)
    called = {"gen": False}

    def gen(*a, **k):
        called["gen"] = True
        return {"message": "SHOULD NOT APPEAR", "detected_name": None}

    return IntelligenceOrchestrator(db=db, legacy_generator=gen, structured_mode=False), called


def test_the_chat_asks_the_reason_first_and_never_lists_random_doctors(monkeypatch):
    seen = []
    orch, called = _orch(monkeypatch, seen=seen)
    out = orch.process(authenticated_user_id=42, message="میخواهم یه دکتر خوب برام تو پردیس معرفی کنی", language="fa")
    assert out.message.strip() == Q["fa"].strip() or ci.is_reason_question(out.message)
    assert called["gen"] is False and seen == [] and "CARE_NAVIGATION_REASON_ASKED" in out.reason_codes


def test_the_answer_runs_the_search_for_the_right_specialty(monkeypatch):
    from datetime import datetime
    from types import SimpleNamespace

    last = SimpleNamespace(user_message=PRIOR, sedi_response=Q["fa"], created_at=datetime.utcnow())
    seen = []
    orch, called = _orch(monkeypatch, last_row=last, seen=seen)
    out = orch.process(authenticated_user_id=42, message="سردرد دارم", language="fa")
    assert called["gen"] is False and "CARE_NAVIGATION_REASON_ASKED" not in out.reason_codes
    assert seen and "اعصاب" in (seen[0] or "")  # the neurology stem reached the directory search


def test_an_old_question_is_not_continued(monkeypatch):
    from datetime import datetime, timedelta
    from types import SimpleNamespace

    last = SimpleNamespace(user_message=PRIOR, sedi_response=Q["fa"], created_at=datetime.utcnow() - timedelta(hours=3))
    seen = []
    orch, _called = _orch(monkeypatch, last_row=last, seen=seen)
    orch.process(authenticated_user_id=42, message="سردرد دارم", language="fa")
    assert not any("اعصاب" in (x or "") for x in seen)


# ---- Codex review of PR 191 ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("answer", ["ناگهان چشم راستم تار شده", "my vision suddenly went black", "قفسه سینه‌ام درد می‌کند و نفسم تنگ شده",
                                    "خونریزی شدید دارم", "غش کردم"])
def test_p1_an_emergency_answer_is_never_turned_into_a_routine_search(answer):
    assert ci.request_for_answer(PRIOR, Q["fa"], answer, "fa") is None


@pytest.mark.parametrize("answer, spec, place", [("نورولوژی در شیراز", "مغز و اعصاب", "شیراز"), ("اورولوژی توی نارمک", "اورولوژی", "نارمک"),
                                                 ("سردرد دارم، توی کرج", "مغز و اعصاب", "کرج")])
def test_p2_a_place_named_in_the_answer_replaces_the_first_place(answer, spec, place):
    done = ci.request_for_answer(PRIOR, Q["fa"], answer, "fa")
    req = cn.parse_care_nav_request(done, language="fa")
    assert req.specialty_or_service == spec
    assert place in (req.city or "") or place in (req.area or "") or cn._places.normalize(place) in cn._places.normalize((req.area or "") + (req.city or ""))
    assert "پردیس" not in (done or "")


def test_p2_without_a_place_in_the_answer_the_first_place_is_kept():
    done = ci.request_for_answer(PRIOR, Q["fa"], "نورولوژی", "fa")
    assert done.startswith(PRIOR) and "پردیس" in done


# ---- Codex round 2 ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("answer", ["not sure why my vision suddenly went black", "نمی‌دانم چرا ناگهان چشمم سیاه شد", "I don't know, I fainted",
                                    "فرقی نمی‌کند، خونریزی شدید دارم"])
def test_p1_uncertainty_never_turns_an_emergency_into_a_general_practitioner_search(answer):
    assert ci.request_for_answer(PRIOR, Q["fa"], answer, "fa") is None


@pytest.mark.parametrize("answer, lang", [("pain in knee", "en"), ("pain in left knee", "en"), ("a rash in my arm", "en")])
def test_p2_anatomy_after_in_is_not_a_city(answer, lang):
    done = ci.request_for_answer("find a doctor in Tehran", Q["en"], answer, lang)
    assert done and done.startswith("find a doctor in Tehran") and " in knee" not in done and " in left" not in done


# ---- Codex round 3 ---------------------------------------------------------------------------------------------------------
def test_p2_the_general_practitioner_search_term_is_not_a_substring_of_general_surgery():
    from backend.app.services.i5 import specialty_lexicon as sl

    assert sl.governed_stem("پزشک عمومی") == "پزشک عمومی" and sl.governed_stem("پزشک عمومی") not in "جراحی عمومی"


@pytest.mark.parametrize("answer, spec", [("not skin, my knee hurts", "ارتوپدی"), ("نه پوست، زانوم درد می‌کند", "ارتوپدی"),
                                          ("no dentist, I have a headache", "مغز و اعصاب")])
def test_p2_a_rejected_specialty_is_not_chosen(answer, spec):
    done = ci.request_for_answer("find a doctor in Tehran", Q["en"], answer, "fa" if any("؀" <= c <= "ۿ" for c in answer) else "en")
    assert done and f"متخصص {spec}" in done


@pytest.mark.parametrize("answer", ["many thanks", "any news today?", "company policy", "هر کیلو چند است؟", "thanks a lot"])
def test_p2_unrelated_replies_are_not_read_as_dont_know(answer):
    assert ci.request_for_answer(PRIOR, Q["fa"], answer, "fa") is None


@pytest.mark.parametrize("answer", ["any doctor", "I don't know", "not sure", "anyone is fine", "mmm, no idea", "هر دکتری", "نمی‌دانم", "عمومی"])
def test_p2_real_dont_know_phrases_still_work(answer):
    done = ci.request_for_answer(PRIOR, Q["fa"], answer, "fa")
    assert done and "پزشک عمومی" in done

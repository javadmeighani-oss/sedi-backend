"""R-105 / R-106 step 1 (Javad 2026-11-19): the interaction engine.

 - up to THREE short questions per reply, for every conversation (R-105);
 - a place is CONFIRMED in dialogue, never silently inferred: «تهرانپارس» -> «منظورت منطقه‌ی تهرانپارس در شهر تهران است یا جای
   دیگری؟»; a city without a verified directory slug («پردیس») is confirmed too; a complete place is trusted (R-106);
 - the reason question and the place question travel TOGETHER in one message, and one answer can settle both.
DB-free (the directory search is stubbed); matrix: phrasing x place type x answer type x language.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app import sedi_copy
from backend.app.services.i5 import care_nav_interview as ci
from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.intelligence import grounding_guard as gg


# --- R-105: the cap ---------------------------------------------------------------------------------------------------------------------
def test_the_cap_is_three_for_every_conversation():
    assert gg.MAX_QUESTIONS_PER_REPLY == 3
    reply = "یک؟ دو؟ سه؟ چهار؟ پنج؟ و یک جمله‌ی خبری."
    out = gg.limit_questions(reply, gg.MAX_QUESTIONS_PER_REPLY)
    assert out.count("؟") == 3 and "جمله‌ی خبری" in out  # every statement is kept, only the questions beyond three go


def test_the_persona_allows_three_short_questions_in_all_languages():
    from backend.app.core.conversation import persona_policy_v1 as pp

    text = open(pp.__file__, encoding="utf-8").read()
    assert "at most one question per reply" not in text.lower()
    assert "THREE short questions" in text and "سه پرسش کوتاه" in text and "ثلاثة أسئلة قصيرة" in text


# --- R-106: place status --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,status",
    [
        ("یه دکتر قلب در تهرانپارس", "confirm"),            # a neighbourhood that only IMPLIES Tehran
        ("یه دکتر قلب در تهرانپارس تهران", "ok"),           # area AND city said by the user
        ("یه دکتر قلب در شهر تهران", "ok"),
        ("یه دکتر قلب در شیراز", "ok"),                      # a city with a verified directory slug
        ("یه دکتر خوب در پردیس", "confirm"),                 # a known city WITHOUT a verified slug: confirm
        ("یه دکتر خوب در شهر پردیس", "ok"),                  # «شهر X» is an explicit statement
        ("یه آزمایشگاه نزدیک منطقه ۸", "confirm"),
        ("یه دکتر قلب", "none"),
    ],
)
def test_place_status_matrix(text, status):
    assert ci.place_status(text)[0] == status


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_the_place_question_names_the_understood_place_and_has_one_marker(lang):
    msg = {"fa": "یه دکتر قلب در تهرانپارس", "ar": "ابحث لي عن طبيب قلب في تهرانپارس", "en": "find a heart doctor in تهرانپارس"}[lang]
    q = ci.place_question(msg, lang)
    assert q and ci.is_place_question(q) and "تهرانپارس" in q.replace(chr(0x200c), "") and "{" not in q
    assert q.count("؟") + q.count("?") == 1


def test_an_area_without_a_known_city_asks_for_the_city():
    # find_place knows the area only through the Tehran list; an unknown neighbourhood name is «none» (the existing location question)
    assert ci.place_question("یه دکتر قلب", "fa") is None


def test_a_complete_place_asks_nothing():
    assert ci.place_question("یه دکتر مغز و اعصاب در شیراز", "fa") is None
    assert ci.first_question("یه دکتر مغز و اعصاب در تهرانپارس تهران", "fa") is None


# --- the combined first question ------------------------------------------------------------------------------------------------------
def test_reason_and_place_travel_together_in_one_message():
    q = ci.first_question("میخواهم یه دکتر خوب برام تو پردیس معرفی کنی", "fa")
    assert ci.is_reason_question(q) and ci.is_place_question(q) and "پردیس" in q
    assert q.count("؟") == 2 <= gg.MAX_QUESTIONS_PER_REPLY


def test_only_the_missing_part_is_asked():
    only_place = ci.first_question("یه دکتر قلب در تهرانپارس", "fa")
    assert ci.is_place_question(only_place) and not ci.is_reason_question(only_place)
    only_reason = ci.first_question("یه دکتر خوب در شیراز", "fa")
    assert ci.is_reason_question(only_reason) and not ci.is_place_question(only_reason)
    assert ci.first_question("سلام، چطوری؟", "fa") is None


# --- the answers -------------------------------------------------------------------------------------------------------------------------
PRIOR = "میخواهم یه دکتر خوب برام تو پردیس معرفی کنی"
BOTH = ci.first_question(PRIOR, "fa")


@pytest.mark.parametrize("answer", ["قلبم درد می‌کند، بله شهر پردیس", "متخصص قلب، همان پردیس"])
def test_one_answer_can_settle_both(answer):
    done = ci.request_for_answer(PRIOR, BOTH, answer, "fa")
    assert done and "قلب" in done
    status, place = ci.place_status(done)
    assert status == "ok" and place.city == "پردیس"  # now an explicit «شهر پردیس»: no second question


def test_the_specialty_alone_keeps_the_place_open_for_the_next_question():
    done = ci.request_for_answer(PRIOR, BOTH, "متخصص قلب", "fa")
    assert done and "قلب" in done
    q = ci.first_question(done, "fa")
    assert q and ci.is_place_question(q) and not ci.is_reason_question(q)  # asked once more, only the place


def test_a_plain_yes_confirms_the_inferred_place():
    prior = "یه دکتر قلب در تهرانپارس"
    q = ci.first_question(prior, "fa")
    assert ci.is_place_question(q)
    done = ci.request_for_answer(prior, q, "بله", "fa")
    status, place = ci.place_status(done)
    assert status == "ok" and place.area.replace(chr(0x200c), "") == "تهرانپارس" and place.city == "تهران" and "قلب" in done


def test_a_different_place_replaces_the_unconfirmed_one():
    prior = "یه دکتر قلب در تهرانپارس"
    q = ci.first_question(prior, "fa")
    done = ci.request_for_answer(prior, q, "نه، در شیراز", "fa")
    status, place = ci.place_status(done)
    assert status == "ok" and place.city == "شیراز" and "تهرانپارس" not in done.replace(chr(0x200c), "") and "قلب" in done


@pytest.mark.parametrize("answer", ["", "ولش کن", "یه چیز نامربوط که هیچ ربطی ندارد و خیلی طولانی هم هست و ادامه دارد و ادامه دارد و ادامه دارد دارد دارد دارد دارد دارد"])
def test_unrelated_answers_keep_their_normal_handling(answer):
    assert ci.request_for_answer("یه دکتر قلب در تهرانپارس", ci.first_question("یه دکتر قلب در تهرانپارس", "fa"), answer, "fa") is None


# --- through the real orchestrator -----------------------------------------------------------------------------------------------------
def _orch(monkeypatch, last_row=None, seen=None):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    import backend.app.services.i6.consent_service as consent
    import backend.app.services.i7.retention as retention

    monkeypatch.setattr(consent, "has_permission", lambda *a, **k: True)
    monkeypatch.setattr(retention, "query_eligible_raw", lambda *a, **k: [last_row] if last_row is not None else [])

    def search(db_, **k):
        if seen is not None:
            seen.append((k.get("specialty"), k.get("city"), k.get("area")))
        return []

    monkeypatch.setattr(cn._governed_directory, "search_doctors", search)
    called = {"gen": False}

    def gen(*a, **k):
        called["gen"] = True
        return {"message": "SHOULD NOT APPEAR", "detected_name": None}

    return IntelligenceOrchestrator(db=MagicMock(), legacy_generator=gen, structured_mode=False), called


def test_orchestrator_asks_reason_and_place_together_and_searches_nothing(monkeypatch):
    seen = []
    orch, called = _orch(monkeypatch, seen=seen)
    out = orch.process(authenticated_user_id=42, message=PRIOR, language="fa")
    assert ci.is_reason_question(out.message) and ci.is_place_question(out.message) and seen == [] and called["gen"] is False


def test_orchestrator_the_confirmed_answer_runs_the_search_in_that_place(monkeypatch):
    last = SimpleNamespace(user_message=PRIOR, sedi_response=BOTH, created_at=datetime.utcnow())
    seen = []
    orch, called = _orch(monkeypatch, last_row=last, seen=seen)
    orch.process(authenticated_user_id=42, message="قلبم درد می‌کند، بله شهر پردیس", language="fa")
    assert called["gen"] is False and seen and "قلب" in (seen[0][0] or "")
    assert seen[0][1] == "پردیس"


# --- Codex round 1 on PR 194 ---------------------------------------------------------------------------------------------------------------
def _turn(user, reply):
    return SimpleNamespace(user_message=user, sedi_response=reply, created_at=datetime.utcnow())


def test_p1_the_pending_request_survives_a_partial_answer():
    """«متخصص قلب» settles only the specialty; the place question follows; the next «بله» must still know the specialty."""
    place_q = ci.first_question(ci.request_for_answer(PRIOR, BOTH, "متخصص قلب", "fa"), "fa")
    rows = [_turn("متخصص قلب", place_q), _turn(PRIOR, BOTH)]  # newest first
    done = ci.request_for_chain(rows, "بله", "fa")
    status, place = ci.place_status(done)
    assert done and "قلب" in done and status == "ok" and place.city == "پردیس"


def test_p1_a_single_question_chain_still_works():
    done = ci.request_for_chain([_turn(PRIOR, BOTH)], "قلبم درد می‌کند، بله شهر پردیس", "fa")
    assert done and "قلب" in done and ci.place_status(done)[0] == "ok"
    assert ci.request_for_chain([_turn("سلام", "سلام! چه خبر؟")], "بله", "fa") is None


def test_p1_through_the_orchestrator_two_partial_answers_reach_the_search(monkeypatch):
    place_q = ci.first_question(ci.request_for_answer(PRIOR, BOTH, "متخصص قلب", "fa"), "fa")
    import backend.app.services.i7.retention as retention

    seen = []
    orch, called = _orch(monkeypatch, seen=seen)
    monkeypatch.setattr(retention, "query_eligible_raw", lambda *a, **k: [_turn("متخصص قلب", place_q), _turn(PRIOR, BOTH)])
    orch.process(authenticated_user_id=42, message="بله", language="fa")
    assert called["gen"] is False and seen and "قلب" in (seen[0][0] or "") and seen[0][1] == "پردیس"


def test_p2_every_spelling_of_the_old_place_is_removed():
    prior = "یه دکتر قلب در سعادت آباد"  # spaced spelling; the canonical form is «سعادت‌آباد»
    q = ci.first_question(prior, "fa")
    done = ci.request_for_answer(prior, q, "نه، نارمک تهران", "fa")
    assert done and "سعادت" not in done and "نارمک" in done and "قلب" in done
    assert ci.place_status(done)[1].area.replace(chr(0x200c), "") == "نارمک"


def test_p2_a_complete_replacement_request_keeps_its_own_specialty():
    prior = "یه دکتر قلب در پردیس"
    q = ci.first_question(prior, "fa")
    assert ci.request_for_answer(prior, q, "یه دکتر پوست در شیراز معرفی کن", "fa") is None  # it is a request of its own


def test_p2_a_replacement_request_in_the_middle_becomes_the_new_chain_root():
    first_q = ci.first_question("یه دکتر قلب در پردیس", "fa")
    new_request = "یه دکتر پوست در کرمانشاه معرفی کن"
    second_q = ci.first_question(new_request, "fa")
    assert ci.is_place_question(second_q)
    rows = [_turn(new_request, second_q), _turn("یه دکتر قلب در پردیس", first_q)]
    done = ci.request_for_chain(rows, "بله", "fa")
    status, place = ci.place_status(done)
    assert done and "پوست" in done and "قلب" not in done and status == "ok" and place.city == "کرمانشاه"

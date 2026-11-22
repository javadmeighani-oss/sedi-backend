"""R-114 / R-115 (PR-A1): the doctor request is completed from MEMORY (problem, stored place, insistence), never re-asked.

Real session (in-memory SQLite, the harness of test_r108_care_loop_e2e). The first block replays the reviewed pilot chat (D-485).
"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.app import models, sedi_copy
from backend.app.services.care_navigation import symptom_triage
from backend.app.services.i5 import care_nav_interview as ci
from backend.app.services.i5 import care_nav_memory as mem
from backend.tests.test_r108_care_loop_e2e import _fixed_timezone, db, user  # noqa: F401  (real-session fixtures)

ISSUE = "درد سمت راست زیر قفسه سینه حدود یک سال"
JAW = "ورم و برجستگی زیر فک"
ASK_REASON = sedi_copy.t("care_nav.ask_reason", "fa")


def _fact(db, user, domain, key, value):
    from backend.app.services.i6.memory_writes import write_fact

    write_fact(db, user.id, domain, key, value, source="chat", provenance_class="USER_STATED", commit=True)


def _remember(db, user, issues=(ISSUE,), area="بومهن", city="تهران"):
    if issues:
        _fact(db, user, "medical", "health_concerns", list(issues))
    if area:
        _fact(db, user, "social", "home_area", area)
    if city:
        _fact(db, user, "social", "home_city", city)


def _turn(db, user, message, reply, minutes_ago=1):
    from datetime import timedelta

    from backend.app.core.conversation.memory import ConversationMemory

    row = ConversationMemory(db).save_conversation(user.id, message, reply, "fa")
    assert row is not None
    if minutes_ago:
        row.created_at = datetime.utcnow() - timedelta(minutes=minutes_ago)
        db.commit()


def _rows(db, user):
    from backend.app.services.i7.retention import query_eligible_raw

    return list(query_eligible_raw(db, user.id, limit=8) or [])


# --- the user's tone, any wording --------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "اما تو باید یه دکتر پیدا کنی", "تو باید پیدا کنی", "هر چی میخوای بده فقط الکی سوال نکن", "الکی سوال نکن", "مگه قبل بهت نگفتم", "قبلا گفتم سمت راست",
    "سوال نپرس", "بدون سوال معرفی کن", "I already told you", "don't ask me again", "just find one", "you need to find a doctor", "قلت لك سابقاً", "لا تسأل مرة أخرى",
])
def test_insistence_is_recognised_in_every_language(text):
    assert mem.says_proceed(text)


@pytest.mark.parametrize("text", ["سلام", "یه دکتر پیدا کن", "دکتر خوبی سراغ داری", "I need a doctor", "ابحث لي عن طبيب", "ممنون"])
def test_a_plain_request_is_not_insistence(text):
    assert not mem.says_proceed(text)


@pytest.mark.parametrize("text", ["شما هر جا بگی من میرم شهرش مهم نیست", "شهرش مهم نیست", "هر جا", "any city is fine", "the city doesn't matter", "المدينة غير مهمة"])
def test_any_place_is_recognised(text):
    assert mem.says_any_place(text)
    assert not mem.says_any_place("در تهران")


@pytest.mark.parametrize("text", ["همون مشکل سمت راست بدنم", "همان مشکل", "the same problem", "same issue as before"])
def test_a_reference_to_what_is_known_is_recognised(text):
    assert mem.refers_to_known(text) and not mem.refers_to_known("برام دکتر پیدا کن")


# --- completing a request from memory ------------------------------------------------------------------------------------------------------------------
def test_the_known_problem_and_place_complete_the_request(db, user):
    _remember(db, user)
    out = mem.complete_request(db, user.id, "برام یه دکتر پیدا کن", "fa", rows=_rows(db, user))
    assert out is not None
    assert out.text == "یه دکتر گوارش برام پیدا کن در بومهن تهران"
    assert sedi_copy.t("care_nav.memory.place_used", "fa", place="بومهن تهران") in out.notes
    assert "CARE_NAV_STORED_PLACE" in out.reason_codes


def test_two_problems_name_the_second_specialty_and_search_for_the_first(db, user):
    _remember(db, user, issues=(ISSUE, JAW))
    out = mem.complete_request(db, user.id, "اما تو باید یه دکتر پیدا کنی", "fa", rows=[])
    assert "گوارش" in out.text and "CARE_NAV_INSISTENCE_PROCEED" in out.reason_codes
    other = [n for n in out.notes if JAW in n]
    assert other and "گوش و حلق و بینی" in other[0] and "؟" not in other[0]


def test_the_problem_the_message_mentions_wins(db, user):
    _remember(db, user, issues=(ISSUE, JAW))
    out = mem.complete_request(db, user.id, "برای ورم زیر فک دکتر پیدا کن", "fa", rows=[])
    assert out is not None and "گوش و حلق و بینی" in out.text


def test_a_vague_answer_to_the_reason_question_means_the_known_problem(db, user):
    _remember(db, user)
    _turn(db, user, "برام یه دکتر پیدا کن", ASK_REASON)
    out = mem.complete_request(db, user.id, "همون مشکل سمت راست بدنم", "fa", rows=_rows(db, user))
    assert out is not None and "گوارش" in out.text and "بومهن تهران" in out.text


def test_without_a_known_problem_the_single_question_stays(db, user):
    assert mem.complete_request(db, user.id, "برام یه دکتر پیدا کن", "fa", rows=[]) is None
    _turn(db, user, "برام یه دکتر پیدا کن", ASK_REASON)
    assert mem.complete_request(db, user.id, "همون مشکل سمت راست بدنم", "fa", rows=_rows(db, user)) is None  # nothing to refer to


def test_insistence_without_any_memory_goes_to_a_general_practitioner(db, user):
    out = mem.complete_request(db, user.id, "الکی سوال نکن یه دکتر پیدا کن", "fa", rows=[])
    assert out is not None and "پزشک عمومی" in out.text


def test_the_recent_turns_can_supply_the_problem(db, user):
    _turn(db, user, "از دیروز زیر دنده راستم درد می‌کنه", "از کی شروع شد؟", minutes_ago=5)
    out = mem.complete_request(db, user.id, "برام یه دکتر پیدا کن", "fa", rows=_rows(db, user))  # memory-read consent is granted here
    assert out is not None and "گوارش" in out.text


def test_any_place_uses_the_stored_place_else_tehran_with_a_disclosure(db, user):
    _remember(db, user, area=None, city=None)
    _turn(db, user, "یه دکتر گوارش برام پیدا کن", sedi_copy.t("care_nav.ask_place_city", "fa", area="X"))
    out = mem.complete_request(db, user.id, "شهرش مهم نیست", "fa", rows=_rows(db, user))
    assert out is not None and out.text.endswith("در تهران")
    assert sedi_copy.t("care_nav.memory.place_default", "fa", city="تهران") in out.notes and "CARE_NAV_DEFAULT_CITY" in out.reason_codes


def test_a_named_specialty_gets_the_stored_place(db, user):
    _remember(db, user, issues=())
    out = mem.complete_request(db, user.id, "یه دکتر پوست پیدا کن", "fa", rows=[])
    assert out is not None and out.text == "یه دکتر پوست پیدا کن در بومهن تهران"
    assert mem.complete_request(db, user.id, "یه دکتر پوست در شیراز پیدا کن", "fa", rows=[]) is None  # a complete request of its own


def test_other_requests_and_emergencies_are_left_alone(db, user):
    _remember(db, user)
    assert mem.complete_request(db, user.id, "یه آزمایشگاه پیدا کن", "fa", rows=[]) is None
    assert mem.complete_request(db, user.id, "سلام حالت چطوره", "fa", rows=[]) is None
    assert mem.complete_request(db, user.id, "قفسه سینه‌ام خیلی شدید درد می‌کند دکتر پیدا کن", "fa", rows=[]) is None  # the safety path owns it


def test_without_memory_read_consent_nothing_is_read(db, user):
    from backend.app.services.i6 import consent_service as consent

    _remember(db, user)
    consent.revoke_memory_consent(db, user.id)
    assert mem.complete_request(db, user.id, "برام یه دکتر پیدا کن", "fa", rows=[]) is None


def test_the_flag_is_on_when_unset_and_off_when_written_false(monkeypatch):
    monkeypatch.delenv(mem.FLAG, raising=False)
    assert mem.enabled()
    for raw, expected in (("true", True), ("1", True), ("false", False), ("0", False), ("off", False)):
        monkeypatch.setenv(mem.FLAG, raw)
        assert mem.enabled() is expected


def test_the_kill_switch_restores_the_old_flow(db, user, monkeypatch):
    _remember(db, user)
    monkeypatch.setenv(mem.FLAG, "false")
    assert mem.complete_request(db, user.id, "برام یه دکتر پیدا کن", "fa", rows=[]) is None


@pytest.mark.parametrize("lang,message,expected_prefix", [
    ("en", "I need you to find me a doctor", "Please find me a doctor"),
    ("ar", "ابحث لي عن طبيب", "ابحث لي عن طبيب"),
])
def test_other_languages_build_their_own_request(db, user, lang, message, expected_prefix):
    _remember(db, user)
    out = mem.complete_request(db, user.id, message, lang, rows=[])
    assert out is not None and out.text.startswith(expected_prefix)
    assert all("{" not in n for n in out.notes)


def test_every_new_catalog_text_exists_in_three_languages():
    for key, kw in (("care_nav.memory.place_used", {"place": "P"}), ("care_nav.memory.place_default", {"city": "C"}),
                    ("care_nav.memory.other_issue", {"issue": "I", "specialty": "S"})):
        for lang in ("fa", "ar", "en"):
            text = sedi_copy.t(key, lang, **kw)
            assert text and "{" not in text


# --- the triage the flow relies on (DEBT-078 + the pilot's body areas) --------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,lang", [
    ("I have severe chest pain", "en"), ("crushing chest pain", "en"), ("درد شدید قفسه سینه دارم", "fa"), ("قفسه سینه‌ام خیلی شدید درد می‌کند", "fa"), ("ألم شديد في الصدر", "ar"),
])
def test_severe_chest_pain_is_an_emergency_in_every_language(text, lang):
    result = symptom_triage.triage(text, lang)
    assert result.red_flag and result.urgency == "emergency"


@pytest.mark.parametrize("text", ["درد قفسه سینه دارم", "chest pain when I run", "قلبم درد می‌کند"])
def test_ordinary_chest_pain_is_still_soon_not_an_emergency(text):
    result = symptom_triage.triage(text, "fa")
    assert not result.red_flag and result.urgency == "soon" and "قلب" in result.specialties


@pytest.mark.parametrize("text,lang", [
    (ISSUE, "fa"), ("درد زیر دنده راست", "fa"), ("pain under right ribs for a year", "en"), ("درد بالای شکم سمت راست", "fa"),
])
def test_pain_under_the_ribs_is_a_digestive_complaint_not_a_heart_one(text, lang):
    result = symptom_triage.triage(text, lang)
    assert not result.red_flag and result.specialties[0] == "گوارش" and "قلب" not in result.specialties


@pytest.mark.parametrize("text,lang", [(JAW, "fa"), ("I have a lump under my jaw", "en"), ("I have a swollen gland in my neck", "en")])
def test_a_swelling_under_the_jaw_goes_to_ear_nose_throat(text, lang):
    assert symptom_triage.triage(text, lang).specialties[0] == "گوش و حلق و بینی"


# --- the care journey starts without the interview -----------------------------------------------------------------------------------------------------------
def test_the_follow_up_chain_is_tracked_without_asking_questions(db, user):
    from backend.app.services import care_state as cs
    from backend.app.services.care_journey import journey as j

    assert j.track(db, user.id, "یه دکتر گوارش برام پیدا کن در بومهن تهران", "fa") is True
    assert cs.get_care_state(db, user.id).has_open_journey
    assert j.track(db, user.id, "یه دکتر گوارش برام پیدا کن", "fa") is True  # an open journey is not duplicated
    open_chains = db.query(models.CareFollowUpTask).count()
    assert open_chains >= 1


# --- the reviewed pilot chat, replayed through the real orchestrator (D-485) ----------------------------------------------------------------------------------
@pytest.fixture
def orch(db, monkeypatch):
    from backend.app.services.i5 import care_navigation_directory as cn
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator

    seen = []

    def fake_resolve(db_, message, *, language, authenticated_user_id=None, **k):
        seen.append(message)
        return SimpleNamespace(user_message=f"DIRECTORY<{message}>", status=cn.STATUS_VERIFIED)

    monkeypatch.setattr(cn, "resolve_care_navigation", fake_resolve)
    o = IntelligenceOrchestrator(db=db, legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)
    o.seen = seen
    return o


def _say_to(orch, user, text):
    return orch.process(authenticated_user_id=user.id, message=text, language="fa").message


def test_replay_the_doctor_request_is_answered_at_once_and_never_re_asked(db, user, orch):
    from backend.app.services import care_state as cs

    _remember(db, user, issues=(ISSUE, JAW))
    first = _say_to(orch, user, "برام یه دکتر پیدا کن")
    assert "DIRECTORY<" in first and ASK_REASON not in first                       # no «برای چه مشکلی» although no specialty was named
    assert "گوارش" in orch.seen[-1] and "بومهن" in orch.seen[-1]                   # the known problem + the stored place reached the directory
    assert sedi_copy.t("care_nav.memory.place_used", "fa", place="بومهن تهران") in first
    assert sedi_copy.t("care_nav.memory.other_issue", "fa", issue=JAW, specialty="گوش و حلق و بینی") in first
    second = _say_to(orch, user, "اما تو باید یه دکتر پیدا کنی")
    assert "DIRECTORY<" in second and ASK_REASON not in second
    assert cs.get_care_state(db, user.id).has_open_journey                        # the care journey follows (R-109) without an interview


def test_replay_without_memory_the_old_single_question_is_kept(db, user, orch):
    first = _say_to(orch, user, "برام یه دکتر پیدا کن")
    assert ASK_REASON in first and not orch.seen


def test_a_question_the_model_wrote_in_a_doctor_thread_is_pending_too(db, user):
    """The pilot chat: the model asked «در کدام شهر یا محدوده؟» (not the catalog question) and the user answered «شهرش مهم نیست»."""
    _remember(db, user, area=None, city=None)
    _turn(db, user, "برام یه دکتر پیدا کن", "برای پیدا کردن پزشک مشخص، در کدام شهر یا محدوده می‌خواهی ویزیت شوی؟", minutes_ago=2)
    out = mem.complete_request(db, user.id, "شما هر جا بگی من میرم شهرش مهم نیست", "fa", rows=_rows(db, user))
    assert out is not None and "گوارش" in out.text and out.text.endswith("در تهران")
    again = mem.complete_request(db, user.id, "قبلا گفتم سمت راست زیر قفسه سینه", "fa", rows=_rows(db, user))
    assert again is not None and "گوارش" in again.text


def test_the_model_question_outside_a_doctor_thread_is_not_pending(db, user):
    _remember(db, user)
    _turn(db, user, "سلام", "امروز چطوری؟", minutes_ago=2)
    assert mem.complete_request(db, user.id, "قبلا گفتم", "fa", rows=_rows(db, user)) is None

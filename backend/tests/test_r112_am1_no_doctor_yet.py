"""R-112 am.1 (Javad 2026-11-21: «اگر کاربر به صدی بگوید دکتر نرفته‌ام جواب صدی چیست؟»): DEBT-099 / 100 / 101.

Before: no hint for «I have not seen a doctor» (the model might scold or answer vaguely); «ریزش مو» mapped to no specialty and no triage area;
the «yes» to Sedi's specialist offer lost the specialty and the directory flow asked the reason AGAIN.
Real session (in-memory SQLite) for the end-to-end cases; the matchers are pure.
"""
from unittest.mock import MagicMock

import pytest

from backend.app import models, sedi_copy
from backend.app.services.care_navigation import symptom_triage
from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import specialty_lexicon as sl
from backend.app.services.interview import guide
from backend.app.services.intelligence.specialist_offer import specialist_request_for_reply as offer_reply
from backend.tests.test_r103_pill_time_change import db, user  # noqa: F401  (real-session fixtures)
from backend.tests.test_r103_pill_time_change import _pinned, _say  # noqa: F401


# --- DEBT-100: the vocabulary ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["ریزش مو", "تساقط مو", "طاسی", "دکتر مو", "متخصص مو", "hair loss", "alopecia", "hair fall", "تساقط الشعر"])
def test_hair_words_name_the_dermatology_specialty(text):
    assert sl.find_specialty(text) == "پوست"


@pytest.mark.parametrize(
    "text,lang",
    [("ریزش مو دارم", "fa"), ("تساقط مو دارم", "fa"), ("طاسی سر دارم و نگرانم", "fa"), ("موهام خیلی می‌ریزه", "fa"), ("I have hair loss and I am worried", "en")],
)
def test_a_hair_complaint_reaches_the_skin_area(text, lang):
    result = symptom_triage.triage(text, lang)
    assert "skin" in result.areas and "پوست" in result.specialties and not result.red_flag and result.urgency == "routine"


@pytest.mark.parametrize("text", ["موضوع مهمی دارم", "موقع خواب", "مومیایی", "یک موسیقی خوب", "the movie was good"])
def test_the_word_for_hair_never_matches_inside_other_words(text):
    assert sl.find_specialty(text) is None and not symptom_triage.triage(text, "fa").areas


# --- DEBT-099: the «no doctor yet» detector ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "message,expected",
    [
        ("دکتر نرفتم", True), ("هنوز دکتر نرفتم", True), ("هنوز پیش دکتر نرفتم", True), ("نرفتم دکتر", True), ("پزشک نرفته‌ام", True),
        ("تا حالا به متخصص نرفتم", True), ("دکتر ندیدم", True),
        ("I haven't seen a doctor yet", True), ("not seen a doctor", True), ("I did not see a doctor", True), ("no doctor yet", True),
        ("لم أذهب إلى الطبيب", True), ("لم أزر الطبيب", True),
        ("دکتر رفتم", False), ("دیروز پیش دکتر بودم", False), ("دکترم گفت آزمایش بدم", False), ("I saw a doctor yesterday", False), ("", False),
    ],
)
def test_the_no_doctor_yet_matrix(message, expected):
    assert guide.says_no_doctor_yet(message) is expected


def _hair_issue(db, user):
    from backend.app.services.candidate_promotion_service import _merge_list_value
    from backend.app.services.i6.memory_writes import write_fact

    write_fact(db, user.id, "medical", "health_concerns", _merge_list_value(db, user.id, "medical", "health_concerns", "ریزش مو"),
               source="chat", provenance_class="USER_STATED", commit=True)


def test_the_hint_is_first_non_judging_and_names_the_specialty(db, user):
    _hair_issue(db, user)
    hint = guide.hint_for_turn(db, user.id, "دکتر نرفتم", "fa")
    assert hint.startswith(guide.NO_DOCTOR_PREFIX)
    assert "for «ریزش مو»" in hint and "پوست" in hint                       # the problem and its specialty come from memory
    for needle in ("Do NOT judge", "ONE line on why a visit helps", "ferritin", "ONE direct question", "no softeners",
                   "practical non-drug steps", "Do not ask the reason or the doctor question again", "never diagnose"):
        assert needle in hint, needle


def test_without_a_known_problem_the_offer_is_general_not_invented(db, user):
    hint = guide.hint_for_turn(db, user.id, "دکتر نرفتم", "fa")
    assert hint.startswith(guide.NO_DOCTOR_PREFIX) and "the right specialist" in hint and "for «" not in hint


def test_the_specialty_can_come_from_the_recent_conversation(db, user):
    _say(db, user, "ریزش مو دارم", "از کی شروع شد؟")
    hint = guide.hint_for_turn(db, user.id, "دکتر نرفتم", "fa")
    assert "پوست" in hint


def test_other_messages_and_emergencies_get_no_no_doctor_hint(db, user):
    assert guide.no_doctor_hint(db, user.id, "سلام", "fa") is None
    assert guide.hint_for_turn(db, user.id, "دکتر نرفتم و نفسم بند آمده و قفسه سینه‌ام درد می‌کند", "fa") is None  # the safety path owns it


def test_the_hint_never_breaks_the_guide(db, user, monkeypatch):
    monkeypatch.setattr(guide, "says_no_doctor_yet", lambda m: (_ for _ in ()).throw(RuntimeError("down")))
    assert guide.no_doctor_hint(db, user.id, "دکتر نرفتم", "fa") is None


# --- DEBT-101: «yes» keeps the specialty ---------------------------------------------------------------------------------------------------------------
OFFER = "برای ریزش مو یک آزمایش ساده خیلی کمک می‌کند. می‌خوای یه متخصص پوست و مو در منطقه‌ات پیدا کنم؟"


def test_a_yes_to_an_offer_that_names_the_specialty_asks_for_that_specialty():
    request = offer_reply(OFFER, "آره", "fa")
    assert request == "یه دکتر پوست برام پیدا کن"
    assert cn.is_care_navigation_query(request) and sl.find_specialty(request) == "پوست"  # the directory flow understands it, reason included


def test_a_yes_to_a_nameless_offer_uses_the_conversation():
    assert offer_reply("می‌خوای یه متخصص پیدا کنم؟", "آره", "fa", context=["سلام", "ریزش مو دارم"]) == "یه دکتر پوست برام پیدا کن"
    assert offer_reply("Do you want me to find a specialist?", "yes", "en", context=["I have hair loss"]) == "Please find me a doctor پوست"
    assert offer_reply("می‌خوای یه متخصص پیدا کنم؟", "آره", "fa", context=["سلام"]) == "یه متخصص مناسب برام پیدا کن"  # nothing known: exactly as before


def test_a_psychologist_offer_is_unchanged_and_no_yes_no_request():
    assert offer_reply("می‌خوای یه روانشناس پیدا کنم؟", "آره", "fa", context=["ریزش مو دارم"]) == "یک متخصص روانشناسی برام پیدا کن"
    assert offer_reply(OFFER, "نه ممنون", "fa") is None and offer_reply("یه جواب معمولی", "آره", "fa") is None


def test_the_whole_conversation_does_not_ask_the_reason_again(db, user, monkeypatch):
    """Turn 1 «دکتر نرفتم» (hint) -> Sedi's offer -> «آره»: the directory flow starts from the named specialty and asks the PLACE, not the reason."""
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    import backend.app.services.i6.consent_service as consent

    _say(db, user, "ریزش مو دارم", "از کی شروع شد؟")
    _say(db, user, "دکتر نرفتم", OFFER)
    monkeypatch.setattr(cn._governed_directory, "search_doctors", lambda db_, **k: [])
    orch = IntelligenceOrchestrator(db=db, legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)
    out = orch.process(authenticated_user_id=user.id, message="آره", language="fa")
    from backend.app.services.care_journey import journey

    assert out.message != "GEN" and "برای چه مشکل یا نیازی" not in out.message          # the reason is NOT asked again
    assert journey.is_interview_reply(out.message) or "کجا" in out.message or "شهر" in out.message  # the care journey intake (or the place question) follows


# --- Codex round 1 on PR 208 ------------------------------------------------------------------------------------------------------------------
def test_p1_without_memory_read_consent_past_conversations_are_not_read(db, user):
    from backend.app.services.i6 import consent_service as consent

    _say(db, user, "ریزش مو دارم", "از کی شروع شد؟")
    consent.revoke_memory_consent(db, user.id)
    hint = guide.hint_for_turn(db, user.id, "دکتر نرفتم", "fa")
    assert hint.startswith(guide.NO_DOCTOR_PREFIX) and "پوست" not in hint and "the right specialist" in hint  # generic: nothing inferred


def test_p2_the_specialty_of_the_offer_beats_a_complaint_word_in_the_same_reply():
    reply = "برای ریزش مو شاید بررسی هورمون لازم باشد. می‌خوای یه متخصص غدد پیدا کنم؟"
    assert offer_reply(reply, "آره", "fa") == "یه دکتر غدد برام پیدا کن"


def test_p1_a_yes_to_an_offer_does_not_read_past_conversation_without_consent(db, user):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.app.services.i6 import consent_service as consent

    _say(db, user, "ریزش مو دارم", "از کی شروع شد؟")
    _say(db, user, "دکتر نرفتم", "می‌خوای یه متخصص پیدا کنم؟")
    orch = IntelligenceOrchestrator(db=db, legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)
    with_consent = orch._continue_specialist_offer(None, user.id, "آره", "fa")
    assert with_consent == "یه دکتر پوست برام پیدا کن"          # permitted history: the specialty of the complaint is carried
    consent.revoke_memory_consent(db, user.id)
    assert orch._continue_specialist_offer(None, user.id, "آره", "fa") == "آره"  # revoked: nothing is read, the message stays as it is


# --- Codex round 3 on PR 208 ------------------------------------------------------------------------------------------------------------------
def test_p2_an_explicitly_named_specialty_beats_a_hair_complaint_word():
    assert sl.find_specialty("یه متخصص غدد برای ریزش مو پیدا کن") == "غدد"
    assert sl.find_specialty("دکتر زنان برای ریزش مو بعد از زایمان") == "زنان"
    assert sl.find_specialty("ریزش مو دارم") == "پوست" and sl.find_specialty("hair loss") == "پوست"   # no specialty named: the complaint decides
    assert sl.find_specialty("موضوع مهمی دارم") is None


def test_p2_the_current_complaint_beats_a_stored_one(db, user):
    _hair_issue(db, user)
    stomach = guide.hint_for_turn(db, user.id, "معده درد دارم و دکتر نرفتم", "fa")
    assert stomach.startswith(guide.NO_DOCTOR_PREFIX) and "for «ریزش مو»" not in stomach and "گوارش" in stomach
    stored = guide.hint_for_turn(db, user.id, "دکتر نرفتم", "fa")
    assert "for «ریزش مو»" in stored and "پوست" in stored                     # a bare «دکتر نرفتم» still uses what memory knows

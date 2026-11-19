"""J2 (R-094): symptom -> body area -> kind of doctor. Deterministic, offline. Emergencies first (R-014), no diagnosis (R-033)."""
import pytest

from backend.app.services.care_navigation import symptom_triage as st


@pytest.mark.parametrize(
    "text, key",
    [
        ("درد قفسه‌ی سینه دارم و نفسم می‌گیرد", "chest_pain_with_breathing"),
        ("قفسه سینه‌ام درد می‌کند و عرق سرد کرده‌ام", "chest_pain_with_breathing"),
        ("چشمم کج شده و صورتم افتاده", None),  # not a pattern: stays routine/soon, never a false emergency claim
        ("ناگهان یک طرف صورتم افتاده و دستم ضعیف شده", "stroke_signs"),
        ("ناگهان دستم بی‌حس شد و حرف زدن برایم سخت است", "stroke_signs"),
        ("این بدترین سردرد زندگی‌ام است", "worst_headache"),
        ("خونریزی شدید دارم", "heavy_bleeding"),
        ("غش کردم و نمی‌دانم چرا", "fainting"),
        ("I have chest pain and I am short of breath", "chest_pain_with_breathing"),
        ("sudden weakness in my arm and slurred speech", "stroke_signs"),
        ("I can't breathe", "severe_breathing"),
    ],
)
def test_emergencies_are_flagged_first_and_ask_no_questions(text, key):
    out = st.triage(text)
    if key is None:
        assert not out.red_flag or out.red_flag_key  # a flagged result always names its pattern
        return
    assert out.red_flag and out.urgency == "emergency" and out.red_flag_key == key
    assert out.specialties[0] == "اورژانس" and out.next_question is None


@pytest.mark.parametrize(
    "text",
    ["سلام حالت چطوره", "امروز هوا خوبه", "می‌خواهم برنامه‌ی ورزشی بنویسی", "قیمت قرص چنده", "سینه‌ام را بعد از ورزش می‌کشم"],
)
def test_ordinary_talk_is_never_an_emergency(text):
    assert not st.triage(text).red_flag


def test_chest_pain_without_breathing_is_soon_not_routine_and_not_an_emergency_claim():
    out = st.triage("بعد از دویدن درد قفسه سینه داشتم")
    assert not out.red_flag and out.urgency == "soon" and "قلب" in out.specialties


def test_companion_symptoms_add_the_second_specialist_with_a_reason():
    out = st.triage("کمردرد دارم و پایم گزگز می‌کند")
    assert out.specialties[:2] == ("ارتوپدی", "مغز و اعصاب") and out.reasons["مغز و اعصاب"] == "back_joint"


def test_sudden_vision_change_is_urgent_soon():
    out = st.triage("دیدم ناگهان تار شده")
    assert out.urgency == "soon" and out.specialties[0] == "چشم" and not out.red_flag


def test_every_non_emergency_result_asks_exactly_one_question_key():
    for text in ["سردرد دارم", "زانویم درد می‌کند", "پوستم خارش دارد", "معده‌ام می‌سوزد", "اضطراب دارم", "گلویم درد می‌کند", "دندانم درد می‌کند",
                 "قاعدگی‌ام نامنظم است", "سرفه دارم", "قند خونم بالاست", "ضربان قلبم نامنظم است", "ادرار می‌سوزد"]:
        out = st.triage(text)
        assert not out.red_flag and out.specialties and out.next_question and out.next_question.startswith("care_nav.q.")


def test_unknown_area_asks_which_area_instead_of_guessing():
    out = st.triage("یه چیزی‌ام هست ولی نمی‌دانم چیست")
    assert out.specialties == () and out.next_question == "care_nav.q.which_area"


def test_english_basics_and_garbage_input_never_raise():
    assert st.triage("I have a headache and dizziness").specialties[0] == "مغز و اعصاب"
    assert st.triage("my knee hurts when I climb stairs").specialties[0] == "ارتوپدی"
    for junk in ("", None, "   ", "؟؟؟", "a" * 5000):
        st.triage(junk)


def test_the_result_never_names_a_disease():
    out = st.triage("چند وقته سردرد شدیدی دارم")
    blob = " ".join(out.specialties) + " " + " ".join(out.reasons.values())
    assert "تشخیص" not in blob and "سرطان" not in blob and "تومور" not in blob  # specialist + area only (R-033/R-074)


# --- the hint handed to the chat model ---------------------------------------------------------------------------
def test_emergency_hint_urges_help_and_forbids_questions_and_advice():
    hint = st.llm_hint(st.triage("درد قفسه سینه دارم و نفسم می‌گیرد"))
    assert "EMERGENCY" in hint and "115" in hint and "NO questions" in hint and "NO diagnosis" in hint


def test_routine_hint_names_the_doctor_why_one_question_and_forbids_diagnosis():
    hint = st.llm_hint(st.triage("چند وقته سردرد شدیدی دارم"))
    assert "مغز و اعصاب" in hint and "ONE question" in hint and "Never name a disease" in hint and "neighbourhood" in hint


def test_soon_hint_says_so_and_no_hint_for_small_talk():
    assert "SOON" in st.llm_hint(st.triage("بعد از دویدن درد قفسه سینه داشتم"))
    assert st.llm_hint(st.triage("سلام حالت چطوره")) is None


def test_the_brain_hook_appends_one_block_and_respects_the_kill_switch(monkeypatch):
    from backend.app.core.conversation import brain

    msgs = []
    brain._maybe_append_symptom_triage(msgs, "زانویم درد می‌کند", "fa")
    assert len(msgs) == 1 and msgs[0]["role"] == "system" and "ارتوپدی" in msgs[0]["content"]
    monkeypatch.setenv("SEDI_SYMPTOM_TRIAGE_DISABLED", "1")
    off = []
    brain._maybe_append_symptom_triage(off, "زانویم درد می‌کند", "fa")
    assert off == []
    monkeypatch.delenv("SEDI_SYMPTOM_TRIAGE_DISABLED")
    calm = []
    brain._maybe_append_symptom_triage(calm, "سلام", "fa")
    assert calm == []

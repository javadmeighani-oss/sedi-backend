"""F1/F2/F3 (D-402): regional help line on I4 terminal replies, 72 h support window, anonymous crisis counter."""
import logging
from types import SimpleNamespace

import pytest

from backend.app.services.care_navigation import crisis_support as cs
from backend.app.services.intelligence import emergency_lines as el
from backend.app.services.intelligence.contracts import RiskDomain, RiskLevel
from backend.app.services.intelligence.safety_risk import assess_safety_risk, build_safety_response


def _reply(text, lang, user_id=None):
    a = assess_safety_risk(message=text, language=lang)
    base = build_safety_response(a).localized_message
    return a, base, el.finalize_terminal_message(base, a, None, user_id)


def test_persian_self_harm_reply_gets_the_real_numbers_in_persian_digits():
    a, base, out = _reply("میخوام خودمو بکشم", "fa")
    assert a.domain is RiskDomain.SELF_HARM_CRISIS and out.startswith(base)
    assert "۱۱۵" in out and "۱۲۳" in out and "115" not in out


def test_english_reply_without_a_verified_region_stays_neutral():
    a, base, out = _reply("I want to die", "en")
    assert out == base  # no phone/timezone known and not Persian: never a guessed number


def test_arabic_reply_without_a_region_stays_neutral():
    a, base, out = _reply("أريد أن أموت", "ar")
    assert out == base


def test_medical_emergency_gets_the_emergency_number_only_when_the_level_is_emergency():
    a, base, out = _reply("درد قفسه سینه دارم و نفسم نمیاد", "fa")
    if a.level is RiskLevel.EMERGENCY:
        assert "۱۱۵" in out and "۱۲۳" not in out
    else:
        assert out == base


def test_the_i4_templates_themselves_stay_country_neutral():
    from backend.app.services.intelligence.safety_risk import list_template_strings

    assert "115" not in "".join(list_template_strings()) and "۱۱۵" not in "".join(list_template_strings())


def test_finalize_never_raises_and_returns_the_message_unchanged_on_failure():
    assert el.finalize_terminal_message("hello", object(), None, None) == "hello"


def test_phone_prefix_or_timezone_selects_iran_and_an_english_user_elsewhere_gets_none():
    class Q:
        def __init__(self, row): self.row = row
        def filter(self, *a, **k): return self
        def first(self): return self.row

    class DB:
        def __init__(self, phone, tz):
            self.phone, self.tz = phone, tz
        def query(self, model):
            name = getattr(model, "__name__", "")
            return Q(SimpleNamespace(phone=self.phone) if name == "User" else SimpleNamespace(timezone=self.tz))

    assert el.region_for(DB("+989121234567", None), 1, "en") == "IR"
    assert el.region_for(DB(None, "Asia/Tehran"), 1, "en") == "IR"
    assert el.region_for(DB("+14155550123", "America/New_York"), 1, "en") is None
    assert el.region_for(None, None, "fa") == "IR"


def test_the_anonymous_counter_logs_level_and_language_but_no_user_or_text(caplog):
    caplog.set_level(logging.WARNING)
    text = "میخوام خودمو بکشم"
    a = assess_safety_risk(message=text, language="fa")
    el.finalize_terminal_message("x", a, None, 4242)
    lines = [r.getMessage() for r in caplog.records if "I4_SELF_HARM_EVENT" in r.getMessage()]
    assert len(lines) == 1 and "lang=fa" in lines[0]
    assert "4242" not in lines[0] and "خودمو" not in lines[0]


def test_the_support_window_is_72_hours():
    assert cs.LOOKBACK.total_seconds() == 72 * 3600


# --- Codex review of PR 187 (R-069): three P1, two P2 -----------------------------------------------------------------
@pytest.mark.parametrize("text, lang", [
    ("I took too many pills to kill myself", "en"), ("می‌خوام خودمو بکشم", "fa"), ("أريد أن أنهي حياتي", "ar")])
def test_p1_the_emergency_self_harm_reply_urges_help_now_and_not_staying_alone(text, lang):
    a = assess_safety_risk(message=text, language=lang)
    if a.level is not RiskLevel.EMERGENCY or a.domain is not RiskDomain.SELF_HARM_CRISIS:
        pytest.skip("not an emergency-level self-harm phrase for this language")
    reply = build_safety_response(a).localized_message
    assert "no rush" not in reply and "عجله" not in reply
    marker = {"en": ("right now", "do not stay alone"), "fa": ("همین حالا", "تنها نمان"), "ar": ("الآن", "ولا تبقَ وحدك")}[lang]
    assert all(m in reply for m in marker)
    assert reply.count("?") + reply.count("؟") <= 1  # still ONE open invitation, not an interrogation (R-099)


@pytest.mark.parametrize("text, lang", [
    ("I have a severe headache and life is not worth living", "en"),
    ("سردرد شدید دارم و دیگه نمی‌خوام زنده باشم", "fa")])
def test_p1_self_harm_is_detected_even_when_a_medical_rule_wins(text, lang):
    assert cs.is_self_harm_text(text, lang)


def test_p1_a_denied_self_harm_phrase_is_still_not_self_harm_talk():
    assert not cs.is_self_harm_text("I do not want to kill myself", "en")


def test_p1_the_router_records_the_terminal_turn_before_returning(monkeypatch):
    import backend.app.routers.interact as inter

    saved = []

    class Mem:
        def __init__(self, db): pass
        def save_conversation(self, uid, msg, reply, lang, **kw): saved.append((uid, msg, reply, lang))

    import backend.app.core.conversation.memory as memmod
    monkeypatch.setattr(memmod, "ConversationMemory", Mem)
    inter._record_terminal_turn(object(), 7, "I want to die", " reply ", "en")
    assert saved == [(7, "I want to die", "reply", "en")]


def test_p1_recording_a_terminal_turn_never_breaks_the_reply(monkeypatch):
    import backend.app.routers.interact as inter
    import backend.app.core.conversation.memory as memmod

    class Boom:
        def __init__(self, db): raise RuntimeError("db down")

    monkeypatch.setattr(memmod, "ConversationMemory", Boom)
    inter._record_terminal_turn(SimpleNamespace(rollback=lambda: None), 7, "x", "y", "en")  # must not raise


@pytest.mark.parametrize("text", ["I never fainted or passed out", "What does heavy bleeding mean?", "هرگز غش نکردم", "خونریزی شدید ندارم"])
def test_p2_denied_or_informational_physical_emergencies_are_not_emergencies(text):
    from backend.app.services.care_navigation.symptom_triage import triage

    assert triage(text, "fa" if any("؀" <= c <= "ۿ" for c in text) else "en").red_flag_key is None


@pytest.mark.parametrize("text", ["I fainted and I never had this before", "I never fainted before but now I passed out",
                                  "heavy bleeding that won't stop", "غش کردم"])
def test_p2_an_independent_real_emergency_is_never_hidden_by_a_denial_elsewhere(text):
    from backend.app.services.care_navigation.symptom_triage import triage

    assert triage(text, "fa" if any("؀" <= c <= "ۿ" for c in text) else "en").red_flag is True


def test_p2_the_word_see_in_ordinary_persian_is_not_an_ent_complaint():
    from backend.app.services.care_navigation.symptom_triage import triage

    assert triage("ببینیم فردا چه می‌شود", "fa").specialties == ()
    assert triage("بینی‌ام گرفته و آبریزش دارم", "fa").specialties == ("گوش و حلق و بینی",)


# --- second Codex round on PR 187 -------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, lang", [
    ("My vision suddenly went black, what does that mean?", "en"),
    ("چشمم ناگهان سیاه شده، یعنی چه؟", "fa"),
    ("I fainted, what does that mean?", "en")])
def test_p1_asking_what_a_reported_symptom_means_is_still_an_emergency(text, lang):
    from backend.app.services.care_navigation.symptom_triage import triage

    assert triage(text, lang).red_flag is True


@pytest.mark.parametrize("text, lang", [("What does heavy bleeding mean?", "en"), ("خونریزی شدید یعنی چی؟", "fa")])
def test_p1_a_pure_definition_question_is_not_an_emergency(text, lang):
    from backend.app.services.care_navigation.symptom_triage import triage

    assert triage(text, lang).red_flag is False


def test_p1_the_support_protocol_names_numbers_only_for_a_verified_region():
    generic = cs.crisis_hint()
    assert "115" not in generic and "123" not in generic and "1480" not in generic and "local emergency number" in generic
    iran = cs.crisis_hint(lines=el.REGION_LINES["IR"])
    assert "115" in iran and "123" in iran and "1480" in iran


def test_p1_hint_for_turn_uses_the_resolved_region(monkeypatch):
    monkeypatch.setattr(cs, "_region_lines", lambda db, uid, lang: None)
    h = cs.hint_for_turn(None, None, "I want to die", "en")
    assert h and "115" not in h
    monkeypatch.setattr(cs, "_region_lines", lambda db, uid, lang: el.REGION_LINES["IR"])
    assert "115" in cs.hint_for_turn(None, None, "I want to die", "en")


@pytest.mark.parametrize("text", ["The trial period ends tomorrow", "this period of my life is busy"])
def test_p2_the_word_period_alone_is_not_a_menstrual_complaint(text):
    from backend.app.services.care_navigation.symptom_triage import triage

    assert "زنان" not in triage(text, "en").specialties


@pytest.mark.parametrize("text, lang", [("my period is late", "en"), ("I have painful periods", "en"), ("پریود شدم و درد دارم", "fa")])
def test_p2_real_menstrual_complaints_still_route_to_the_gynaecologist(text, lang):
    from backend.app.services.care_navigation.symptom_triage import triage

    assert "زنان" in triage(text, lang).specialties


# --- third Codex round: the scope of a negation -----------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "There was no warning before I fainted", "I have no fever but heavy bleeding", "no pain, however I fainted today",
    "I never fainted before but now I passed out", "I fainted and I never had this before"])
def test_p1_a_negation_of_something_else_never_hides_a_real_emergency(text):
    from backend.app.services.care_navigation.symptom_triage import triage

    assert triage(text, "en").red_flag is True


@pytest.mark.parametrize("text", [
    "I have never fainted", "I never ever passed out", "I do not have heavy bleeding", "no heavy bleeding", "I have not fainted"])
def test_p1_a_negation_directly_governing_the_symptom_still_denies_it(text):
    from backend.app.services.care_navigation.symptom_triage import triage

    assert triage(text, "en").red_flag is False

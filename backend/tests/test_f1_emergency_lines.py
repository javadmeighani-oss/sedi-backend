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

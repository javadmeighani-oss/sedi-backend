"""R-078: «send me another one now» -> default title (no junk label) and a «right now» confirmation."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.services.intelligence.reminder_event_dispatch import confirmation_message
from backend.app.services.intelligence.reminder_event_readiness import describe_when, parse_reminder_event_draft

NOW = datetime(2026, 11, 7, 16, 42, tzinfo=timezone.utc)
DEFAULTS = {"fa": "یادآوری", "ar": None, "en": "Reminder"}


@pytest.mark.parametrize(
    "msg,lang",
    [
        ("یه نوتیف دیگه دوباره برام الان ارسال کن", "fa"),
        ("send me another notification now", "en"),
        ("أرسل لي إشعاراً آخر الآن", "ar"),
    ],
)
def test_filler_words_never_become_the_label(msg, lang):
    d, _ = parse_reminder_event_draft(message=msg, timezone_name="Asia/Tehran", now_utc=NOW, language=lang)
    for junk in ("دیگه", "دوباره", "another", "again", "اً", "آخر", "send"):
        assert junk not in d.title.split() and d.title != junk
    assert len(d.title) > 2 and "اً" != d.title


@pytest.mark.parametrize("msg,lang,marker", [
    ("الان برام نوتیف بفرست", "fa", "همین الان"),
    ("send me a notification now", "en", "right now"),
])
def test_immediate_reminder_is_confirmed_as_now(msg, lang, marker):
    d, _ = parse_reminder_event_draft(message=msg, timezone_name="Asia/Tehran", now_utc=NOW, language=lang)
    assert describe_when(d, lang, NOW) == marker


def test_real_titles_and_clock_times_are_untouched():
    d, _ = parse_reminder_event_draft(message="فردا ساعت ۱۰ یادم بنداز باز کردن حساب", timezone_name="Asia/Tehran", now_utc=NOW, language="fa")
    assert d.title == "باز کردن حساب"
    assert describe_when(d, "fa", NOW) != "همین الان"


def test_default_title_is_not_echoed_in_the_confirmation():
    msg = confirmation_message({"when": "همین الان", "title": "یادآوری", "offset_min": None}, "fa")
    assert "«یادآوری»" not in msg and "همین الان" in msg


@pytest.mark.parametrize("spelling", ["إشعارًا", "إشعاراً", "إشعارا"])
def test_vocalized_arabic_notification_word_leaves_no_residue(spelling):
    d, _ = parse_reminder_event_draft(message=f"أرسل لي {spelling} الآن", timezone_name="Asia/Tehran", now_utc=NOW, language="ar")
    assert d.title.strip("اًٌٍَُِّْ ") != "" and "ا" != d.title.replace("ً", "").strip()
    assert not any(ch in d.title for ch in "ًٌٍ")


@pytest.fixture(autouse=True)
def _legacy_bare_hours(monkeypatch):
    """These tests pin other behaviour with bare hours («ساعت ۱۰»); the ask-the-period rule (BE-C) has its own test file."""
    monkeypatch.setenv("SEDI_REMINDER_ASK_PERIOD", "0")

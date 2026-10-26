"""R-026: Sedi sets and sends reminders asked for in chat ("فردا ساعت ۱۰ صبح یادم بنداز ...").

Covers the parser (how people really ask), the confirmation, the I10 delivery chain (generic + medical events,
provider freshness gate) and the scheduler (offset 0 fires, 5-minute cadence).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.services.i10.provider_delivery_policy import (
    ProviderFreshnessOutcome,
    evaluate_notification_provider_freshness,
)
from backend.app.services.intelligence.reminder_event_dispatch import (
    confirmation_message,
    dispatch_reminder_user_event,
)
from backend.app.services.intelligence.reminder_event_readiness import (
    describe_when,
    parse_reminder_event_draft,
)
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.app.services.section10.event_reminder_scheduler import process_event_reminders

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

# 2026-10-26 12:00 UTC = 15:30 in Tehran (Monday).
NOW = datetime(2026, 10, 26, 12, 0)
TZ = "Asia/Tehran"


def _parse(message: str, language: str | None = None):
    return parse_reminder_event_draft(message=message, timezone_name=TZ, now_utc=NOW, language=language)


# ---------------------------------------------------------------- parser
@pytest.mark.parametrize(
    "message, when, offsets, etype",
    [
        ("فردا ساعت 10 صبح بهم یادآوری کن که قرص بخورم", "2026-10-27 10:00", (0,), "other"),
        ("فردا ساعت ۱۰ صبح نوبت دکتر دارم یادم بنداز", "2026-10-27 10:00", (0,), "doctor_visit"),
        ("پس‌فردا ساعت ۱۴ یادآوری کن آزمایش خون بدم", "2026-10-28 14:00", (0,), "lab_test"),
        ("یادم بنداز امشب ساعت ۸ قرص فشار بخورم", "2026-10-26 20:00", (0,), "other"),
        ("سه‌شنبه ساعت ۱۶ یادم بنداز جلسه", "2026-10-27 16:00", (0,), "work_meeting"),
        ("هفته‌ی بعد سه‌شنبه ساعت ۱۶ نوبت دندانپزشکی دارم یادآوری کن", "2026-11-03 16:00", (0,), "doctor_visit"),
        ("۵ آبان ساعت ۸ صبح یادآوری کن آزمایش", "2026-10-27 08:00", (0,), "lab_test"),
        ("۱۴۰۵/۰۸/۱۰ ساعت ۹ یادآوری کن چکاپ", "2026-11-01 09:00", (0,), "other"),
        ("remind me tomorrow at 10am to call the doctor", "2026-10-27 10:00", (0,), "other"),
        ("remind me 1 hour before: tomorrow at 9 pm exam", "2026-10-27 21:00", (60,), "exam"),
        ("تذكير غدا الساعة 10 صباحا موعد الطبيب", "2026-10-27 10:00", (0,), "doctor_visit"),
        # An appointment stated without any reminder word still gets a reminder (1 hour ahead).
        ("فردا ساعت ۱۰ آزمایش خون دارم", "2026-10-27 10:00", (60,), "lab_test"),
        ("امروز ساعت ۵ جلسه دارم", "2026-10-26 17:00", (60,), "work_meeting"),
    ],
)
def test_parser_understands_real_requests(message, when, offsets, etype):
    draft, missing = _parse(message)
    assert missing is None and draft is not None, (message, missing)
    assert draft.starts_at_local.strftime("%Y-%m-%d %H:%M") == when
    assert draft.reminder_offsets == offsets
    assert draft.event_type == etype
    assert draft.reminder_enabled is True


def test_relative_and_now_requests():
    d, miss = _parse("نیم ساعت دیگه یادم بنداز چایی بذارم")
    assert miss is None and d.starts_at_local == datetime(2026, 10, 26, 16, 0) and d.relative
    d, miss = _parse("۲ ساعت دیگه یادآوری کن دارو")
    assert miss is None and d.starts_at_local == datetime(2026, 10, 26, 17, 30)
    d, miss = _parse("الان یه نوتیف پیگیری برای من ارسال کن")
    assert miss is None and d.starts_at_local == datetime(2026, 10, 26, 15, 32) and d.title == "پیگیری"


def test_titles_are_clean_and_localized():
    d, _ = _parse("فردا ساعت 10 صبح بهم یادآوری کن که قرص بخورم")
    assert d.title == "قرص بخورم"
    d, _ = _parse("فردا ساعت ۱۲ شب یادم بنداز")
    assert d.title == "یادآوری"  # nothing to say -> a localized default, not "Reminder"
    d, _ = _parse("remind me tomorrow at 10am to call the doctor")
    assert d.title == "call the doctor"


def test_missing_and_past_and_recurrence():
    assert _parse("فردا یادم بنداز")[1] == "datetime"
    assert _parse("امروز ساعت ۱۰ صبح یادم بنداز")[1] == "past"  # 10:00 already passed (it is 15:30)
    assert _parse("هر شب ساعت ۱۱ می‌خوابم")[1] == "recurrence"
    assert parse_reminder_event_draft(message="Tomorrow at 10 I have an exam", timezone_name=None, now_utc=NOW)[1] == "timezone"


def test_period_words_do_not_turn_exam_into_am():
    """Latin 'am' inside words ('exam', 'program') must not be read as the AM marker."""
    d, miss = _parse("remind me tomorrow at 12 about the exam")
    assert miss is None and d.starts_at_local.hour == 12


# ---------------------------------------------------------------- confirmation
def test_confirmation_says_what_and_when():
    d, _ = _parse("فردا ساعت 10 صبح بهم یادآوری کن که قرص بخورم")
    info = {"when": describe_when(d, "fa", NOW), "title": d.title, "offset_min": 0}
    msg = confirmation_message(info, "fa")
    assert "فردا ساعت ۱۰:۰۰" in msg and "قرص بخورم" in msg and "برنامه‌ی من" in msg
    info["offset_min"] = 60
    assert "یه ساعت قبلش" in confirmation_message(info, "fa")
    assert "tomorrow at 10:00" in confirmation_message(
        {"when": describe_when(d, "en", NOW), "title": "x", "offset_min": 0}, "en"
    )


# ---------------------------------------------------------------- delivery chain
_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG_PATCH = patch(
    "backend.app.services.section10.feature_flags.event_reminder_scheduler_enabled",
    return_value=True,
)


@pytest.fixture
def chain_patch():
    with _GATE4_PATCH, _FLAG_PATCH:
        yield


def _user(db, lang: str = "fa") -> models.User:
    row = models.User(name="r026-user", secret_key=f"sk-r026-{lang}", preferred_language=lang)
    db.add(row)
    db.commit()
    db.refresh(row)
    ensure_self_subject_for_account(db, row.id, commit=True)
    return row


def test_chat_request_becomes_event_then_notification_that_providers_may_send(chain_patch, db):
    """Chat text -> UserEvent -> scheduler -> I10 notification -> provider freshness ALLOW (the chain never worked before)."""
    from datetime import timezone as _tz

    from backend.app.services.i10.event_reminder_i10_adapter import event_starts_utc

    user = _user(db, "fa")
    now = datetime.utcnow()
    result = dispatch_reminder_user_event(
        db,
        user_id=user.id,
        message="فردا ساعت 10 صبح بهم یادآوری کن که قرص بخورم",
        timezone_name="Asia/Tehran",
        now_utc=now,
        language="fa",
    )
    assert result["created"] is True and result["offset_min"] == 0 and result["title"] == "قرص بخورم"
    event = db.query(models.UserEvent).filter(models.UserEvent.user_id == user.id).one()
    assert event.source == "conversation" and event.reminder_enabled is True
    assert json.loads(event.reminder_offsets_json) == [0]
    assert event.timezone == "Asia/Tehran"

    # Nothing is sent early.
    starts = event_starts_utc(event)
    assert process_event_reminders(db, now=starts - timedelta(minutes=10)) == 0
    # Offset 0 fires AT the stated time (within the next scheduler tick).
    assert process_event_reminders(db, now=starts + timedelta(minutes=1)) == 1
    notif = db.query(models.Notification).filter(models.Notification.user_id == user.id).one()
    assert notif.title == "یادآوری از صدی"
    assert "قرص بخورم" in notif.body and "الان" in notif.body  # generic reminders show the user's own text
    assert notif.i10_policy_decision_id is not None
    fresh = evaluate_notification_provider_freshness(
        db, notif, now_utc=(starts + timedelta(minutes=1)).replace(tzinfo=_tz.utc)
    )
    assert fresh.outcome is ProviderFreshnessOutcome.ALLOW, fresh.reason_code
    # A second tick must not duplicate it.
    assert process_event_reminders(db, now=starts + timedelta(minutes=6)) == 0


def _event(db, user, *, etype="other", domain="lifestyle", title="x", starts_in_min=0, offsets=(0,), tz="UTC"):
    row = models.UserEvent(
        user_id=user.id,
        title=title,
        event_type=etype,
        event_domain=domain,
        starts_at=datetime.utcnow() + timedelta(minutes=starts_in_min),
        timezone=tz,
        status="scheduled",
        reminder_enabled=True,
        reminder_offsets_json=json.dumps(list(offsets)),
        source="conversation",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_offset_zero_fires_at_event_time_not_never(chain_patch, db):
    user = _user(db, "en")
    _event(db, user, title="call mum", starts_in_min=-1)  # just started (scheduler tick came a minute late)
    assert process_event_reminders(db) == 1
    n = db.query(models.Notification).one()
    assert n.title == "Reminder from Sedi" and "call mum" in n.body and n.body.startswith("Now")


def test_reminder_is_not_sent_long_after_the_event_started(chain_patch, db):
    user = _user(db, "en")
    _event(db, user, title="old", starts_in_min=-25)
    assert process_event_reminders(db) == 0


def test_medical_reminder_is_lock_screen_safe_and_localized(chain_patch, db):
    user = _user(db, "fa")
    _event(db, user, etype="doctor_visit", domain="medical", title="دکتر قلب بیمارستان X", starts_in_min=60, offsets=(60,))
    assert process_event_reminders(db) == 1
    n = db.query(models.Notification).one()
    assert "دکتر قلب" not in n.body and "بیمارستان" not in n.body  # the user's own medical text never hits the lock screen
    assert "یه ساعت دیگه" in n.body and "نوبت دکتر" in n.body


def test_unknown_language_falls_back_to_english(chain_patch, db):
    user = _user(db, "en")
    user.preferred_language = "xx"
    db.commit()
    _event(db, user, title="walk", starts_in_min=-1)
    assert process_event_reminders(db) == 1
    assert db.query(models.Notification).one().title == "Reminder from Sedi"


def test_scheduler_runs_every_five_minutes_and_uses_generic_path():
    root = Path(__file__).resolve().parents[2]
    src = (root / "backend" / "app" / "core" / "scheduler.py").read_text(encoding="utf-8")
    i = src.index("_section10_reminder_tick,")
    assert "minutes=5" in src[i : i + 120]
    sched = (root / "backend" / "app" / "services" / "section10" / "event_reminder_scheduler.py").read_text(encoding="utf-8")
    assert "is_remindable_event" in sched and "is_medical_remindable_event(event)" not in sched

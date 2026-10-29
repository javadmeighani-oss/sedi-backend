"""Pilot V1 (Javad 2026-10-29): the My Schedule add sheet repeats a reminder at the SAME time on chosen weekdays.
The backend already stored `recurrence_rule` and its scheduler already reads several `BYDAY` codes - these tests pin
that contract end to end and make bad rules fail loudly instead of never firing."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.app import models
from backend.app.schemas.gate2 import EventCreateIn, EventUpdateIn, normalize_recurrence_rule
from backend.app.services.section10.event_reminder_scheduler import (
    process_event_reminders,
    recurring_occurrences_utc,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, None),
        ("", None),
        ("  ", None),
        ("FREQ=DAILY", "FREQ=DAILY"),
        ("freq=daily", "FREQ=DAILY"),
        ("FREQ=WEEKLY", "FREQ=WEEKLY"),
        ("FREQ=WEEKLY;BYDAY=MO", "FREQ=WEEKLY;BYDAY=MO"),
        ("FREQ=WEEKLY;BYDAY=SA,MO,WE", "FREQ=WEEKLY;BYDAY=MO,WE,SA"),  # stored in week order
    ],
)
def test_the_rules_the_sheet_and_chat_write_are_accepted(raw, expected):
    assert normalize_recurrence_rule(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["FREQ=MONTHLY", "FREQ=WEEKLY;BYDAY=XX", "FREQ=WEEKLY;BYDAY=MO,MO", "FREQ=WEEKLY;BYDAY=", "every day", "FREQ=DAILY;INTERVAL=2"],
)
def test_other_shapes_are_rejected_not_silently_stored(raw):
    with pytest.raises(ValueError):
        normalize_recurrence_rule(raw)
    with pytest.raises(ValidationError):
        EventCreateIn(title="x", starts_at=datetime(2026, 11, 2, 21, 30), recurrence_rule=raw)
    with pytest.raises(ValidationError):
        EventUpdateIn(recurrence_rule=raw)


def test_the_models_normalise_on_the_way_in():
    ev = EventCreateIn(title="ورزش", starts_at=datetime(2026, 11, 2, 21, 30), recurrence_rule="freq=weekly;byday=sa,mo")
    assert ev.recurrence_rule == "FREQ=WEEKLY;BYDAY=MO,SA"
    assert EventUpdateIn(recurrence_rule=" ").recurrence_rule is None


def test_the_scheduler_expands_several_weekdays_at_the_same_local_time():
    class _Ev:  # the scheduler only reads these fields
        recurrence_rule = "FREQ=WEEKLY;BYDAY=MO,WE,SA"
        starts_at = datetime(2026, 11, 2, 21, 30)  # a Monday, 21:30 Asia/Tehran
        timezone = "Asia/Tehran"

    now = datetime(2026, 11, 1, 12, 0)  # Sunday noon UTC
    occ = recurring_occurrences_utc(_Ev(), now)
    days = {tag for _utc, tag in occ}
    assert {"20261102", "20261104", "20261107"} <= days  # Mon, Wed, Sat
    assert "20261103" not in days and "20261105" not in days  # Tue, Thu are not repeated
    for utc, _tag in occ:
        # 21:30 Tehran (+03:30 in Nov 2026 no DST) = 18:00 UTC every time
        assert (utc.hour, utc.minute) == (18, 0)


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


def test_a_series_on_two_weekdays_fires_on_those_days_only(chain_patch, db):
    """The add sheet sends FREQ=WEEKLY;BYDAY=<d1>,<d2>: the reminder fires on d1 and d2 at the same time, not between."""
    from backend.app.services.i10.event_reminder_i10_adapter import event_starts_utc
    from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account

    user = models.User(name="rep-days", secret_key="sk-rep", preferred_language="fa")
    db.add(user)
    db.commit()
    db.refresh(user)
    ensure_self_subject_for_account(db, user.id, commit=True)

    codes = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
    start = (datetime.utcnow() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    second = (start + timedelta(days=2)).weekday()
    rule = normalize_recurrence_rule(f"FREQ=WEEKLY;BYDAY={codes[second]},{codes[start.weekday()]}")
    event = models.UserEvent(
        user_id=user.id,
        title="ورزش",
        event_domain="lifestyle",
        event_type="other",
        starts_at=start,
        timezone="UTC",
        status="scheduled",
        reminder_enabled=True,
        reminder_offsets_json="[0]",
        recurrence_rule=rule,
        source="manual",
    )
    db.add(event)
    db.commit()

    first = event_starts_utc(event) + timedelta(minutes=1)
    assert process_event_reminders(db, now=first) == 1  # the first chosen day
    assert process_event_reminders(db, now=first + timedelta(minutes=5)) == 0  # same occurrence, no duplicate
    assert process_event_reminders(db, now=first + timedelta(days=1)) == 0  # the day in between is NOT repeated
    assert process_event_reminders(db, now=first + timedelta(days=2)) == 1  # the second chosen day, same time

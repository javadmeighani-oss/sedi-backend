"""Gate 4D-3 — NotificationPrefs daily_notification_time tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.models import NotificationPrefs, User
from backend.app.schemas.notification_prefs import (
    NotificationPrefsRead,
    NotificationPrefsUpdate,
    validate_hhmm_24h,
)
from backend.app.services.gate4.policy_prefs_bridge import (
    DEFAULT_DAILY_NOTIFICATION_TIME,
    resolve_daily_notification_time,
)
from backend.app.services.notifications.prefs_service import get_prefs, upsert_prefs


@pytest.fixture
def prefs_user(db):
    user = User(name="DailyTime User", secret_key="dt", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_model_has_daily_notification_time_attribute():
    assert hasattr(NotificationPrefs, "daily_notification_time")


@pytest.mark.parametrize(
    "value",
    ["08:00", "09:30", "23:59", "00:00"],
)
def test_schema_accepts_valid_hhmm(value):
    model = NotificationPrefsUpdate(daily_notification_time=value)
    assert model.daily_notification_time == value


@pytest.mark.parametrize(
    "value",
    ["8:00", "24:00", "12:60", "abc", ""],
)
def test_schema_rejects_invalid_hhmm(value):
    with pytest.raises(ValidationError):
        NotificationPrefsUpdate(daily_notification_time=value)


def test_validate_hhmm_24h_helper():
    assert validate_hhmm_24h("08:00") == "08:00"
    with pytest.raises(ValueError):
        validate_hhmm_24h("24:00", field_name="daily_notification_time")


def test_prefs_service_create_and_update_daily_time(db, prefs_user):
    updated = upsert_prefs(
        db,
        prefs_user.id,
        NotificationPrefsUpdate(daily_notification_time="07:45"),
    )
    assert updated.daily_notification_time == "07:45"

    read = get_prefs(db, prefs_user.id)
    assert read.daily_notification_time == "07:45"

    partial = upsert_prefs(db, prefs_user.id, NotificationPrefsUpdate(engagement_level=0))
    assert partial.daily_notification_time == "07:45"
    assert partial.engagement_level == 0


def test_prefs_service_clear_daily_time_with_null(db, prefs_user):
    upsert_prefs(db, prefs_user.id, NotificationPrefsUpdate(daily_notification_time="10:15"))
    cleared = upsert_prefs(db, prefs_user.id, NotificationPrefsUpdate(daily_notification_time=None))
    assert cleared.daily_notification_time is None


def test_get_prefs_defaults_include_null_daily_time(db, prefs_user):
    defaults = get_prefs(db, prefs_user.id)
    assert isinstance(defaults, NotificationPrefsRead)
    assert defaults.daily_notification_time is None


def test_router_put_and_get_daily_notification_time(db, prefs_user):
    from backend.app.routers.notifications import get_notification_prefs, put_notification_prefs

    put_result = put_notification_prefs(
        body=NotificationPrefsUpdate(daily_notification_time="08:30"),
        auth_user=prefs_user,
        user_id=prefs_user.id,
        db=db,
    )
    assert put_result.ok is True
    assert put_result.data["daily_notification_time"] == "08:30"

    get_result = get_notification_prefs(
        auth_user=prefs_user,
        user_id=prefs_user.id,
        db=db,
    )
    assert get_result.ok is True
    assert get_result.data["daily_notification_time"] == "08:30"


def test_router_put_rejects_invalid_daily_time_schema():
    with pytest.raises(ValidationError):
        NotificationPrefsUpdate(daily_notification_time="8:00")


def test_resolver_prefers_prefs_over_memory_fact():
    prefs = SimpleNamespace(daily_notification_time="09:15")
    memory = {"hour": 7, "minute": 0}
    assert resolve_daily_notification_time(notification_prefs=prefs, memory_fact_time=memory) == "09:15"


def test_resolver_uses_memory_when_prefs_missing():
    prefs = SimpleNamespace(daily_notification_time=None)
    memory = {"hour": 9, "minute": 30}
    assert resolve_daily_notification_time(notification_prefs=prefs, memory_fact_time=memory) == "09:30"


def test_resolver_final_fallback_is_08_00():
    assert resolve_daily_notification_time() == DEFAULT_DAILY_NOTIFICATION_TIME
    assert DEFAULT_DAILY_NOTIFICATION_TIME == "08:00"

"""P10: Health (heart rate only) - exact gadget data status, a range summary and trend, the day's HR average in Sedi's
memory (I7), and one gentle "your gadget went quiet" question through I10 (OFF unless its flag is set)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytz

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.services.i10 import hr_data_gap_producer as gap
from backend.app.services.i7.derived_signals import collect_daily_signals, merge_signals
from backend.app.services.lifestyle.a3_health_hr_projection import _summary, _trend, build_lifestyle_hr_projection
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

TEHRAN = pytz.timezone("Asia/Tehran")


def _auth(uid):
    return {"Authorization": f"Bearer {create_access_token({'user_id': uid})}"}


def _device(db, user):
    d = models.Device(user_id=user.id, device_id=f"p10-{uuid4().hex[:8]}", device_type="heart_rate", status="active", token_hash=f"th-{uuid4().hex}")
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _bpm(db, user, device, value, at):
    db.add(models.PhysiologicalMeasurement(
        user_id=user.id, device_id=device.id, measurement_type="heart_rate", numeric_value=value, unit="bpm",
        measured_at=at, received_at=at, idempotency_key=f"p10-{uuid4().hex}", ingestion_status="accepted",
    ))
    db.commit()


def test_summary_and_trend_are_plain_observations_of_the_users_numbers():
    pts = [{"avg": 70.0, "min": 60.0, "max": 90.0, "count": 10}, {"avg": 74.0, "min": 62.0, "max": 95.0, "count": 30}]
    assert _summary(pts) == {"avg": 73, "min": 60, "max": 95}  # sample-weighted
    assert _summary([]) is None
    assert _trend([{"avg": 70.0}] * 3) == "insufficient"
    assert _trend([{"avg": a} for a in (70, 71, 72, 71, 70, 71, 79, 80)]) == "up"
    assert _trend([{"avg": a} for a in (80, 79, 72, 71, 70, 71, 70, 72)]) == "down"
    assert _trend([{"avg": a} for a in (72, 73, 72, 74, 73, 72, 73, 72)]) == "steady"


def test_data_status_states_and_todays_gap(db):
    u = _user(db, "+17770061001", tz="Asia/Tehran")
    dev = _device(db, u)
    status = build_lifestyle_hr_projection(db, u.id)["data_status"]
    assert status["state"] == "never" and status["today"]["count"] == 0 and status["minutes_since_last"] is None

    now = datetime.now(timezone.utc)
    midnight = TEHRAN.localize(datetime.combine(now.astimezone(TEHRAN).date(), datetime.min.time())).astimezone(timezone.utc)
    if now - midnight < timedelta(hours=3):
        pytest.skip("too close to local midnight for a same-day gap fixture")
    for minutes in (150, 140, 20, 3):  # a long quiet stretch (140 -> 20) then fresh data
        _bpm(db, u, dev, 72.0, now - timedelta(minutes=minutes))
    st = build_lifestyle_hr_projection(db, u.id)["data_status"]
    assert st["state"] == "receiving" and st["minutes_since_last"] <= 5
    assert st["today"]["count"] == 4 and st["today"]["longest_gap_minutes"] >= 115  # the 140 -> 20 minute silence

    _bpm(db, u, dev, 70.0, now - timedelta(hours=30))
    other = _user(db, "+17770061002", tz="Asia/Tehran")
    assert build_lifestyle_hr_projection(db, other.id)["data_status"]["state"] == "never"  # nobody else's data


def test_state_quiet_and_stale(db):
    u = _user(db, "+17770061003", tz="Asia/Tehran")
    dev = _device(db, u)
    _bpm(db, u, dev, 72.0, datetime.now(timezone.utc) - timedelta(hours=5))
    assert build_lifestyle_hr_projection(db, u.id)["data_status"]["state"] == "quiet"
    u2 = _user(db, "+17770061004", tz="Asia/Tehran")
    _bpm(db, u2, _device(db, u2), 72.0, datetime.now(timezone.utc) - timedelta(days=3))
    assert build_lifestyle_hr_projection(db, u2.id)["data_status"]["state"] == "stale"


def test_the_days_hr_average_becomes_a_memory_signal_and_merges_upwards(db):
    u = _user(db, "+17770061005", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    dev = _device(db, u)
    now = datetime.now(timezone.utc)
    local_day = now.astimezone(TEHRAN).date()
    start = TEHRAN.localize(datetime.combine(local_day, datetime.min.time())).astimezone(timezone.utc)
    for i, v in enumerate((60.0, 70.0, 80.0)):
        _bpm(db, u, dev, v, start + timedelta(minutes=5 + i))
    sig = collect_daily_signals(db, u.id, local_day, [])
    assert sig["hr"] == {"count": 3, "avg": 70, "min": 60, "max": 80}
    merged = merge_signals([sig, {"hr": {"count": 1, "avg": 90, "min": 90, "max": 90}}, {}])
    assert merged["hr"] == {"count": 4, "avg": 75, "min": 60, "max": 90, "days": 2}
    assert "hr" not in merge_signals([{}, {}])


def test_the_memory_day_view_shows_the_hr_average(client, db):
    u = _user(db, "+17770061006", tz="Asia/Tehran")
    u.preferred_language = "fa"
    db.commit()
    _seed_consent(db, u.id)
    dev = _device(db, u)
    now = datetime.now(timezone.utc)
    start = TEHRAN.localize(datetime.combine(now.astimezone(TEHRAN).date(), datetime.min.time())).astimezone(timezone.utc)
    for i, v in enumerate((68.0, 72.0)):
        _bpm(db, u, dev, v, start + timedelta(minutes=10 + i))
    day = client.get("/memory/day", params={"date": now.astimezone(TEHRAN).date().isoformat()}, headers=_auth(u.id)).json()["data"]
    assert day["summary"]["chips"]["hr_avg"] == 70
    assert "ضربان قلبت به‌طور میانگین حدود 70 بود" in day["summary"]["text"]


def test_projection_endpoint_carries_the_new_fields(client, db):
    u = _user(db, "+17770061007", tz="Asia/Tehran")
    r = client.get("/lifestyle/health-hr", params={"range_key": "7d"}, headers=_auth(u.id))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["summary"] is None and data["trend"] == "insufficient" and data["data_status"]["state"] == "never"


# ---------- the gap producer ----------
def test_gap_producer_is_dormant_without_its_flag(db, monkeypatch):
    monkeypatch.delenv("SEDI_I10_HR_DATA_GAP_ENABLED", raising=False)
    assert gap.run_hr_data_gap_scan(db) == {"processed": 0, "sent": 0, "dormant": True}


def test_gap_copy_is_warm_localized_and_lock_screen_safe(db):
    u = _user(db, "+17770061008", tz="Asia/Tehran")
    u.name = "جواد"
    u.preferred_language = "fa"
    db.commit()
    title, body = gap.render_copy(db, u.id)
    assert title == "گجتت" and body.startswith("جواد، ") and "سدی" not in body
    for word in ("bpm", "ضربان", "قلب", "heart", "بیمار"):
        assert word not in title + body  # never a value, a rhythm or a condition
    u.preferred_language = "en"
    db.commit()
    assert gap.render_copy(db, u.id)[0] == "Your gadget"


def test_gap_producer_asks_once_per_quiet_episode(db, monkeypatch):
    monkeypatch.setenv("SEDI_I10_HR_DATA_GAP_ENABLED", "1")
    u = _user(db, "+17770061009", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    dev = _device(db, u)
    last = datetime.now(timezone.utc) - timedelta(hours=26)
    _bpm(db, u, dev, 72.0, last)
    fresh = _user(db, "+17770061010", tz="Asia/Tehran")
    _bpm(db, fresh, _device(db, fresh), 72.0, datetime.now(timezone.utc) - timedelta(minutes=10))
    old = _user(db, "+17770061011", tz="Asia/Tehran")
    _bpm(db, old, _device(db, old), 72.0, datetime.now(timezone.utc) - timedelta(days=20))

    first = gap.run_hr_data_gap_scan(db)
    assert first == {"processed": 1, "sent": 1, "dormant": False}  # only the user whose gadget went quiet 20h..7d ago
    again = gap.run_hr_data_gap_scan(db)
    assert again["sent"] == 0  # the same episode is never repeated
    rows = db.query(models.Notification).filter(models.Notification.user_id == u.id, models.Notification.template_key == "hr_data_gap").all()
    assert len(rows) == 1 and rows[0].title == "Your gadget"
    assert not db.query(models.Notification).filter(models.Notification.user_id.in_([fresh.id, old.id])).count()

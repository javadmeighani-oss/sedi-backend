"""H1: the memory explorer (calendar, one day, search, day notes, turn edit/delete) — 30-day raw window, notes beside old summaries."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytz

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.services.i7.life_events import record_life_event
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

TEHRAN = pytz.timezone("Asia/Tehran")


def _auth(uid):
    return {"Authorization": f"Bearer {create_access_token({'user_id': uid})}"}


def _today():
    return datetime.now(timezone.utc).astimezone(TEHRAN).date()


def _turn(db, uid, days_ago, text, reply="باشه", *, hour=10):
    """A chat turn `days_ago` local days back at `hour`:00 (Tehran); retention follows the 30-day rule."""
    day = _today() - timedelta(days=days_ago)
    at = TEHRAN.localize(datetime(day.year, day.month, day.day, hour, 0)).astimezone(timezone.utc)
    row = models.Memory(
        user_id=uid, user_message=text, sedi_response=reply, language="fa",
        created_at=at.replace(tzinfo=None), retain_until=at + timedelta(days=30),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, day


def test_day_shows_raw_only_inside_thirty_days(client, db):
    u = _user(db, "+17770031001", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    _, recent = _turn(db, u.id, 2, "امروز نوبت دکتر دارم")
    _, old = _turn(db, u.id, 60, "درباره خواب حرف زدیم")

    d = client.get("/memory/day", params={"date": recent.isoformat()}, headers=_auth(u.id)).json()["data"]
    assert d["raw_visible"] is True and d["days_ago"] == 2
    assert [t["user_message"] for t in d["turns"]] == ["امروز نوبت دکتر دارم"] and d["turns"][0]["time"] == "10:00"

    o = client.get("/memory/day", params={"date": old.isoformat()}, headers=_auth(u.id)).json()["data"]
    assert o["raw_visible"] is False and o["turns"] == []  # the raw text of an old day is never returned


def test_old_day_correction_is_a_note_beside_the_summary_not_a_rewrite(client, db):
    u = _user(db, "+17770031002", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    day = (_today() - timedelta(days=80)).isoformat()

    r = client.post("/memory/day-notes", json={"day": day, "text": "اون روز مشکل خواب نبود", "kind": "correction"}, headers=_auth(u.id))
    assert r.status_code == 200, r.text
    note = r.json()["data"]
    assert note["kind"] == "correction" and note["day"] == day

    d = client.get("/memory/day", params={"date": day}, headers=_auth(u.id)).json()["data"]
    assert [n["text"] for n in d["notes"]] == ["اون روز مشکل خواب نبود"] and d["notes"][0]["kind"] == "correction"

    e = client.patch(f"/memory/day-notes/{note['id']}", json={"text": "فقط کار زیاد داشتم"}, headers=_auth(u.id))
    assert e.json()["data"]["text"] == "فقط کار زیاد داشتم"
    assert client.delete(f"/memory/day-notes/{note['id']}", headers=_auth(u.id)).json()["data"]["deleted"] is True
    d2 = client.get("/memory/day", params={"date": day}, headers=_auth(u.id)).json()["data"]
    assert d2["notes"] == []
    # notes never leak into the schedule's life-event timeline
    assert db.query(models.UserEvent).filter(models.UserEvent.user_id == u.id, models.UserEvent.event_type == "memory_note").count() == 1


def test_notes_are_consent_gated_and_isolated(client, db):
    u = _user(db, "+17770031003", tz="Asia/Tehran")
    other = _user(db, "+17770031004", tz="Asia/Tehran")
    _seed_consent(db, other.id)
    day = _today().isoformat()
    assert client.post("/memory/day-notes", json={"day": day, "text": "x"}, headers=_auth(u.id)).status_code == 403
    assert client.get("/memory/day", params={"date": day}, headers=_auth(u.id)).json()["data"]["consent"] is False

    mine = client.post("/memory/day-notes", json={"day": day, "text": "یادداشت من"}, headers=_auth(other.id)).json()["data"]
    _seed_consent(db, u.id)
    assert client.patch(f"/memory/day-notes/{mine['id']}", json={"text": "هک"}, headers=_auth(u.id)).status_code == 404
    assert client.delete(f"/memory/day-notes/{mine['id']}", headers=_auth(u.id)).status_code == 404
    assert client.post("/memory/day-notes", json={"day": "نادرست", "text": "x"}, headers=_auth(u.id)).status_code == 422


def test_turn_edit_and_delete_inside_window_only(client, db):
    u = _user(db, "+17770031005", tz="Asia/Tehran")
    other = _user(db, "+17770031006", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    _seed_consent(db, other.id)
    row, day = _turn(db, u.id, 1, "فشار خونم بالا بود")
    expired, _ = _turn(db, u.id, 45, "پیام قدیمی")
    foreign, _ = _turn(db, other.id, 1, "پیام دیگری")

    r = client.patch(f"/memory/turns/{row.id}", json={"user_message": "فشار خونم نرمال بود"}, headers=_auth(u.id))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["user_message"] == "فشار خونم نرمال بود"
    db.expire_all()
    assert "user_edited_at" in (db.query(models.Memory).get(row.id).provenance_json or "")

    assert client.patch(f"/memory/turns/{expired.id}", json={"user_message": "x"}, headers=_auth(u.id)).status_code == 404
    assert client.patch(f"/memory/turns/{foreign.id}", json={"user_message": "x"}, headers=_auth(u.id)).status_code == 404
    assert client.patch(f"/memory/turns/{row.id}", json={}, headers=_auth(u.id)).status_code == 422

    assert client.delete(f"/memory/turns/{row.id}", headers=_auth(u.id)).json()["data"]["forgotten"] is True
    d = client.get("/memory/day", params={"date": day.isoformat()}, headers=_auth(u.id)).json()["data"]
    assert d["turns"] == []


def test_search_covers_recent_chat_and_old_events_but_never_old_raw_chat(client, db):
    u = _user(db, "+17770031007", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    _turn(db, u.id, 3, "امروز فشار خون را اندازه گرفتم")
    _turn(db, u.id, 70, "فشار خون من بالاست")  # expired raw: must stay invisible
    record_life_event(db, u.id, kind="medical_document", summary="آزمایش فشار خون سالانه", occurred_at=datetime.utcnow() - timedelta(days=90))

    res = client.get("/memory/search", params={"q": "فشار خون"}, headers=_auth(u.id)).json()["data"]
    kinds = sorted(r["type"] for r in res["results"])
    assert kinds == ["chat", "event"]
    assert all("بالاست" not in r["snippet"] for r in res["results"])
    assert res["results"][0]["type"] == "chat"  # newest first

    # Arabic letter variants (ي/ك) normalise to the Persian spelling
    arabic = client.get("/memory/search", params={"q": "آزمايش"}, headers=_auth(u.id)).json()["data"]
    assert [r["type"] for r in arabic["results"]] == ["event"]
    ranged = client.get("/memory/search", params={"q": "فشار", "from": (_today() - timedelta(days=10)).isoformat(), "to": _today().isoformat()}, headers=_auth(u.id)).json()["data"]
    assert [r["type"] for r in ranged["results"]] == ["chat"]
    assert client.get("/memory/search", params={"q": "ف"}, headers=_auth(u.id)).status_code == 422


def test_calendar_marks_days_with_memory(client, db):
    u = _user(db, "+17770031008", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    _, d1 = _turn(db, u.id, 4, "سلام")
    _turn(db, u.id, 4, "سلام دوباره", hour=15)
    client.post("/memory/day-notes", json={"day": (_today() - timedelta(days=20)).isoformat(), "text": "یادداشت"}, headers=_auth(u.id))

    cal = client.get("/memory/calendar", params={"from": (_today() - timedelta(days=30)).isoformat(), "to": _today().isoformat()}, headers=_auth(u.id)).json()["data"]
    by_day = {x["date"]: x for x in cal["days"]}
    assert by_day[d1.isoformat()]["turns"] == 2
    assert by_day[(_today() - timedelta(days=20)).isoformat()]["notes"] == 1
    assert len(cal["days"]) == 2

    too_long = client.get("/memory/calendar", params={"from": (_today() - timedelta(days=200)).isoformat(), "to": _today().isoformat()}, headers=_auth(u.id))
    assert too_long.status_code == 422


def test_day_summary_is_derived_text_never_a_transcript(client, db):
    u = _user(db, "+17770031009", tz="Asia/Tehran")
    u.preferred_language = "fa"
    db.commit()
    _seed_consent(db, u.id)
    _, day = _turn(db, u.id, 1, "امروز خیلی خسته‌ام و استرس دارم")
    d = client.get("/memory/day", params={"date": day.isoformat()}, headers=_auth(u.id)).json()["data"]
    assert "خسته" in d["summary"]["text"] or "استرس" in d["summary"]["text"]
    assert "امروز خیلی خسته‌ام" not in d["summary"]["text"]  # a derived sentence, not the user's words echoed back
    assert set(d["summary"]["chips"]["wellbeing"]) >= {"fatigue", "stress"}

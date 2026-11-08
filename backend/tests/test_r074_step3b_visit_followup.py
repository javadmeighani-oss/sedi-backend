"""R-074 step 3b: the next visit printed on a confirmed document becomes a scheduled doctor visit (only on the user's yes),
printed instructions are echoed as printed, and the pre-visit checklist is built only from the user's own recorded picture."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.services.i7 import attachments as att
from backend.app.services.i7 import health_documents as hd
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

PDF = b"%PDF-1.4\n" + b"sedi-test-pdf" * 20


def _auth(uid):
    return {"Authorization": f"Bearer {create_access_token({'user_id': uid})}"}


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("SEDI_ATTACHMENTS_ENABLED", "true")


def _doc(client, monkeypatch, uid, payload, tag):
    monkeypatch.setattr(att, "_analyze_with_openai", lambda b, m, lang: json.dumps(payload, ensure_ascii=False))
    up = client.post("/memory/attachments", files={"file": (f"{tag}.pdf", PDF + tag.encode() * 3, "application/pdf")}, headers=_auth(uid))
    aid = up.json()["data"]["id"]
    done = client.post(f"/memory/attachments/{aid}/process", headers=_auth(uid)).json()["data"]
    return aid, done


def _rx(days_ahead=20, **extra):
    d = {
        "document_type": "prescription", "summary": "نسخه", "date": "2026-11-02", "findings": [],
        "medications": ["Metformin 500"], "instructions": ["take after meals", "repeat the blood test"],
        "next_visit_date": (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d"),
    }
    d.update(extra)
    return d


def test_the_visit_is_suggested_but_never_created_before_the_user_says_yes(client, db, monkeypatch):
    u = _user(db, "+17770025001", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    aid, done = _doc(client, monkeypatch, u.id, _rx(), "a")
    a = done["analysis"]
    assert {"kind": "next_visit", "date": _rx()["next_visit_date"], "time": ""} in a["suggestions"]
    assert "take after meals" in a["text"]  # instructions are echoed exactly as printed
    assert any(s["kind"] == "medication_times" for s in a["suggestions"])
    r = client.post(f"/memory/attachments/{aid}/accept-next-visit", headers=_auth(u.id))
    assert r.status_code == 409  # not confirmed yet
    assert db.query(models.UserEvent).filter(models.UserEvent.user_id == u.id, models.UserEvent.event_type == "doctor_visit").count() == 0


def test_accepting_creates_one_doctor_visit_with_a_reminder_and_is_idempotent(client, db, monkeypatch):
    u = _user(db, "+17770025002", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    aid, _ = _doc(client, monkeypatch, u.id, _rx(), "b")
    conf = client.post(f"/memory/attachments/{aid}/confirm", headers=_auth(u.id)).json()["data"]
    assert "what time" in conf["analysis"]["text"].lower()  # no time printed: Sedi asks for it, never guesses (Codex P2)
    first = client.post(f"/memory/attachments/{aid}/accept-next-visit?time=14:30", headers=_auth(u.id)).json()["data"]
    assert first["created"] is True and first["duplicate"] is False and first["time"] == "14:30" and first["time_assumed"] is False
    ev = db.query(models.UserEvent).filter(models.UserEvent.user_id == u.id, models.UserEvent.event_type == "doctor_visit").one()
    assert ev.event_type == "doctor_visit" and ev.event_domain == "medical" and ev.reminder_enabled is True
    assert json.loads(ev.reminder_offsets_json) == [60] and ev.source == "system"
    second = client.post(f"/memory/attachments/{aid}/accept-next-visit", headers=_auth(u.id)).json()["data"]
    assert second["duplicate"] is True and second["event_id"] == first["event_id"]
    assert db.query(models.UserEvent).filter(models.UserEvent.user_id == u.id, models.UserEvent.event_type == "doctor_visit").count() == 1


def test_a_past_or_missing_date_suggests_nothing_and_accept_is_refused(client, db, monkeypatch):
    u = _user(db, "+17770025003", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    aid, done = _doc(client, monkeypatch, u.id, _rx(days_ahead=-90), "c")
    assert not any(s["kind"] == "next_visit" for s in done["analysis"]["suggestions"])
    client.post(f"/memory/attachments/{aid}/confirm", headers=_auth(u.id))
    assert client.post(f"/memory/attachments/{aid}/accept-next-visit", headers=_auth(u.id)).status_code == 404
    aid2, done2 = _doc(client, monkeypatch, u.id, _rx(next_visit_date="not a date"), "c2")
    assert not any(s["kind"] == "next_visit" for s in done2["analysis"]["suggestions"])


def test_the_validator_drops_bad_dates_and_bounds_instructions():
    ok = att.validate_document_findings(json.dumps({"document_type": "report", "summary": "x", "next_visit_date": "2026-13-45", "instructions": ["a"] * 9}))
    assert ok["next_visit_date"] == "" and len(ok["instructions"]) == 5


def test_previsit_checklist_uses_only_the_recorded_picture(client, db, monkeypatch):
    u = _user(db, "+17770025004", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    empty = client.get("/memory/previsit-checklist", headers=_auth(u.id)).json()["data"]
    assert len(empty["bring"]) == 1 and "Metformin" not in empty["text"]  # nothing recorded -> nothing invented
    aid, _ = _doc(client, monkeypatch, u.id, _rx(), "d")
    client.post(f"/memory/attachments/{aid}/confirm", headers=_auth(u.id))
    full = client.get("/memory/previsit-checklist", headers=_auth(u.id)).json()["data"]
    assert "Metformin 500" in full["text"] and len(full["bring"]) == 2 and len(full["say"]) == 3


@pytest.mark.parametrize("lang,marker", [("fa", "پیش از ویزیت"), ("ar", "قبل الزيارة"), ("en", "Before the visit")])
def test_the_checklist_speaks_three_languages(db, lang, marker):
    u = _user(db, f"+1777002510{['fa', 'ar', 'en'].index(lang)}", tz="Asia/Tehran")
    assert marker in hd.previsit_checklist(db, u.id, lang)["text"]


def test_printed_time_is_used_and_an_unknown_time_is_flagged_as_assumed(client, db, monkeypatch):
    u = _user(db, "+17770025005", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    aid, _ = _doc(client, monkeypatch, u.id, _rx(next_visit_time="16:45"), "f")
    conf = client.post(f"/memory/attachments/{aid}/confirm", headers=_auth(u.id)).json()["data"]
    assert "16:45" in conf["analysis"]["text"]
    ok = client.post(f"/memory/attachments/{aid}/accept-next-visit", headers=_auth(u.id)).json()["data"]
    assert ok["time"] == "16:45" and ok["time_assumed"] is False
    aid2, _ = _doc(client, monkeypatch, u.id, _rx(days_ahead=40), "g")
    client.post(f"/memory/attachments/{aid2}/confirm", headers=_auth(u.id))
    assumed = client.post(f"/memory/attachments/{aid2}/accept-next-visit", headers=_auth(u.id)).json()["data"]
    assert assumed["time"] == "09:00" and assumed["time_assumed"] is True


def test_no_reminder_is_promised_while_the_scheduler_is_off(client, db, monkeypatch):
    monkeypatch.delenv("SEDI_EVENT_REMINDER_SCHEDULER_ENABLED", raising=False)
    u = _user(db, "+17770025006", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    aid, _ = _doc(client, monkeypatch, u.id, _rx(next_visit_time="10:00"), "h")
    off = client.post(f"/memory/attachments/{aid}/confirm", headers=_auth(u.id)).json()["data"]["analysis"]["text"]
    assert "reminder" not in off.split("Shall I add it")[-1].lower() and "schedule" in off
    monkeypatch.setenv("SEDI_EVENT_REMINDER_SCHEDULER_ENABLED", "true")
    aid2, _ = _doc(client, monkeypatch, u.id, _rx(days_ahead=50, next_visit_time="10:00"), "i")
    on = client.post(f"/memory/attachments/{aid2}/confirm", headers=_auth(u.id)).json()["data"]["analysis"]["text"]
    assert "a reminder an hour before" in on

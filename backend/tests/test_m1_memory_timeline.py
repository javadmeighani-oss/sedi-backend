"""R-021 / M1: life-event timeline (I7) + user-visible, user-editable memory API."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty, write_fact
from backend.app.services.i7 import life_events as le
from backend.app.services.knowledge.conversation_extraction_service import process_message
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user


def _auth(uid):
    return {"Authorization": f"Bearer {create_access_token({'user_id': uid})}"}


def test_life_event_requires_consent_is_idempotent_and_sanitized(db):
    u = _user(db, "+17770021001", tz="Asia/Tehran")
    assert le.record_life_event(db, u.id, kind="loss") is None  # no memory.write
    _seed_consent(db, u.id)
    a = le.record_life_event(db, u.id, kind="loss", subject="mother", summary="  از دست دادن مادر  ")
    b = le.record_life_event(db, u.id, kind="loss", subject="mother")
    assert a and b and a["id"] == b["id"] and a["title"] == "از دست دادن مادر"
    assert a["kind"] == "loss" and a["subject"] == "mother" and a["source"] == "conversation"
    rows = db.query(models.UserEvent).filter(models.UserEvent.user_id == u.id).all()
    assert len(rows) == 1 and rows[0].reminder_enabled is False and rows[0].status == "completed"
    assert le.list_life_events(db, u.id)[0]["id"] == a["id"]


def test_chat_care_event_lands_on_timeline_and_reaches_the_model_context(db):
    from backend.app.services.intelligence.adapters import HealthContextAdapter

    u = _user(db, "+17770021002", tz="Asia/Tehran")
    u.preferred_language = "fa"
    _seed_consent(db, u.id)
    process_message(db, u.id, "اخراج شدم", "fa")
    tl = le.list_life_events(db, u.id)
    assert [e["kind"] for e in tl] == ["job_loss"] and tl[0]["title"] == "از دست دادن کار"
    lines = [i.display_text for i in HealthContextAdapter().load(db, authenticated_user_id=u.id)]
    assert any(l.startswith("life_event=از دست دادن کار (job_loss") for l in lines)


def test_timeline_is_part_of_the_lifelong_aggregator_and_hidden_after_delete(db):
    from backend.app.services.i7.timeline import list_lifelong_timeline

    u = _user(db, "+17770021003", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    ev = le.record_life_event(db, u.id, kind="surgery", summary="عمل جراحی زانو")
    assert any(r["event_id"] == f"user_event:{ev['id']}" for r in list_lifelong_timeline(db, u.id))
    assert le.delete_life_event(db, u.id, ev["id"]) is True
    assert le.list_life_events(db, u.id) == []


def test_memory_api_overview_edit_delete_with_isolation(client, db):
    u = _user(db, "+17770021004", tz="Asia/Tehran")
    u.name = "جواد"
    _seed_consent(db, u.id)
    other = _user(db, "+17770021005", tz="Asia/Tehran")
    _seed_consent(db, other.id)
    process_message(db, u.id, "من دیابت دارم", "fa")
    process_message(db, u.id, "اخراج شدم", "fa")
    write_fact(db, other.id, "intake", "goal", "هدف دیگری")

    ov = client.get("/memory/overview", headers=_auth(u.id)).json()["data"]
    assert ov["consent"] is True and "دیابت" in ov["summary"]
    concern = next(f for f in ov["facts"] if f["key"] == "health_concerns")
    assert concern["value"] == "دیابت" and concern["editable"] is True
    assert [e["kind"] for e in ov["timeline"]] == ["job_loss"]

    # my correction supersedes the extracted value and is marked as the user's own word
    r = client.patch(f"/memory/facts/{concern['id']}", json={"value": "دیابت نوع ۲، فشار خون"}, headers=_auth(u.id))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["value"] == "دیابت نوع ۲، فشار خون"
    row = next(x for x in list_facts_readonly_or_empty(db, u.id, domain="medical") if x.key == "health_concerns")
    assert row.provenance_class == "USER_STATED" and row.source == "user_edit"

    # another user's fact is invisible to me
    other_fact = next(x for x in list_facts_readonly_or_empty(db, other.id, domain="intake"))
    assert client.patch(f"/memory/facts/{other_fact.id}", json={"value": "x"}, headers=_auth(u.id)).status_code == 404
    assert client.delete(f"/memory/facts/{other_fact.id}", headers=_auth(u.id)).status_code == 404

    assert client.delete(f"/memory/facts/{row.id}", headers=_auth(u.id)).json()["data"]["deleted"] is True
    ov2 = client.get("/memory/overview", headers=_auth(u.id)).json()["data"]
    assert not [f for f in ov2["facts"] if f["key"] == "health_concerns"]

    ev_id = ov2["timeline"][0]["id"]
    p = client.patch(f"/memory/events/{ev_id}", json={"summary": "کارم تغییر کرد"}, headers=_auth(u.id))
    assert p.json()["data"]["title"] == "کارم تغییر کرد" and p.json()["data"]["source"] == "manual"
    n = client.post("/memory/events", json={"kind": "move", "summary": "نقل‌مکان به شیراز"}, headers=_auth(u.id))
    assert n.status_code == 200 and n.json()["data"]["kind"] == "move"
    assert client.delete(f"/memory/events/{ev_id}", headers=_auth(u.id)).status_code == 200
    assert client.delete(f"/memory/events/{ev_id}", headers=_auth(other.id)).status_code == 404


def test_overview_without_consent_is_empty(client, db):
    u = _user(db, "+17770021006", tz="Asia/Tehran")
    data = client.get("/memory/overview", headers=_auth(u.id)).json()["data"]
    assert data["consent"] is False and data["facts"] == [] and data["timeline"] == []


def test_function_and_intake_facts_now_reach_the_model_with_consent(db):
    """R-021 / M3: what the user told Sedi about their body/plan is part of the second memory sent to the model."""
    from backend.app.services.intelligence.adapters import LifestyleContextAdapter
    from backend.app.services.intelligence.context_types import is_llm_projection_eligible

    u = _user(db, "+17770021007", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    write_fact(db, u.id, "function", "mobility", "برای راه رفتن از عصا استفاده می‌کنم")
    write_fact(db, u.id, "intake", "allergies", "گردو")
    write_fact(db, u.id, "intake", "goal", "بهتر شدن انرژی")
    items = {i.canonical_key: i for i in LifestyleContextAdapter().load(db, authenticated_user_id=u.id)}
    assert is_llm_projection_eligible(items["function.mobility"])
    assert is_llm_projection_eligible(items["intake.allergies"])
    assert is_llm_projection_eligible(items["lifestyle.goal.stated"])
    assert not is_llm_projection_eligible(items["intake.goal"])  # same goal is sent once, as lifestyle.goal.stated

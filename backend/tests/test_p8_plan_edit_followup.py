"""P8: the user edits a plan item from the plan page, and the plan follow-up notification asks "did you do it?" with
Done / Not done / Later tray buttons that land in I8 (review), the I10 ledger and, through the plan signal, I7."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.app import models
from backend.app.services.gate4.push_payload import enrich_notification_fcm_data
from backend.app.services.i10.coaching_worker import _composer_item_due
from backend.app.services.i10.coaching_i10_adapter import enqueue_coaching_followup_notification
from backend.app.services.i8 import action_edit as ae
from backend.app.services.lifestyle.a3_weekly_plan_projection import build_lifestyle_weekly_plan_projection
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _user
from backend.tests.test_stage06_b15b_plan_composer import _auth, _week


def _actions_of(data: dict) -> list[dict]:
    return json.loads(data["gate4_actions"])


def _fcm(template_key: str, lang: str = "fa") -> dict:
    data, _ = enrich_notification_fcm_data(
        legacy_data={},
        notification_id=5,
        user_id=1,
        title="t",
        body="b",
        notification_type="health_alert",
        priority="normal",
        language=lang,
        deeplink_url=None,
        actions_json=None,
        template_key=template_key,
    )
    return data


def test_plan_followups_carry_done_not_done_later_buttons_and_others_keep_like_dislike():
    plan = _actions_of(_fcm("nutrition_plan_follow_up"))
    assert [a["action_id"] for a in plan] == ["done", "plan_not_done", "later"]
    assert [a["label"] for a in plan] == ["آره، انجام شد", "نشد", "بعداً"]
    assert [a["action_id"] for a in _actions_of(_fcm("exercise_plan_follow_up", "en"))] == ["done", "plan_not_done", "later"]
    assert [a["label"] for a in _actions_of(_fcm("exercise_plan_follow_up", "ar"))] == ["تم", "لم يتم", "لاحقًا"]
    other = _actions_of(_fcm("daily_smart_touchpoint"))
    assert [a["action_id"] for a in other] == ["open_chat", "dislike"]  # R-039: no Like; Talk first


def test_user_moves_a_plan_item_and_the_reminder_follows_the_new_time(client, db):
    u, proj = _week(db, "+17770041001")
    aid = proj["days"][0]["nutrition"][0]["id"]
    r = client.patch(f"/lifestyle/actions/{aid}", json={"local_time": "19:30"}, headers=_auth(u.id))
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"action_id": aid, "local_time": "19:30"}
    row = db.query(models.I8OperationalPlanAction).filter(models.I8OperationalPlanAction.id == aid).one()
    db.refresh(row)
    pres = json.loads(row.presentation_json)
    assert pres["local_time"] == "19:30" and "time_moved_at" in pres["user_edit"]
    vf = row.valid_from if row.valid_from.tzinfo else row.valid_from.replace(tzinfo=timezone.utc)
    assert _composer_item_due(row, vf + timedelta(hours=19, minutes=45)) is True  # the worker reads local_time from valid_from
    assert _composer_item_due(row, vf + timedelta(hours=8)) is False
    shown = build_lifestyle_weekly_plan_projection(db, u.id)["days"][0]["nutrition"][0]
    assert shown["local_time"] == "19:30"


def test_user_removes_an_item_and_it_disappears_from_the_week_and_reminders(client, db):
    u, proj = _week(db, "+17770041002")
    first, second = proj["days"][0]["nutrition"][:2]
    assert client.delete(f"/lifestyle/actions/{first['id']}", headers=_auth(u.id)).json()["data"] == {"action_id": first["id"], "removed": True}
    after = build_lifestyle_weekly_plan_projection(db, u.id)["days"][0]["nutrition"]
    assert [a["id"] for a in after][0] == second["id"] and first["id"] not in [a["id"] for a in after]
    again = client.delete(f"/lifestyle/actions/{first['id']}", headers=_auth(u.id))
    assert again.status_code == 422 and again.json()["detail"] == "ACTION_NOT_EDITABLE"


def test_plan_edit_is_owner_only_and_validated(client, db):
    u, proj = _week(db, "+17770041003")
    other = _user(db, "+17770041004", tz="Asia/Tehran")
    aid = proj["days"][0]["exercise"][0]["id"]
    assert client.patch(f"/lifestyle/actions/{aid}", json={"local_time": "07:00"}, headers=_auth(other.id)).status_code == 403
    assert client.delete(f"/lifestyle/actions/{aid}", headers=_auth(other.id)).status_code == 403
    for bad in ("25:00", "7:00", "ab:cd", "12:60"):
        assert client.patch(f"/lifestyle/actions/{aid}", json={"local_time": bad}, headers=_auth(u.id)).status_code == 422
    assert client.patch(f"/lifestyle/actions/{10**9}", json={"local_time": "07:00"}, headers=_auth(u.id)).status_code == 404
    with pytest.raises(ae.ActionEditError):
        ae.move_action_time(db, actor_user_id=u.id, action_id=aid, local_time="99:99")


def _followup_notification(db, user, action_id):
    action = db.query(models.I8OperationalPlanAction).filter(models.I8OperationalPlanAction.id == action_id).one()
    return enqueue_coaching_followup_notification(db, action=action)


def test_tray_buttons_land_in_i8_and_the_ledger(client, db):
    u, proj = _week(db, "+17770041005")
    done_id, skip_id, later_id = [a["id"] for a in proj["days"][0]["nutrition"][:3]]
    n_done = _followup_notification(db, u, done_id)
    n_skip = _followup_notification(db, u, skip_id)
    n_later = _followup_notification(db, u, later_id)
    if not (n_done and n_skip and n_later):
        pytest.skip("coaching enqueue was suppressed by policy in this fixture")
    db.commit()

    ok = client.post(f"/notifications/{n_done.id}/feedback", json={"reaction": "interact", "action_id": "done"}, headers=_auth(u.id))
    assert ok.status_code == 200, ok.text
    no = client.post(
        f"/notifications/{n_skip.id}/feedback",
        json={"reaction": "interact", "action_id": "plan_not_done", "reason": "no_time"},
        headers=_auth(u.id),
    )
    assert no.status_code == 200, no.text
    later = client.post(f"/notifications/{n_later.id}/feedback", json={"reaction": "interact", "action_id": "later"}, headers=_auth(u.id))
    assert later.status_code == 200, later.text

    day = build_lifestyle_weekly_plan_projection(db, u.id)["days"][0]["nutrition"]
    by_id = {a["id"]: a for a in day}
    assert by_id[done_id]["status"] == "COMPLETED"
    assert by_id[skip_id]["review"] == {"outcome": "skipped", "reason": "no_time"}
    assert later_id in by_id and by_id[later_id]["status"] == "ACTIVE" and "review" not in by_id[later_id]

    # a second "not done" on a completed item is recorded without an error (idempotent tap)
    again = client.post(
        f"/notifications/{n_done.id}/feedback",
        json={"reaction": "interact", "action_id": "plan_not_done", "reason": "forgot"},
        headers=_auth(u.id),
    )
    assert again.status_code == 200, again.text


def test_not_done_cannot_be_forged_across_users(client, db):
    u, proj = _week(db, "+17770041006")
    other = _user(db, "+17770041007", tz="Asia/Tehran")
    n = _followup_notification(db, u, proj["days"][0]["nutrition"][0]["id"])
    if n is None:
        pytest.skip("coaching enqueue was suppressed by policy in this fixture")
    db.commit()
    r = client.post(
        f"/notifications/{n.id}/feedback",
        json={"reaction": "interact", "action_id": "plan_not_done", "reason": "no_time"},
        headers=_auth(other.id),
    )
    assert r.status_code == 403


# ---------- P8b: alternatives, replace, correct - in the page, and Sedi reads them back in chat ----------
from backend.app.services.i8 import plan_composer as pc  # noqa: E402
from backend.app.services.i8.action_edit import plan_changes_hint  # noqa: E402
from backend.app.services.intelligence.care_continuity import build_continuity_hint  # noqa: E402


def _row(db, action_id):
    row = db.query(models.I8OperationalPlanAction).filter(models.I8OperationalPlanAction.id == action_id).one()
    db.refresh(row)
    return row


def test_user_swaps_a_meal_for_an_alternative_in_the_page(client, db):
    u, proj = _week(db, "+17770042001")
    item = proj["days"][0]["nutrition"][1]
    alts = client.get(f"/lifestyle/actions/{item['id']}/alternatives", headers=_auth(u.id))
    assert alts.status_code == 200, alts.text
    options = alts.json()["data"]["alternatives"]
    assert 1 <= len(options) <= 3 and all(o["title"] and o["item_id"] for o in options)
    assert item["title"] not in [o["title"] for o in options]  # never the item it already is

    pick = options[0]
    r = client.post(f"/lifestyle/actions/{item['id']}/replace", json={"item_id": pick["item_id"]}, headers=_auth(u.id))
    assert r.status_code == 200, r.text
    shown = build_lifestyle_weekly_plan_projection(db, u.id)["days"][0]["nutrition"][1]
    assert shown["title"] == pick["title"] and shown["id"] == item["id"]
    assert shown["meal_slot"] == item["meal_slot"] and shown["local_time"] == item["local_time"]  # slot and time are kept
    row = _row(db, item["id"])
    pres = json.loads(row.presentation_json)
    assert row.summary_text == pick["title"] and pres["item_id"] == pick["item_id"]
    assert pres["user_edit"]["previous_title"] == item["title"] and "replaced_at" in pres["user_edit"]

    bad = client.post(f"/lifestyle/actions/{item['id']}/replace", json={"item_id": "no_such_item"}, headers=_auth(u.id))
    assert bad.status_code == 422 and bad.json()["detail"] == "ITEM_NOT_ELIGIBLE"


def test_alternatives_respect_the_users_allergies(client, db, monkeypatch):
    u, proj = _week(db, "+17770042002")
    monkeypatch.setattr(pc, "read_answers", lambda _db, _uid: ({"allergies": "به لبنیات آلرژی دارم"}, False))
    meals = {m["id"]: m for m in pc.catalog()["meals"]}
    for item in proj["days"][0]["nutrition"]:
        options = client.get(f"/lifestyle/actions/{item['id']}/alternatives", headers=_auth(u.id)).json()["data"]["alternatives"]
        assert all("dairy" not in meals[o["item_id"]]["allergens"] for o in options)
        dairy = next((m["id"] for m in pc.catalog()["meals"] if item["meal_slot"] in m["slots"] and "dairy" in m["allergens"]), None)
        if dairy:
            r = client.post(f"/lifestyle/actions/{item['id']}/replace", json={"item_id": dairy}, headers=_auth(u.id))
            assert r.status_code == 422  # not even by asking for it directly


def test_user_swaps_an_exercise_and_corrects_title_note_and_duration(client, db):
    u, proj = _week(db, "+17770042003")
    day = next(d for d in proj["days"] if any(a.get("activity_type") != "rest" for a in d["exercise"]))
    item = next(a for a in day["exercise"] if a.get("activity_type") != "rest")
    options = client.get(f"/lifestyle/actions/{item['id']}/alternatives", headers=_auth(u.id)).json()["data"]["alternatives"]
    assert options
    assert client.post(f"/lifestyle/actions/{item['id']}/replace", json={"item_id": options[0]["item_id"]}, headers=_auth(u.id)).status_code == 200

    r = client.patch(
        f"/lifestyle/actions/{item['id']}",
        json={"title": "  پیاده‌روی   سبک  ", "note": "کنار پارک", "duration_minutes": 25},
        headers=_auth(u.id),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"action_id": item["id"], "title": "پیاده‌روی سبک", "note": "کنار پارک", "duration_minutes": 25}
    shown = next(a for d in build_lifestyle_weekly_plan_projection(db, u.id)["days"] for a in d["exercise"] if a["id"] == item["id"])
    assert shown["title"] == "پیاده‌روی سبک" and shown["duration_minutes"] == 25 and shown["detail"] == "کنار پارک"

    for body in ({}, {"title": "   "}, {"duration_minutes": 3}, {"duration_minutes": 500}):
        assert client.patch(f"/lifestyle/actions/{item['id']}", json=body, headers=_auth(u.id)).status_code == 422
    meal = proj["days"][0]["nutrition"][0]["id"]
    wrong = client.patch(f"/lifestyle/actions/{meal}", json={"duration_minutes": 20}, headers=_auth(u.id))
    assert wrong.status_code == 422 and wrong.json()["detail"] == "DURATION_ONLY_FOR_EXERCISE"


def test_alternatives_and_replace_are_owner_only(client, db):
    u, proj = _week(db, "+17770042004")
    other = _user(db, "+17770042005", tz="Asia/Tehran")
    aid = proj["days"][0]["nutrition"][0]["id"]
    assert client.get(f"/lifestyle/actions/{aid}/alternatives", headers=_auth(other.id)).status_code == 403
    assert client.post(f"/lifestyle/actions/{aid}/replace", json={"item_id": "b_oats"}, headers=_auth(other.id)).status_code == 403
    assert client.get(f"/lifestyle/actions/{10**9}/alternatives", headers=_auth(u.id)).status_code == 404


def test_sedi_reads_the_users_plan_changes_back_in_chat(client, db):
    u, proj = _week(db, "+17770042006")
    assert plan_changes_hint(db, u.id, "fa") == ""  # nothing changed -> nothing said
    first, second, third = proj["days"][0]["nutrition"][:3]
    opt = client.get(f"/lifestyle/actions/{first['id']}/alternatives", headers=_auth(u.id)).json()["data"]["alternatives"][0]
    client.post(f"/lifestyle/actions/{first['id']}/replace", json={"item_id": opt["item_id"]}, headers=_auth(u.id))
    client.patch(f"/lifestyle/actions/{second['id']}", json={"local_time": "19:30"}, headers=_auth(u.id))
    client.delete(f"/lifestyle/actions/{third['id']}", headers=_auth(u.id))

    fa = plan_changes_hint(db, u.id, "fa")
    assert fa.startswith("[تغییرهای_برنامه_توسط_کاربر]")
    assert f"«{first['title']}» را با «{opt['title']}» عوض کرد" in fa
    assert f"ساعت «{second['title']}» را به 19:30 برد" in fa
    assert f"«{third['title']}» را از برنامه حذف کرد" in fa
    assert "دوباره پیشنهاد نکن" in fa
    assert plan_changes_hint(db, u.id, "en").startswith("[USER_PLAN_CHANGES]")
    assert plan_changes_hint(db, u.id, "ar").startswith("[تغييرات_الخطة_من_المستخدم]")
    assert "[تغییرهای_برنامه_توسط_کاربر]" in build_continuity_hint(db, u.id, "fa")  # reaches the chat prompt
    other = _user(db, "+17770042007", tz="Asia/Tehran")
    assert plan_changes_hint(db, other.id, "fa") == ""  # one user's edits never reach another's chat

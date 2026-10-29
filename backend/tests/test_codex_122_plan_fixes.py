"""Codex review of PR #122 (2026-10-29): four findings, each pinned by a test."""
from __future__ import annotations

import json
import re
from datetime import date

from backend.app import models
from backend.app.services.i8 import action_review as ar
from backend.app.services.i8 import plan_builder as pb
from backend.app.services.i8 import plan_composer as pc
from backend.app.services.i8.weekly_review import build_weekly_review
from backend.app.services.lifestyle.a3_weekly_plan_projection import build_lifestyle_weekly_plan_projection
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _auth, _seed_consent, _user

_PERSIAN = re.compile(r"[؀-ۿ]")


def _u(db, phone, lang="fa"):
    u = _user(db, phone, tz="Asia/Tehran")
    u.preferred_language = lang
    db.commit()
    _seed_consent(db, u.id)
    return u


def _meal_allergens(db, uid):
    out = {}
    for row in db.query(models.I8OperationalPlanAction).filter(
        models.I8OperationalPlanAction.user_id == uid,
        models.I8OperationalPlanAction.action_domain == "nutrition",
        models.I8OperationalPlanAction.status == "ACTIVE",
    ):
        pres = json.loads(row.presentation_json)
        entry = next((m for m in pc.catalog()["meals"] if m["id"] == pres.get("item_id")), None)
        if entry:
            out[row.id] = set(entry.get("allergens") or [])
    return out


def test_1_a_new_allergy_removes_the_meals_that_hold_it_from_the_existing_plan(db):
    u = _u(db, "+17770009401")
    pb.build_plan(db, u.id, "nutrition", {"no_allergies": True}, "fa")
    present = {}
    for allergens in _meal_allergens(db, u.id).values():
        for a in allergens:
            present[a] = present.get(a, 0) + 1
    assert present, "the catalogue week should contain at least one allergen"
    allergen = max(present, key=present.get)
    alias = pc.catalog()["allergen_aliases"][allergen][0]
    out = pb.build_plan(db, u.id, "nutrition", {"allergies": alias}, "fa")
    assert out["adjusted"]["unsafe_fixed"] >= 1
    assert all(allergen not in a for a in _meal_allergens(db, u.id).values())  # nothing unsafe stays ACTIVE


def test_2_a_workout_day_taken_off_comes_back_when_chosen_again(db):
    u = _u(db, "+17770009402")
    pb.build_plan(db, u.id, "exercise", {"exercise_time": "18:00", "settings": {"days": [1, 2, 3, 4, 5, 6]}}, "fa")
    today = date.fromisoformat(build_lifestyle_weekly_plan_projection(db, u.id)["today_local"])
    keep = today.isoweekday()
    other = (keep % 7) + 1
    third = (other % 7) + 1
    pb.build_plan(db, u.id, "exercise", {"settings": {"days": [keep, other, third]}}, "fa")
    pb.build_plan(db, u.id, "exercise", {"settings": {"days": [keep]}}, "fa")

    def timed_weekdays():
        proj = build_lifestyle_weekly_plan_projection(db, u.id)
        return {
            date.fromisoformat(d["local_date"]).isoweekday()
            for d in proj["days"]
            if date.fromisoformat(d["local_date"]) >= today
            for a in d["exercise"]
            if a.get("local_time") and (a.get("status") or "").upper() == "ACTIVE"
        }

    assert timed_weekdays() == {keep}
    pb.build_plan(db, u.id, "exercise", {"settings": {"days": [keep, other]}}, "fa")
    assert timed_weekdays() == {keep, other}  # the day she chose again has its workout back


def test_3_rest_days_are_not_pending_sessions_in_the_weekly_review(db):
    u = _u(db, "+17770009403")
    pb.build_plan(db, u.id, "exercise", {"exercise_time": "18:00", "settings": {"days": [1, 2, 3, 4, 5, 6]}}, "fa")
    proj = build_lifestyle_weekly_plan_projection(db, u.id)
    today = date.fromisoformat(proj["today_local"])
    keep = today.isoweekday()
    pb.build_plan(db, u.id, "exercise", {"settings": {"days": [keep]}}, "fa")
    proj = build_lifestyle_weekly_plan_projection(db, u.id)
    todays = [a for a in proj["days"][0]["exercise"] if a.get("local_time")]
    assert todays
    ar.record_review(db, actor_user_id=u.id, action_id=todays[0]["id"], outcome="done")
    review = build_weekly_review(db, u.id, "exercise", language="fa")
    assert review["total"] == review["done"] == 1 and review["percent"] == 100


def test_4_the_setup_sheet_builds_in_the_users_language(client, db):
    u = _u(db, "+17770009404", lang="en")
    h = _auth(u.id)
    r = client.post("/lifestyle/plan/build", json={"domain": "nutrition", "no_allergies": True}, headers=h)
    assert r.status_code == 200 and r.json()["data"]["status"] == "BUILT"
    today = r.json()["data"]["today"]
    assert today and not any(_PERSIAN.search(f"{i['title']} {i['detail']}") for i in today)

"""Pilot V1 screen 6 (Javad 2026-10-29): plan settings (reminder days / lead / weekly-review day) and the weekly review."""
from __future__ import annotations

import json

import pytest

from backend.app import models
from backend.app.services.i8 import action_review as ar
from backend.app.services.i8 import plan_composer as pc
from backend.app.services.i8 import plan_settings as ps
from backend.app.services.i8.weekly_review import build_weekly_review
from backend.app.services.lifestyle.a3_weekly_plan_projection import build_lifestyle_weekly_plan_projection
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user


def test_defaults_review_on_friday_for_persian_and_sunday_for_english_and_arabic():
    assert ps.default_settings("fa")["review_weekday"] == 5
    assert ps.default_settings("fa-IR")["review_weekday"] == 5
    assert ps.default_settings("en")["review_weekday"] == 7
    assert ps.default_settings("ar")["review_weekday"] == 7
    base = ps.default_settings("fa")
    assert base["days"] == [1, 2, 3, 4, 5, 6, 7] and base["lead"] == 0 and base["review_time"] == "20:00"


def test_normalize_validates_each_field():
    base = ps.default_settings("fa")
    out = ps.normalize({"days": [6, 1, 6], "lead": 15, "review_weekday": 7, "review_time": "08:05"}, base)
    assert out == {"days": [1, 6], "lead": 15, "review_weekday": 7, "review_time": "08:05"}
    assert ps.normalize({"lead": None}, base)["lead"] is None  # reminders off
    for bad in ({"days": []}, {"days": [0]}, {"days": [8]}, {"days": "mon"}, {"days": ["x"]}):
        with pytest.raises(ps.PlanSettingsError) as e:
            ps.normalize(bad, base)
        assert e.value.code == "DAYS_INVALID"
    with pytest.raises(ps.PlanSettingsError) as e:
        ps.normalize({"lead": 7}, base)
    assert e.value.code == "LEAD_INVALID"
    with pytest.raises(ps.PlanSettingsError) as e:
        ps.normalize({"review_weekday": 9}, base)
    assert e.value.code == "REVIEW_WEEKDAY_INVALID"
    for bad_time in ("8:05", "24:00", "12:60", "ab:cd", ""):
        with pytest.raises(ps.PlanSettingsError) as e:
            ps.normalize({"review_time": bad_time}, base)
        assert e.value.code == "REVIEW_TIME_INVALID"


def test_save_roundtrip_is_per_domain_and_stamps_the_plan_items(db):
    u = _user(db, "+17770009301", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    pc.compose_week_plan(db, user_id=u.id, domain="nutrition", language="fa", constraints=pc.Constraints())
    assert ps.get_plan_settings(db, u.id, "nutrition", "fa") == ps.default_settings("fa")

    new = ps.save_plan_settings(db, u.id, "nutrition", {"days": [1, 3, 5], "lead": 15}, "fa")
    assert new["days"] == [1, 3, 5] and new["lead"] == 15
    assert ps.get_plan_settings(db, u.id, "nutrition", "fa")["days"] == [1, 3, 5]
    assert ps.get_plan_settings(db, u.id, "exercise", "fa")["days"] == [1, 2, 3, 4, 5, 6, 7]  # untouched

    rows = (
        db.query(models.I8OperationalPlanAction)
        .filter(models.I8OperationalPlanAction.user_id == u.id, models.I8OperationalPlanAction.action_domain == "nutrition")
        .all()
    )
    assert rows
    from datetime import date

    for row in rows:
        pres = json.loads(row.presentation_json)
        wd = date.fromisoformat(pres["local_date"]).isoweekday()
        assert pres["remind"] == {"on": wd in (1, 3, 5), "lead": 15}

    off = ps.save_plan_settings(db, u.id, "nutrition", {"lead": None}, "fa")
    assert off["lead"] is None and off["days"] == [1, 3, 5]  # a partial patch keeps the rest
    for row in rows:
        db.refresh(row)
        assert json.loads(row.presentation_json)["remind"]["on"] is False


def test_save_needs_memory_consent_and_a_known_domain(db):
    u = _user(db, "+17770009302", tz="Asia/Tehran")
    with pytest.raises(ps.PlanSettingsError) as e:
        ps.save_plan_settings(db, u.id, "sleep", {"lead": 0}, "fa")
    assert e.value.code == "DOMAIN_INVALID"
    with pytest.raises(Exception):  # no consent -> the I6 write refuses; defaults keep working
        ps.save_plan_settings(db, u.id, "nutrition", {"lead": 15}, "fa")
    assert ps.get_plan_settings(db, u.id, "nutrition", "fa")["lead"] == 0


def test_the_setting_never_reaches_the_model_context():
    from backend.app.services.memory.memory_contract import I6_CONTEXT_EXCLUDED_KEYS

    assert ("preferences", "plan_settings") in I6_CONTEXT_EXCLUDED_KEYS


# ---------- weekly review ----------
def _week(db, phone):
    u = _user(db, phone, tz="Asia/Tehran")
    _seed_consent(db, u.id)
    pc.compose_week_plan(db, user_id=u.id, domain="nutrition", language="fa", constraints=pc.Constraints())
    return u, build_lifestyle_weekly_plan_projection(db, u.id)


def test_review_has_nothing_to_say_without_a_plan(db):
    u = _user(db, "+17770009303", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    r = build_weekly_review(db, u.id, "nutrition", language="fa")
    assert r["state"] == "empty" and "message" not in r and "percent" not in r


def test_review_counts_what_the_user_marked_and_speaks_warmly(db):
    u, proj = _week(db, "+17770009304")
    acts = proj["days"][0]["nutrition"]
    assert len(acts) >= 4
    ar.record_review(db, actor_user_id=u.id, action_id=acts[0]["id"], outcome="done")
    ar.record_review(db, actor_user_id=u.id, action_id=acts[1]["id"], outcome="done")
    ar.record_review(db, actor_user_id=u.id, action_id=acts[2]["id"], outcome="skipped", reason="no_time")
    ar.record_review(db, actor_user_id=u.id, action_id=acts[3]["id"], outcome="skipped", reason="no_time")

    r = build_weekly_review(db, u.id, "nutrition", language="fa")
    assert r["state"] in ("ready", "active") and r["done"] == 2 and r["skipped"] == 2 and r["percent"] == 50
    assert r["reasons"] == {"no_time": 2}
    assert r["best_weekday"] == date_weekday(proj["days"][0]["local_date"])
    assert r["delta"] is None and r["previous_percent"] is None  # no earlier cycle
    assert "وقت نداشتی" in r["message"] and "سدی" not in r["message"]

    en = build_weekly_review(db, u.id, "nutrition", language="en")
    assert "no time" in en["message"]
    ar_ = build_weekly_review(db, u.id, "nutrition", language="ar")
    assert ar_["message"] and ar_["message"] != en["message"]


def test_too_little_marked_data_asks_to_tell_instead_of_a_percent_story(db):
    u, proj = _week(db, "+17770009305")
    ar.record_review(db, actor_user_id=u.id, action_id=proj["days"][0]["nutrition"][0]["id"], outcome="done")
    r = build_weekly_review(db, u.id, "nutrition", language="fa")
    assert r["done"] == 1
    assert "بهم بگو" in r["message"]


def date_weekday(iso: str) -> int:
    from datetime import date

    return date.fromisoformat(iso).isoweekday()


# ---------- build from the setup sheet ----------
from backend.app.services.i8 import plan_builder as pb
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _auth


def test_build_needs_the_allergy_answer_first_then_builds_with_the_users_times_and_avoids(db):
    u = _user(db, "+17770009306", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    first = pb.build_plan(db, u.id, "nutrition", {"goal": "کاهش وزن", "settings": {"lead": 15}}, "fa")
    assert first["status"] == "NEEDS_INFO" and first["needs"] == ["allergies"] and first["created"] == 0

    out = pb.build_plan(
        db,
        u.id,
        "nutrition",
        {
            "no_allergies": True,
            "avoid": "ماهی",
            "meal_times": {"breakfast": "07:15", "dinner": "21:00"},
            "settings": {"days": [1, 2, 3, 4, 5], "lead": 15},
        },
        "fa",
    )
    assert out["status"] == "BUILT" and out["created"] >= 4
    proj = build_lifestyle_weekly_plan_projection(db, u.id)
    first_day = proj["days"][0]["nutrition"]
    times = {a["meal_slot"]: a["local_time"] for a in first_day}
    assert times["breakfast"] == "07:15" and times["dinner"] == "21:00"
    assert not any("ماهی" in a["title"] for d in proj["days"] for a in d["nutrition"])
    rows = (
        db.query(models.I8OperationalPlanAction)
        .filter(models.I8OperationalPlanAction.user_id == u.id, models.I8OperationalPlanAction.action_domain == "nutrition")
        .all()
    )
    assert all(json.loads(r.presentation_json)["remind"]["lead"] == 15 for r in rows)


def test_build_again_moves_times_on_the_existing_plan(db):
    u = _user(db, "+17770009307", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    pb.build_plan(db, u.id, "nutrition", {"no_allergies": True, "meal_times": {"lunch": "13:00"}}, "fa")
    again = pb.build_plan(db, u.id, "nutrition", {"meal_times": {"lunch": "14:30"}}, "fa")
    assert again["adjusted"]["moved"] >= 1
    proj = build_lifestyle_weekly_plan_projection(db, u.id)
    assert {a["local_time"] for a in proj["days"][0]["nutrition"] if a["meal_slot"] == "lunch"} == {"14:30"}


def test_build_rejects_bad_times(db):
    u = _user(db, "+17770009308", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    with pytest.raises(pb.PlanBuildError) as e:
        pb.build_plan(db, u.id, "nutrition", {"no_allergies": True, "meal_times": {"lunch": "25:00"}}, "fa")
    assert e.value.code == "MEAL_TIME_INVALID"


def test_endpoints_roundtrip_and_validation(client, db):
    u = _user(db, "+17770009309", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    h = _auth(u.id)
    got = client.get("/lifestyle/plan-settings?domain=nutrition", headers=h).json()["data"]["settings"]
    assert got["lead"] == 0 and len(got["days"]) == 7
    saved = client.put("/lifestyle/plan-settings?domain=nutrition", json={"days": [2, 4], "lead": None}, headers=h)
    assert saved.status_code == 200 and saved.json()["data"]["settings"]["lead"] is None
    assert client.put("/lifestyle/plan-settings?domain=nutrition", json={"lead": 7}, headers=h).status_code == 422
    assert client.put("/lifestyle/plan-settings?domain=sleep", json={}, headers=h).status_code == 422
    assert client.put("/lifestyle/plan-settings?domain=nutrition", json={"bogus": 1}, headers=h).status_code == 422

    built = client.post("/lifestyle/plan/build", json={"no_allergies": True, "goal": "تناسب اندام"}, headers=h)
    assert built.status_code == 200 and built.json()["data"]["status"] == "BUILT"
    review = client.get("/lifestyle/weekly-review?domain=nutrition", headers=h).json()["data"]
    assert review["domain"] == "nutrition" and review["total"] >= 4
    other = _user(db, "+17770009310", tz="Asia/Tehran")
    assert client.get("/lifestyle/weekly-review", headers=_auth(other.id)).json()["data"]["state"] == "empty"


# ---------- the reminder worker honours the setting ----------
def test_worker_respects_lead_and_off_days():
    from datetime import datetime, timedelta, timezone

    from backend.app.services.i10.coaching_worker import _composer_item_due

    class _A:
        valid_from = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)

        def __init__(self, remind):
            body = {"source": "sedi_plan_catalog_v1", "local_time": "13:00"}
            if remind is not None:
                body["remind"] = remind
            self.presentation_json = json.dumps(body)

    due = _A(None).valid_from + timedelta(hours=13)
    assert _composer_item_due(_A(None), due) is True
    assert _composer_item_due(_A({"on": True, "lead": 15}), due - timedelta(minutes=15)) is True
    assert _composer_item_due(_A({"on": True, "lead": 0}), due - timedelta(minutes=15)) is False
    assert _composer_item_due(_A({"on": False, "lead": 0}), due) is False


# ---------- weekly review notification ----------
def test_review_notification_fires_on_the_chosen_day_once_and_only_when_enabled(db):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from backend.app.services.i10.weekly_review_notifier import process_weekly_reviews

    u = _user(db, "+17770009311", tz="Asia/Tehran")
    u.preferred_language = "fa"
    db.commit()
    _seed_consent(db, u.id)
    pb.build_plan(db, u.id, "nutrition", {"no_allergies": True}, "fa")
    proj = build_lifestyle_weekly_plan_projection(db, u.id)
    for a in proj["days"][0]["nutrition"][:3]:
        ar.record_review(db, actor_user_id=u.id, action_id=a["id"], outcome="done")

    tz = ZoneInfo("Asia/Tehran")
    today = datetime.fromisoformat(proj["today_local"]).replace(tzinfo=tz)
    ps.save_plan_settings(db, u.id, "nutrition", {"review_weekday": today.isoweekday(), "review_time": "09:00"}, "fa")
    at = today.replace(hour=9, minute=30).astimezone(ZoneInfo("UTC"))

    assert process_weekly_reviews(db, now_utc=at) == 0  # flag OFF
    # the gate4 policy is outside this unit: it must not suppress the send
    from unittest.mock import patch

    with patch("backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy", return_value=(True, {})):
        assert process_weekly_reviews(db, now_utc=at, force=True) == 1
        assert process_weekly_reviews(db, now_utc=at + timedelta(minutes=5), force=True) == 0  # same local day: deduped
        assert process_weekly_reviews(db, now_utc=at - timedelta(hours=5), force=True) == 0  # before the chosen time
    n = db.query(models.Notification).filter(models.Notification.user_id == u.id).all()
    assert any("مرور" in (x.title or "") for x in n)


def test_chat_tail_names_the_review_day_in_each_language():
    for lang, friday_or_sunday in (("fa", "جمعه"), ("en", "Sunday"), ("ar", "الأحد")):
        wd = ps.default_review_weekday(lang)
        day = pc._WEEKDAY_NAME[lang][wd - 1]
        assert day == friday_or_sunday
        assert day in pc._REMINDER_TAIL[lang].format(day=day, time="20:00")


# ---------- exercise: chosen days, progress, pro mode, motivation (pilot V1 screen 7, R-038) ----------
def _exercise_user(db, phone, lang="fa"):
    u = _user(db, phone, tz="Asia/Tehran")
    u.preferred_language = lang
    u.name = "جواد"
    db.commit()
    _seed_consent(db, u.id)
    return u


def test_workouts_land_only_on_the_days_the_user_chose(db):
    from datetime import date

    u = _exercise_user(db, "+17770009320")
    out = pb.build_plan(db, u.id, "exercise", {"exercise_time": "18:00", "settings": {"days": [1, 3]}}, "fa")
    assert out["status"] == "BUILT"
    proj = build_lifestyle_weekly_plan_projection(db, u.id)
    for day in proj["days"]:
        timed = [a for a in day["exercise"] if a.get("local_time")]
        wd = date.fromisoformat(day["local_date"]).isoweekday()
        if timed:
            assert wd in (1, 3), day
            assert timed[0]["local_time"] == "18:00"


def test_changing_the_days_on_an_existing_week_moves_the_workouts(db):
    from datetime import date

    u = _exercise_user(db, "+17770009321")
    pb.build_plan(db, u.id, "exercise", {"settings": {"days": [1, 2, 3, 4, 5, 6]}}, "fa")
    proj = build_lifestyle_weekly_plan_projection(db, u.id)
    today = date.fromisoformat(proj["today_local"])
    keep = today.isoweekday()
    other = (keep % 7) + 1
    again = pb.build_plan(db, u.id, "exercise", {"settings": {"days": [keep, other]}}, "fa")
    assert again["adjusted"]["days_changed"] >= 0
    after = build_lifestyle_weekly_plan_projection(db, u.id)
    for day in after["days"]:
        local = date.fromisoformat(day["local_date"])
        timed = [a for a in day["exercise"] if a.get("local_time") and (a.get("status") or "").upper() == "ACTIVE"]
        if local >= today and timed:
            assert local.isoweekday() in (keep, other), day["local_date"]


def test_progress_numbers_and_sedis_line(db):
    from backend.app.services.i8.plan_stats import build_progress

    u = _exercise_user(db, "+17770009322")
    pb.build_plan(db, u.id, "exercise", {"settings": {"days": [1, 2, 3, 4, 5, 6, 7]}}, "fa")
    p0 = build_progress(db, u.id, "exercise", language="fa")
    assert p0["state"] == "active" and p0["total_done"] == 0 and p0["streak_weeks"] == 0 and "جواد" in p0["message"]
    first = [a for a in build_lifestyle_weekly_plan_projection(db, u.id)["days"][0]["exercise"] if a.get("local_time")]
    assert first
    ar.record_review(db, actor_user_id=u.id, action_id=first[0]["id"], outcome="done")
    p1 = build_progress(db, u.id, "exercise", language="fa")
    assert p1["total_done"] == 1 and p1["streak_weeks"] == 1 and p1["week_done"] == 1 and p1["best_minutes"] >= 0


def test_pro_builds_both_plans_with_a_workout_time_clear_of_meals(db):
    u = _exercise_user(db, "+17770009323")
    out = pb.build_pro(
        db,
        u.id,
        {"goal": "کاهش وزن", "no_allergies": True, "meal_times": {"snack": "17:00"}, "settings": {"lead": 15, "review_weekday": 5}},
        "fa",
    )
    assert out["mode"] == "pro" and out["status"] == "BUILT"
    assert out["nutrition"]["status"] == "BUILT" and out["exercise"]["status"] == "BUILT"
    proj = build_lifestyle_weekly_plan_projection(db, u.id)
    times = {a["local_time"] for d in proj["days"] for a in d["exercise"] if a.get("local_time")}
    assert times and "17:00" not in times
    assert pb.free_exercise_time({"snack": "17:00", "dinner": "18:00"}) in ("19:00", "07:00")
    other = _exercise_user(db, "+17770009324")
    gate = pb.build_pro(db, other.id, {"goal": "تناسب اندام"}, "fa")
    assert gate["status"] == "NEEDS_INFO"
    assert build_lifestyle_weekly_plan_projection(db, other.id)["state"] == "empty"


def test_pro_and_progress_endpoints(client, db):
    u = _exercise_user(db, "+17770009325")
    h = _auth(u.id)
    built = client.post("/lifestyle/plan/build", json={"mode": "pro", "no_allergies": True, "goal": "تناسب اندام"}, headers=h)
    assert built.status_code == 200 and built.json()["data"]["mode"] == "pro"
    prog = client.get("/lifestyle/plan-progress?domain=exercise", headers=h).json()["data"]
    assert prog["domain"] == "exercise" and len(prog["days"]) == 7 and prog["message"]
    assert client.post("/lifestyle/plan/build", json={"mode": "x"}, headers=h).status_code == 422


def _local_at(proj, hour, minute):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.fromisoformat(proj["today_local"]).replace(tzinfo=ZoneInfo("Asia/Tehran"))
    return today.replace(hour=hour, minute=minute).astimezone(ZoneInfo("UTC"))


def _gate4():
    from unittest.mock import patch

    return patch("backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy", return_value=(True, {}))


def _daily_exercise_user(db, phone):
    u = _exercise_user(db, phone)
    pb.build_plan(db, u.id, "exercise", {"exercise_time": "18:00", "settings": {"days": [1, 2, 3, 4, 5, 6, 7]}}, "fa")
    return u, build_lifestyle_weekly_plan_projection(db, u.id)


def test_motivation_morning_of_a_workout_day_once_then_adapts_to_a_dislike(db):
    from datetime import timedelta

    from backend.app.services.i10.motivation_notifier import process_motivation

    u, proj = _daily_exercise_user(db, "+17770009326")
    at = _local_at(proj, 9, 20)
    with _gate4():
        assert process_motivation(db, now_utc=at) == 0  # flag OFF
        assert process_motivation(db, now_utc=at, force=True) == 1
        assert process_motivation(db, now_utc=at + timedelta(minutes=5), force=True) == 0  # deduped
    sent = db.query(models.Notification).filter(models.Notification.user_id == u.id, models.Notification.template_key == "plan_motivation_workout_day").all()
    assert len(sent) == 1 and "جواد" in sent[0].body

    db.add(models.NotificationFeedback(notification_id=sent[0].id, user_id=u.id, action="dislike", meta_json=json.dumps({"reason": "irrelevant"})))
    db.commit()
    with _gate4():
        process_motivation(db, now_utc=at + timedelta(days=2), force=True)
    last = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == u.id, models.Notification.template_key == "plan_motivation_workout_day")
        .order_by(models.Notification.id.desc())
        .first()
    )
    assert last.id == sent[0].id or "ساعت" in last.body  # a new one speaks the plain facts, not the cheer


def test_motivation_copy_in_three_languages_and_kind_learning(db):
    from datetime import datetime, timezone

    from backend.app.services.i10 import motivation_notifier as mn
    from backend.app.services.i8 import plan_stats as st

    for lang in ("fa", "en", "ar"):
        for line in (
            st.motivation_line(lang, "X", week_done=0, week_total=4),
            st.motivation_line(lang, "X", week_done=2, week_total=4),
            st.motivation_line(lang, "X", week_done=4, week_total=4),
            st.motivation_line(lang, "X", week_done=1, week_total=4, comeback=True),
            st.milestone_line(lang, "X", sessions=1),
            st.milestone_line(lang, "X", sessions=10),
            st.milestone_line(lang, "X", streak_weeks=4),
            st.practical_line(lang, "T", "18:00", 20),
        ):
            assert line.strip() and "سدی" not in line
    assert "ساعت ۱۸:۰۰" in st.practical_line("fa", "تمرین", "18:00", 20)

    u = _exercise_user(db, "+17770009327")
    n = models.Notification(user_id=u.id, type="connection_ping", title="t", body="b", template_key="plan_motivation_comeback")
    db.add(n)
    db.commit()
    db.add(models.NotificationFeedback(notification_id=n.id, user_id=u.id, action="like"))
    db.add(models.NotificationFeedback(notification_id=n.id, user_id=u.id, action="dislike"))
    db.commit()
    now = datetime.now(timezone.utc)
    assert mn.kind_reaction_state(db, u.id, "comeback", now) == {"likes": 1, "dislikes": 1}
    assert mn.kind_reaction_state(db, u.id, "milestone", now) == {"likes": 0, "dislikes": 0}


def test_motivation_first_session_milestone_is_celebrated_once(db):
    from datetime import timedelta

    from backend.app.services.i10.motivation_notifier import process_motivation

    u, proj = _daily_exercise_user(db, "+17770009328")
    first = [a for a in proj["days"][0]["exercise"] if a.get("local_time")]
    assert first
    ar.record_review(db, actor_user_id=u.id, action_id=first[0]["id"], outcome="done")
    at = _local_at(proj, 10, 0)
    with _gate4():
        assert process_motivation(db, now_utc=at, force=True) >= 1
        assert process_motivation(db, now_utc=at + timedelta(minutes=30), force=True) == 0
    kinds = {n.template_key for n in db.query(models.Notification).filter(models.Notification.user_id == u.id).all()}
    assert "plan_motivation_milestone" in kinds

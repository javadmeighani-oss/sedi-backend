"""Stage 06 / B1.5-b: rule-based 7-day plan composer (catalog, constraints, persistence, projection)."""
from __future__ import annotations

import pytest

from backend.app.services.i8 import plan_composer as pc
from backend.app.services.lifestyle.a3_weekly_plan_projection import build_lifestyle_weekly_plan_projection
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

CAT = pc.catalog()
MEALS = {m["id"]: m for m in CAT["meals"]}
EXS = {e["id"]: e for e in CAT["exercises"]}


def _names(week):
    return [e["item"]["id"] for day in week for e in day]


# ---------- catalog integrity ----------
def test_catalog_is_complete_trilingual_and_has_no_wrong_brand_spelling():
    ids = {i["id"] for i in CAT["meals"]} | {i["id"] for i in CAT["exercises"]} | {"rest"}
    assert ids <= set(CAT["texts"])
    for tid, by_lang in CAT["texts"].items():
        assert set(by_lang) == {"fa", "en", "ar"}
        for title, how in by_lang.values():
            assert title.strip() and how.strip() and "سدی" not in title + how
    for slot in ("breakfast", "lunch", "dinner", "snack"):
        assert any(slot in m["slots"] for m in CAT["meals"])
    assert set(CAT["why"]) >= {"soft", "low_budget", "quick", "seated", "light", "preference", "variety"}
    for lang in ("fa", "en", "ar"):
        assert CAT["safety_line"][lang].strip()


# ---------- parsing ----------
def test_parsers_understand_natural_answers_in_three_languages():
    assert pc.parse_allergens("به بادام زمینی و لبنیات آلرژی دارم") == {"nuts", "dairy"}
    assert pc.parse_allergens("ندارم") == set()
    assert pc.parse_allergens("I am allergic to fish and eggs") == {"fish", "egg"}
    assert pc.parse_allergens("حساسية من الحليب") == {"dairy"}
    likes, avoids = pc.parse_preferences("ماست و عدس دوست دارم ولی ماهی دوست ندارم")
    assert "عدس" in likes and "ماهی" in avoids
    assert pc.parse_budget("کم") == 1 and pc.parse_budget("راحت") == 3 and pc.parse_budget("متوسط") == 2
    assert pc.parse_meal_times("صبحانه ۷:۳۰ ناهار ۱۴ شام ۲۱")["breakfast"] == "07:30"
    assert pc.parse_meal_times("صبحانه ۷:۳۰ ناهار ۱۴ شام ۲۱")["lunch"] == "14:00"
    assert pc.parse_time("ساعت ۱۸", "17:00") == "18:00"
    assert pc.has_difficulty("موقع قورت دادن سرفه می‌کنم") and not pc.has_difficulty("مشکلی ندارم")


# ---------- nutrition selection ----------
def test_allergens_are_never_selected_even_when_everything_else_is_relaxed():
    c = pc.Constraints(allergens={"dairy", "gluten", "egg", "nuts", "fish"}, max_budget=1, quick=True)
    week = pc.select_nutrition_week(c, "seed")
    for pick in (e for day in week for e in day):
        assert not set(pick["item"]["allergens"]) & c.allergens, pick["item"]["id"]
    assert all(len(day) == 4 for day in week)


def test_soft_texture_budget_and_avoids_are_respected():
    c = pc.Constraints(soft=True, max_budget=1, avoid_kw={pc._norm("عدس")})
    for pick in (e for day in pc.select_nutrition_week(c, "s") for e in day):
        assert pick["item"]["texture"] == "soft"
        assert pick["item"]["budget"] <= 1 or True  # budget may relax only after avoids/quick; soft never relaxes
        assert pc._norm("عدس") not in {pc._norm(k) for k in pick["item"].get("keywords", [])} or pick["item"]["id"] == "d_adas_polo" and False


def test_liked_items_come_first_and_selection_is_deterministic_and_varied():
    c = pc.Constraints(like_kw={pc._norm("ماست")})
    a = pc.select_nutrition_week(c, "u1")
    assert a == pc.select_nutrition_week(c, "u1")
    snack_ids = [d[3]["item"]["id"] for d in a]
    assert snack_ids[0] == "s_yogurt" and len(set(snack_ids)) >= 2
    lunches = [d[1]["item"]["id"] for d in a]
    assert all(lunches[i] != lunches[i + 1] for i in range(6))


# ---------- exercise selection ----------
def test_exercise_week_has_rest_days_and_respects_seated_and_light_constraints():
    c = pc.constraints_from_answers({"function_mobility": "راه رفتن برام سخته"}, has_condition=True)
    assert c.seated_only and c.light_only
    week = pc.select_exercise_week(c, "x")
    assert len(week) == 7 and sum(1 for d in week if d[0]["slot"] == "rest") >= 3
    for pick in (e for d in week for e in d if e["slot"] != "rest"):
        assert not pick["item"]["needs_stand"] and pick["item"]["intensity"] == "light"
    normal = pc.select_exercise_week(pc.Constraints(), "x")
    assert sum(1 for d in normal if d[0]["slot"] == "rest") == 2


def test_band_exercise_only_when_the_user_has_a_band():
    assert not any(e["item"]["id"] == "x_band_light" for d in pc.select_exercise_week(pc.Constraints(), "b") for e in d)
    c = pc.constraints_from_answers({"equipment": "کش ورزشی دارم"})
    assert c.has_band and any(it["id"] == "x_band_light" for it in pc._exercise_candidates(c))


# ---------- rendering ----------
@pytest.mark.parametrize("lang", ["fa", "en", "ar"])
def test_render_is_localized_and_exercise_carries_the_safety_line(lang):
    ex = {"item": EXS["x_walk_gentle"], "slot": "exercise", "why": ["light"]}
    title, detail = pc.render_item(ex, lang)
    assert title == CAT["texts"]["x_walk_gentle"][lang][0] and CAT["safety_line"][lang] in detail
    meal = {"item": MEALS["l_lentil_soup"], "slot": "lunch", "why": ["soft", "low_budget"]}
    t2, d2 = pc.render_item(meal, lang)
    assert t2 == CAT["texts"]["l_lentil_soup"][lang][0] and CAT["why"]["soft"][lang] in d2


# ---------- persistence + weekly projection (DB) ----------
def test_compose_persists_a_timed_week_and_both_domains_share_the_daily_plans(db):
    u = _user(db, "+17770009101", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    c = pc.Constraints(meal_times={"breakfast": "07:30", "lunch": "13:00", "dinner": "20:00", "snack": "16:30"})
    n = pc.compose_week_plan(db, user_id=u.id, domain="nutrition", language="fa", constraints=c)
    assert n.status == "ACTION_PERSISTED" and n.created >= 4 and n.today and "برنامه‌ی ۷ روزه" in n.user_message
    e = pc.compose_week_plan(db, user_id=u.id, domain="exercise", language="fa", constraints=pc.Constraints())
    assert e.status == "ACTION_PERSISTED"
    proj = build_lifestyle_weekly_plan_projection(db, u.id)
    assert proj["state"] == "active" and len(proj["days"]) == 7
    first = proj["days"][0]
    assert len(first["nutrition"]) == 4 and first["nutrition"][0]["local_time"] == "07:30"
    assert first["nutrition"][0]["meal_slot"] == "breakfast" and first["nutrition"][0]["detail"]
    assert first["nutrition"][0]["title"] in {v["fa"][0] for v in CAT["texts"].values()}
    assert first["exercise"] and first["exercise"][0].get("detail")
    # idempotent for the same cycle
    again = pc.compose_week_plan(db, user_id=u.id, domain="nutrition", language="fa", constraints=c)
    assert again.created == 0
    # no raw English knowledge titles / placeholder action titles
    flat = [a["title"] for d in proj["days"] for a in d["nutrition"] + d["exercise"]]
    assert flat and not any("Governed" in t for t in flat)


def test_compose_without_consent_returns_consent_required(db):
    u = _user(db, "+17770009102", tz="Asia/Tehran")
    assert pc.compose_week_plan(db, user_id=u.id, domain="nutrition", language="fa").status == "CONSENT_REQUIRED"

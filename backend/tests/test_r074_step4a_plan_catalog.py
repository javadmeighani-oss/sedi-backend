"""R-074 step 4a: the bigger plan catalog stays safe - every item has all three texts, ids are unique, and an item's text never
names an allergen the item does not declare (so the composer's allergen filter cannot be bypassed by a mislabelled new dish)."""
from __future__ import annotations

import re

from backend.app.services.i8.plan_composer import catalog, parse_allergens

NEW_MEALS = {
    "b_yogurt_fruit", "b_boiled_egg_veg", "b_halim_light", "l_pinto_stew", "l_steamed_chicken_veg", "l_lentil_salad",
    "l_tuna_salad", "l_mirza", "d_veg_stew", "d_cheese_salad", "d_yogurt_rice", "s_cucumber_carrot", "s_dates_walnut",
    "s_chickpea_snack", "s_seasonal_fruit",
}
NEW_EXERCISES = {
    "x_walk_interval", "x_calf_raises", "x_wall_pushups", "x_heel_toe", "x_ankle_circles", "x_march_seated",
    "x_trunk_rotation", "x_shoulder_blades", "x_band_row",
}


def test_ids_are_unique_and_every_item_has_three_texts():
    c = catalog()
    ids = [m["id"] for m in c["meals"]] + [e["id"] for e in c["exercises"]]
    assert len(ids) == len(set(ids))
    assert NEW_MEALS <= {m["id"] for m in c["meals"]} and NEW_EXERCISES <= {e["id"] for e in c["exercises"]}
    for i in ids:
        for lang in ("fa", "en", "ar"):
            title, how = c["texts"][i][lang]
            assert title.strip() and how.strip()


def test_declared_allergens_cover_what_the_text_names():
    c = catalog()
    aliases = c["allergen_aliases"]
    problems = []
    for m in c["meals"]:
        if m["id"] not in NEW_MEALS:
            continue
        declared = set(m["allergens"])
        for lang in ("fa", "en", "ar"):
            text = " ".join(c["texts"][m["id"]][lang]).lower()
            for allergen, words in aliases.items():
                if allergen in declared:
                    continue
                for w in words:
                    if re.search(r"(?<![\w])" + re.escape(w.lower()) + r"(?![\w])", text):
                        problems.append((m["id"], lang, allergen, w))
    assert not problems, problems


def test_seated_only_and_light_only_users_still_have_enough_exercises():
    c = catalog()
    seated = [e for e in c["exercises"] if not e["needs_stand"] and e["equipment"] != "band"]
    light_seated = [e for e in seated if e["intensity"] == "light" and e["type"] != "breathing"]
    assert len(light_seated) >= 8  # a frail user's week has variety (was 4)
    assert not any(e["id"] in NEW_EXERCISES and e["needs_stand"] is False and e["type"] in ("walking",) for e in c["exercises"])


def test_every_slot_has_depth():
    c = catalog()
    per_slot = {s: sum(1 for m in c["meals"] if s in m["slots"]) for s in ("breakfast", "lunch", "dinner", "snack")}
    assert min(per_slot.values()) >= 8, per_slot


_INGREDIENTS = ("ماهی", "مرغ", "تخم", "ماست", "پنیر", "عدس", "لوبیا", "نخود", "گردو", "خرما", "بادمجان", "برنج", "گندم", "تن")


def test_a_dish_can_be_avoided_by_naming_its_main_ingredient():
    """A user who says «ماهی نه» must never get the tuna salad: the ingredient words in a new dish's text are in its keywords."""
    c = catalog()
    problems = []
    for m in c["meals"]:
        if m["id"] not in NEW_MEALS:
            continue
        kw = " ".join(m.get("keywords", [])).replace("‌", " ")
        text = " ".join(c["texts"][m["id"]]["fa"]).replace("‌", " ")
        for word in _INGREDIENTS:
            if word in text and word not in kw:
                problems.append((m["id"], word))
    assert not problems, problems


import pytest


@pytest.mark.parametrize("text", ["tuna", "I am allergic to Tuna fish", "حساسیت به تن ماهی دارم", "تن‌ماهی", "تونا", "سالمون", "تونة", "salmon and sardine"])
def test_a_tuna_or_other_fish_allergy_sets_the_fish_constraint(text):
    """Codex P1 (PR 164): naming the fish (not the word 'fish') must still exclude every fish dish, tuna salad included."""
    assert "fish" in parse_allergens(text)


def test_unrelated_words_do_not_trigger_the_fish_constraint():
    for text in ("بدن درد دارم", "تنفس سخت", "تنها هستم", "no allergies", "ندارم"):
        assert "fish" not in parse_allergens(text)

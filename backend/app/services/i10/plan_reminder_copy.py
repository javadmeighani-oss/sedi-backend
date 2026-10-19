"""Localized reminder copy for catalog-composed plan items (Stage 06 / B2-D4). Kept out of the B13 modules."""
from __future__ import annotations

import json

from backend.app import models
from backend.app.services.i10.coaching_followup_types import CoachingPlanDomain

_PLAN_COPY = {
    "nutrition": {
        "fa": ("وقت {slot}", "{name}{title}{when}. وقتی خوردی بگو «انجام شد» تا ثبت کنم."),
        "en": ("Time for {slot}", "{name}{title}{when}. Tell me \"done\" when you've had it."),
        "ar": ("وقت {slot}", "{name}{title}{when}. قل لي «تم» عندما تنتهي."),
    },
    "exercise": {
        "fa": ("وقت حرکت", "{name}{title}{when}. بعد از انجام بگو «انجام شد» یا اگه نشد بگو چرا."),
        "en": ("Time to move", "{name}{title}{when}. Tell me \"done\" afterwards, or why if you couldn't."),
        "ar": ("وقت الحركة", "{name}{title}{when}. قل لي «تم» بعد الانتهاء أو السبب إن لم تستطع."),
    },
}
_SLOT_WORD = {
    "fa": {"breakfast": "صبحانه", "lunch": "ناهار", "dinner": "شام", "snack": "میان‌وعده"},
    "en": {"breakfast": "breakfast", "lunch": "lunch", "dinner": "dinner", "snack": "a snack"},
    "ar": {"breakfast": "الفطور", "lunch": "الغداء", "dinner": "العشاء", "snack": "وجبة خفيفة"},
}


def composer_copy(db, action, domain, name, summary):
    """Localized, time-aware reminder for a catalog-composed plan item (None for any other action)."""
    import json

    try:
        pres = json.loads(action.presentation_json or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(pres, dict) or pres.get("source") != "sedi_plan_catalog_v1":
        return None
    key = "nutrition" if domain is CoachingPlanDomain.NUTRITION else "exercise" if domain is CoachingPlanDomain.EXERCISE else None
    if key is None:
        return None
    row = db.query(models.User.preferred_language).filter(models.User.id == action.user_id).first()
    lang = (row[0] if row and row[0] else "fa").strip().lower().split("-")[0]
    lang = lang if lang in ("fa", "en", "ar") else "en"
    title_t, body_t = _PLAN_COPY[key][lang]
    slot = _SLOT_WORD[lang].get(str(pres.get("meal_slot") or ""), "")
    when = f" ({pres['local_time']})" if pres.get("local_time") else ""
    prefix = (f"{name}، " if lang != "en" else f"{name}, ") if name else ""
    return (
        title_t.format(slot=slot),
        body_t.format(name=prefix, title=summary, when=when),
        "nutrition_plan_follow_up" if key == "nutrition" else "exercise_plan_follow_up",
    )

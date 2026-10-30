"""Localized reminder copy for catalog-composed plan items (Stage 06 / B2-D4). Kept out of the B13 modules."""
from __future__ import annotations

import json

from backend.app import models
from backend.app.services.i10.coaching_followup_types import CoachingPlanDomain
from backend.app import sedi_copy

_PLAN_COPY = sedi_copy.nested_by_lang("reminder.plan")
_SLOT_WORD = sedi_copy.by_lang("reminder.plan_slot_word")


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
    prefix = sedi_copy.t("address.plain", lang, name=name) if name else ""
    return (
        title_t.format(slot=slot),
        body_t.format(name=prefix, title=summary, when=when),
        "nutrition_plan_follow_up" if key == "nutrition" else "exercise_plan_follow_up",
    )

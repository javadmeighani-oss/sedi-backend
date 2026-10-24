# backend.app.services.profile.overview_summary
"""R-020: the profile «خلاصه کاربر» card is an OVERALL STATUS SUMMARY of the user — one short, human paragraph — not a list
of collected rows. Built deterministically ONLY from clean, consented data (I6 facts, I7 recap/wellbeing, I8 plan status).
Pasted stories/requests that older flows stored as «preferences» are ignored. Returns '' when Sedi does not know enough
yet (the app then shows its friendly empty state). No new storage, no LLM call.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

_MAX_CLEAN_VALUE = 60

_T: dict[str, dict[str, Any]] = {
    "fa": {
        "lead_full": "{name}، تا اینجا این‌طور می‌شناسمت ({sex}، {age} ساله): ",
        "lead": "{name}، تا اینجا این‌طور می‌شناسمت: ",
        "health": "وضعیت سلامتت: {v}",
        "family": "سابقه‌ی خانوادگی‌ای که گفتی: {v}",
        "topic": "این روزها بیشتر درباره‌ی {v} با هم حرف می‌زنیم",
        "events": "اتفاق‌های مهمی که گفتی: {v}",
        "goal": "هدفت: {v}",
        "life": "زندگی روزمره‌ات: {v}",
        "sleep": "حدود {h} ساعت در شب می‌خوابی",
        "mood_low": "در گفتگوهای اخیر کمی خسته یا نگران به نظر می‌رسیدی و مراقبتت برای من مهمه",
        "mood_good": "این اواخر حال و روزت خوب بوده و خوشحالم",
        "plan": "برنامه‌ی روزانه‌ات فعاله و کنارت دنبالش می‌کنم",
        "sex": {"male": "مرد", "female": "زن"},
        "sep": "؛ ",
        "comma": "، ",
        "end": ".",
    },
    "en": {
        "lead_full": "{name}, here is how I know you so far ({sex}, {age}): ",
        "lead": "{name}, here is how I know you so far: ",
        "health": "your health: {v}",
        "family": "family history you told me: {v}",
        "topic": "lately we have mostly talked about {v}",
        "events": "important things you told me about: {v}",
        "goal": "your goal: {v}",
        "life": "your daily life: {v}",
        "sleep": "you sleep about {h} hours a night",
        "mood_low": "in recent chats you seemed a bit tired or worried, and I care about that",
        "mood_good": "lately you have been doing well and I'm glad",
        "plan": "your daily plan is active and I'm following it with you",
        "sex": {"male": "man", "female": "woman"},
        "sep": "; ",
        "comma": ", ",
        "end": ".",
    },
    "ar": {
        "lead_full": "{name}، هكذا أعرفك حتى الآن ({sex}، {age} سنة): ",
        "lead": "{name}، هكذا أعرفك حتى الآن: ",
        "health": "وضعك الصحي: {v}",
        "family": "التاريخ العائلي الذي ذكرته: {v}",
        "topic": "في الأيام الأخيرة تحدثنا أكثر عن {v}",
        "events": "أمور مهمة ذكرتها لي: {v}",
        "goal": "هدفك: {v}",
        "life": "حياتك اليومية: {v}",
        "sleep": "تنام نحو {h} ساعات في الليلة",
        "mood_low": "في محادثاتنا الأخيرة بدوت متعباً أو قلقاً قليلاً وهذا يهمني",
        "mood_good": "في الفترة الأخيرة كان حالك جيداً وأنا سعيدة",
        "plan": "خطتك اليومية فعّالة وأتابعها معك",
        "sex": {"male": "رجل", "female": "امرأة"},
        "sep": "؛ ",
        "comma": "، ",
        "end": ".",
    },
}


def clean_value(text: Any, *, goal: bool = False) -> str:
    """A fact value fit for a summary sentence: short and list-like — never a pasted story or request. A goal is a short
    sentence by nature («میخوام بیشتر به سلامتی برسم»), so it only has to be brief and not a question."""
    from backend.app.services.i6.relationship_discovery import _is_story_or_request

    t = " ".join(str(text or "").split())
    if not t:
        return ""
    if goal:
        return t if len(t) <= 90 and "؟" not in t and "?" not in t else ""
    if len(t) > _MAX_CLEAN_VALUE or _is_story_or_request(t):
        return ""
    return t


def _age_from_birth_year(year: Any) -> Optional[int]:
    try:
        y = int(year)
    except (TypeError, ValueError):
        return None
    if y < 1700:  # Jalali year
        y += 621
    age = datetime.now(timezone.utc).year - y
    return age if 3 <= age <= 110 else None


def build_overview(db: Session, user_id: int, facts: dict[str, str], plan_active: bool = False) -> str:
    """``facts`` = {key: value} from I6 (already consent-gated by the caller). Fail-open: '' on any problem."""
    try:
        from backend.app import models

        user = db.query(models.User).filter(models.User.id == user_id).first()
        lang = (getattr(user, "preferred_language", None) or "fa").split("-")[0].lower()
        t = _T.get(lang, _T["fa"])
        parts: list[str] = []

        for key, tpl in (("health_concerns", "health"), ("family_history", "family")):
            v = clean_value(facts.get(key))
            if v:
                parts.append(t[tpl].format(v=v))
        try:
            from backend.app.services.i7.conversation_recap import recap_topic

            topic = recap_topic(db, user_id, lang if lang in _T else "fa", privacy="in_app")
        except Exception:
            topic = None
        if topic:
            parts.append(t["topic"].format(v=topic))
        try:
            from backend.app.services.i7.life_events import list_life_events

            titles = [e["title"] for e in list_life_events(db, user_id, limit=2) if e.get("title")]
        except Exception:
            titles = []
        if titles:
            parts.append(t["events"].format(v=t["comma"].join(titles)))
        goal = clean_value(facts.get("goal"), goal=True)
        if goal:
            parts.append(t["goal"].format(v=goal))
        life = [v for v in (clean_value(facts.get("occupation")), clean_value(facts.get("household_context"))) if v]
        hours = clean_value(facts.get("sleep_duration_hours"))
        if hours:
            life.append(t["sleep"].format(h=hours))
        if life:
            parts.append(t["life"].format(v=t["comma"].join(life)))
        try:
            from backend.app.services.i7.derived_signals import recent_wellbeing_trend

            trend = (recent_wellbeing_trend(db, user_id) or {}).get("trend")
        except Exception:
            trend = None
        if trend == "low":
            parts.append(t["mood_low"])
        elif trend == "good":
            parts.append(t["mood_good"])
        if plan_active:
            parts.append(t["plan"])
        if not parts:
            return ""

        name, sex, age = (getattr(user, "name", None) or "").strip(), None, None
        try:
            from backend.app.services.user_context import UserContextService

            pack = UserContextService(db).get_user_context(user_id)
            name = (getattr(pack, "preferred_name", None) or name).strip()
            sex = t["sex"].get(str(getattr(pack, "sex", "") or "").strip().lower())
            age = _age_from_birth_year(getattr(pack, "birth_year", None))
        except Exception:
            pass
        if name and sex and age:
            lead = t["lead_full"].format(name=name, sex=sex, age=age)
        elif name:
            lead = t["lead"].format(name=name)
        else:
            lead = ""
        return lead + t["sep"].join(parts) + t["end"]
    except Exception:
        return ""

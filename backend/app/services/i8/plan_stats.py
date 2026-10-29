"""Plan progress and Sedi's motivation (pilot V1 screen 7, R-038): the numbers behind the motivation panel.

Pure read from what the user marked (I8 review state). Nothing is invented: no marks -> zeros and a gentle invitation.
The same deterministic, localized lines are used by the panel and by the motivation notifications, so chat, page and
notifications speak with one voice (R-015).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models

MILESTONE_SESSIONS = (1, 5, 10, 25, 50, 100)
MILESTONE_STREAK_WEEKS = (2, 4, 8, 12)
COMEBACK_AFTER_DAYS = 3


def _lang(language: Optional[str]) -> str:
    lang = (language or "fa").split("-")[0].lower()
    return lang if lang in ("fa", "en", "ar") else "en"


def _pick(options: list[str], seed: str) -> str:
    digest = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)
    return options[digest % len(options)]


def _name(db: Session, user_id: int) -> str:
    row = db.query(models.User.name).filter(models.User.id == int(user_id)).first()
    return " ".join(str(row[0]).split())[:32] if row and row[0] else ""


def _pres(raw: Optional[str]) -> dict:
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


# --------------------------------------------------------------------------------------------------------- copy
def motivation_line(
    lang: str,
    name: str,
    *,
    week_done: int,
    week_total: int,
    comeback: bool = False,
    seed: str = "",
    style: str = "normal",
) -> str:
    """One warm sentence for the panel / the push. ``style``: normal | practical | short (R-023 text adaptation)."""
    lang = _lang(lang)
    who = name.strip()
    left = max(0, week_total - week_done)
    if comeback:
        options = {
            "fa": [
                f"چند روزه ندیدمت{('، ' + who) if who else ''}. هر وقت آماده‌ای با یه تمرین سبک برمی‌گردیم.",
                f"دلم برات تنگ شده بود{('، ' + who) if who else ''}. یه تمرین کوتاه و راحت رو شروع کنیم؟",
            ],
            "en": [
                f"I have missed you{(', ' + who) if who else ''}. Whenever you are ready, we come back with one light session.",
                f"No pressure{(', ' + who) if who else ''}. Shall we start again with a short, easy workout?",
            ],
            "ar": [
                f"اشتقت إليك{('، ' + who) if who else ''}. متى كنت جاهزًا نعود بتمرين خفيف.",
                f"لا ضغط{('، ' + who) if who else ''}. هل نبدأ من جديد بتمرين قصير وسهل؟",
            ],
        }[lang]
    elif week_total <= 0:
        options = {
            "fa": ["برنامه‌ی این هفته‌ات آماده‌ست. با هم شروع کنیم؟"],
            "en": ["Your plan for this week is ready. Shall we start together?"],
            "ar": ["خطتك لهذا الأسبوع جاهزة. نبدأ معًا؟"],
        }[lang]
    elif week_done == 0:
        options = {
            "fa": [
                f"هفته‌ی ورزشت آماده‌ست{('، ' + who) if who else ''}. اولین جلسه رو شروع کنیم؟",
                f"من کنارتم{('، ' + who) if who else ''}. اولین قدم همیشه سخت‌ترینه؛ امروز برداریمش.",
            ],
            "en": [
                f"Your week is ready{(', ' + who) if who else ''}. Shall we start the first session?",
                f"I am with you{(', ' + who) if who else ''}. The first step is the hardest; let's take it today.",
            ],
            "ar": [
                f"أسبوعك جاهز{('، ' + who) if who else ''}. هل نبدأ الجلسة الأولى؟",
                f"أنا معك{('، ' + who) if who else ''}. الخطوة الأولى هي الأصعب؛ لنخطها اليوم.",
            ],
        }[lang]
    elif left == 0:
        options = {
            "fa": [f"همه‌ی جلسه‌های این هفته رو انجام دادی{('، ' + who) if who else ''}. به خودت افتخار کن!"],
            "en": [f"You finished every session this week{(', ' + who) if who else ''}. Be proud of yourself!"],
            "ar": [f"أنجزت كل جلسات هذا الأسبوع{('، ' + who) if who else ''}. افخر بنفسك!"],
        }[lang]
    else:
        options = {
            "fa": [
                f"{_n(week_done, lang)} جلسه رو تموم کردی{('، ' + who) if who else ''}. {_n(left, lang)} جلسه‌ی دیگه و هفته‌ات عالیه!",
                f"داری خوب پیش می‌ری{('، ' + who) if who else ''}؛ {_n(left, lang)} جلسه تا آخر هفته مونده.",
            ],
            "en": [
                f"You have done {week_done} session(s){(', ' + who) if who else ''}. {left} more and your week is great!",
                f"You are doing well{(', ' + who) if who else ''}; {left} session(s) left this week.",
            ],
            "ar": [
                f"أنجزت {_n(week_done, lang)} جلسة{('، ' + who) if who else ''}. {_n(left, lang)} أخرى ويصبح أسبوعك رائعًا!",
                f"تتقدم جيدًا{('، ' + who) if who else ''}؛ بقيت {_n(left, lang)} جلسة هذا الأسبوع.",
            ],
        }[lang]
    text = _pick(options, seed or "x")
    if style == "short":
        return text.split(".")[0].split("؛")[0].strip() + ("." if lang == "en" else "")
    return text


def _n(value: int, lang: str) -> str:
    if lang in ("fa", "ar"):
        table = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹" if lang == "fa" else "٠١٢٣٤٥٦٧٨٩")
        return str(value).translate(table)
    return str(value)


def practical_line(lang: str, title: str, local_time: str, minutes: Optional[int]) -> str:
    """Text type for users who disliked the generic cheer: what, when, how long (R-023)."""
    lang = _lang(lang)
    mins = f" · {_n(minutes, lang)} {'دقیقه' if lang == 'fa' else 'دقيقة' if lang == 'ar' else 'min'}" if minutes else ""
    at = _n_time(local_time, lang)
    return {
        "fa": f"امروز ساعت {at}: {title}{mins}.",
        "en": f"Today at {at}: {title}{mins}.",
        "ar": f"اليوم الساعة {at}: {title}{mins}.",
    }[lang]


def _n_time(value: str, lang: str) -> str:
    if lang in ("fa", "ar"):
        table = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹" if lang == "fa" else "٠١٢٣٤٥٦٧٨٩")
        return value.translate(table)
    return value


def milestone_line(lang: str, name: str, *, sessions: Optional[int] = None, streak_weeks: Optional[int] = None) -> str:
    lang = _lang(lang)
    who = name.strip()
    tail_fa = f"، {who}" if who else ""
    tail_en = f", {who}" if who else ""
    if streak_weeks:
        return {
            "fa": f"{_n(streak_weeks, 'fa')} هفته‌ی پشت‌سرهم حرکت کردی{tail_fa}! این یعنی عادت داره می‌شه.",
            "en": f"{streak_weeks} weeks in a row{tail_en}! This is becoming a habit.",
            "ar": f"{_n(streak_weeks, 'ar')} أسابيع متتالية{tail_fa}! هذا يصبح عادة.",
        }[lang]
    n = int(sessions or 0)
    if n <= 1:
        return {
            "fa": f"اولین جلسه‌ات انجام شد{tail_fa}! شروع قشنگی بود.",
            "en": f"Your first session is done{tail_en}! A lovely start.",
            "ar": f"تمت جلستك الأولى{tail_fa}! بداية جميلة.",
        }[lang]
    return {
        "fa": f"{_n(n, 'fa')} جلسه تمرین رو تموم کردی{tail_fa}! آفرین.",
        "en": f"{n} sessions done{tail_en}! Well done.",
        "ar": f"أنجزت {_n(n, 'ar')} جلسة{tail_fa}! أحسنت.",
    }[lang]


# --------------------------------------------------------------------------------------------------------- numbers
def _done_rows(db: Session, user_id: int, domain: str) -> list[tuple[models.I8OperationalPlanAction, dict]]:
    from backend.app.services.i8.action_review import review_of
    from backend.app.services.i8.plan_composer import SOURCE_TAG

    rows = (
        db.query(models.I8OperationalPlanAction)
        .filter(
            models.I8OperationalPlanAction.user_id == int(user_id),
            models.I8OperationalPlanAction.action_domain == domain,
        )
        .order_by(models.I8OperationalPlanAction.id.desc())
        .limit(3000)
        .all()
    )
    out = []
    for a in rows:
        pres = _pres(a.presentation_json)
        if pres.get("source") != SOURCE_TAG or pres.get("activity_type") == "rest":
            continue
        rev = review_of(a)
        if rev and rev.get("outcome") == "done":
            out.append((a, pres))
    return out


def totals(db: Session, user_id: int, domain: str, *, current_cycle_start: Optional[str]) -> dict:
    """total_done, streak_weeks (consecutive 7-day cycles with at least one done session), best_minutes, last_done_date."""
    from backend.app.services.i8.local_day import CYCLE_START_META_KEY

    done = _done_rows(db, user_id, domain)
    cycles: set[str] = set()
    best = 0
    last: Optional[str] = None
    for _a, pres in done:
        stamp = pres.get(CYCLE_START_META_KEY)
        if stamp:
            cycles.add(str(stamp))
        try:
            best = max(best, int(pres.get("duration_minutes") or 0))
        except (TypeError, ValueError):
            pass
        d = str(pres.get("local_date") or "")
        if d and (last is None or d > last):
            last = d
    streak = 0
    if cycles:
        cursor: Optional[date] = None
        if current_cycle_start and current_cycle_start in cycles:
            cursor = date.fromisoformat(current_cycle_start)
        elif current_cycle_start:
            cursor = date.fromisoformat(current_cycle_start) - timedelta(days=7)  # this week is not done yet
        else:
            cursor = date.fromisoformat(max(cycles))
        while cursor is not None and cursor.isoformat() in cycles:
            streak += 1
            cursor -= timedelta(days=7)
    return {"total_done": len(done), "streak_weeks": streak, "best_minutes": best, "last_done_date": last}


def build_progress(
    db: Session,
    user_id: int,
    domain: str,
    *,
    language: Optional[str] = None,
    now_utc: Optional[datetime] = None,
) -> dict[str, Any]:
    from backend.app.services.lifestyle.a3_weekly_plan_projection import build_lifestyle_weekly_plan_projection

    lang = _lang(language)
    proj = build_lifestyle_weekly_plan_projection(db, int(user_id), now_utc=now_utc)
    base: dict[str, Any] = {"domain": domain, "state": proj.get("state")}
    if proj.get("state") in ("empty", "unavailable") or not proj.get("cycle_start"):
        return base
    days = []
    week_total = week_done = 0
    today_iso = str(proj.get("today_local") or "")
    comeback_gap: Optional[int] = None
    for day in proj.get("days") or []:
        items = [i for i in (day.get(domain) or []) if i.get("local_time")]  # rest days carry no time
        done_n = sum(1 for i in items if (i.get("status") or "").upper() == "COMPLETED" or (i.get("review") or {}).get("outcome") == "done")
        if items:
            week_total += len(items)
            week_done += done_n
        local = str(day.get("local_date") or "")
        state = "none" if not items else ("done" if done_n == len(items) else "planned")
        if local == today_iso:
            state = "today" if state != "done" else "today_done"
        days.append({"local_date": local, "state": state, "items": len(items), "done": done_n})
    t = totals(db, user_id, domain, current_cycle_start=str(proj["cycle_start"]))
    if t["last_done_date"] and today_iso:
        try:
            comeback_gap = (date.fromisoformat(today_iso) - date.fromisoformat(t["last_done_date"])).days
        except ValueError:
            comeback_gap = None
    comeback = bool(t["total_done"] and comeback_gap is not None and comeback_gap >= COMEBACK_AFTER_DAYS and week_total > week_done)
    seed = f"{user_id}:{domain}:{today_iso}"
    return {
        **base,
        "cycle_start": proj.get("cycle_start"),
        "cycle_end": proj.get("cycle_end"),
        "today_local": today_iso,
        "week_done": week_done,
        "week_total": week_total,
        "percent": round(100 * week_done / week_total) if week_total else 0,
        "days": days,
        "streak_weeks": t["streak_weeks"],
        "total_done": t["total_done"],
        "best_minutes": t["best_minutes"],
        "days_since_done": comeback_gap,
        "comeback": comeback,
        "message": motivation_line(
            lang, _name(db, user_id), week_done=week_done, week_total=week_total, comeback=comeback, seed=seed
        ),
    }

"""Weekly review of a plan (pilot V1 screen 6): how the week went, from what the user actually did.

Pure read: it builds on the weekly plan projection (the 7 local days of the current stamped cycle) and the existing
review marks (done / skipped + the user's own reason). Nothing is invented: no cycle -> ``state`` says so; no marked
items -> no percent story. The sentence is deterministic, warm and localized; the next week is composed from this
(low adherence -> lighter plan) by the existing composer.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i8.action_review import SKIP_REASONS

_REASON_TEXT = {
    "fa": {
        "no_time": "وقت نداشتی",
        "too_hard": "سخت بود",
        "not_feeling_well": "حالت خوب نبود",
        "dont_like": "دوست نداشتی",
        "forgot": "یادت رفت",
        "other": "دلایل دیگه",
    },
    "en": {
        "no_time": "no time",
        "too_hard": "too hard",
        "not_feeling_well": "not feeling well",
        "dont_like": "not to your taste",
        "forgot": "forgot",
        "other": "other reasons",
    },
    "ar": {
        "no_time": "لا وقت",
        "too_hard": "صعب",
        "not_feeling_well": "لم تكن بخير",
        "dont_like": "لم يعجبك",
        "forgot": "نسيت",
        "other": "أسباب أخرى",
    },
}


def _lang(language: Optional[str]) -> str:
    lang = (language or "fa").split("-")[0].lower()
    return lang if lang in ("fa", "en", "ar") else "en"


def _counts(items: list[dict], *, up_to: Optional[date]) -> dict:
    done = skipped = pending = 0
    reasons: dict[str, int] = {}
    per_weekday: dict[int, int] = {}
    for it in items:
        if not it.get("local_time"):
            continue  # rest-day placeholders carry no time and are not sessions
        local = str(it.get("local_date") or "")
        if up_to is not None and local and local > up_to.isoformat():
            continue
        review = it.get("review") or {}
        outcome = review.get("outcome")
        if (it.get("status") or "").upper() == "COMPLETED" or outcome == "done":
            done += 1
            try:
                wd = date.fromisoformat(local).isoweekday()
                per_weekday[wd] = per_weekday.get(wd, 0) + 1
            except ValueError:
                pass
        elif outcome == "skipped":
            skipped += 1
            reason = review.get("reason") if review.get("reason") in SKIP_REASONS else "other"
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            pending += 1
    total = done + skipped + pending
    return {
        "done": done,
        "skipped": skipped,
        "pending": pending,
        "total": total,
        "percent": round(100 * done / total) if total else 0,
        "reasons": reasons,
        "per_weekday": per_weekday,
    }


def _previous_percent(db: Session, user_id: int, domain: str, cycle_start: str) -> Optional[int]:
    """Adherence % of the stamped cycle just BEFORE ``cycle_start`` (None when there is none or too little data)."""
    import json

    from backend.app.services.i8.local_day import CYCLE_START_META_KEY

    rows = (
        db.query(models.I8OperationalPlanAction)
        .filter(
            models.I8OperationalPlanAction.user_id == int(user_id),
            models.I8OperationalPlanAction.action_domain == domain,
        )
        .order_by(models.I8OperationalPlanAction.id.desc())
        .limit(200)
        .all()
    )
    by_cycle: dict[str, list] = {}
    for a in rows:
        try:
            pres = json.loads(a.presentation_json or "{}")
        except (TypeError, ValueError):
            continue
        if isinstance(pres, dict) and pres.get(CYCLE_START_META_KEY):
            by_cycle.setdefault(str(pres[CYCLE_START_META_KEY]), []).append(a)
    earlier = sorted(c for c in by_cycle if c < cycle_start)
    if not earlier:
        return None
    from backend.app.services.i8.action_review import adherence

    summary = adherence(by_cycle[earlier[-1]])
    return summary["percent"] if summary["done"] + summary["skipped"] >= 3 else None


def _message(lang: str, percent: int, reviewed: int, best_weekday: Optional[int], top_reason: Optional[str]) -> str:
    reason = _REASON_TEXT[lang].get(top_reason or "", "")
    if reviewed < 3:
        return {
            "fa": "هنوز چیز زیادی ثبت نشده؛ هر وعده‌ای که خوردی یا نشد، بهم بگو تا هفته‌ی بعد دقیق‌تر بچینم.",
            "en": "Not much is marked yet; tell me what you did or could not do and I will fit next week better.",
            "ar": "لم يُسجَّل الكثير بعد؛ أخبرني بما فعلته أو لم تستطع لأضبط الأسبوع القادم أفضل.",
        }[lang]
    if percent >= 80:
        return {
            "fa": "هفته‌ی عالی‌ای بود! همین ریتم رو نگه داریم.",
            "en": "A great week! Let's keep this rhythm.",
            "ar": "أسبوع رائع! لنحافظ على هذا الإيقاع.",
        }[lang]
    if percent >= 50:
        base = {
            "fa": "هفته‌ی خوبی بود.",
            "en": "A good week.",
            "ar": "أسبوع جيد.",
        }[lang]
        tail = {
            "fa": f" بیشتر چیزی که سخت بود: {reason}." if reason else "",
            "en": f" The hardest part: {reason}." if reason else "",
            "ar": f" الأصعب: {reason}." if reason else "",
        }[lang]
        return base + tail
    return {
        "fa": "این هفته سخت‌تر بود و اشکالی نداره. هفته‌ی بعد رو سبک‌تر می‌چینم تا راحت‌تر بشه."
        + (f" بیشتر چیزی که سخت بود: {reason}." if reason else ""),
        "en": "This week was harder, and that is fine. I will make next week lighter so it is easier."
        + (f" The hardest part: {reason}." if reason else ""),
        "ar": "كان هذا الأسبوع أصعب، ولا بأس. سأجعل الأسبوع القادم أخف ليكون أسهل."
        + (f" الأصعب: {reason}." if reason else ""),
    }[lang]


def build_weekly_review(
    db: Session,
    user_id: int,
    domain: str,
    *,
    language: Optional[str] = None,
    now_utc=None,
) -> dict[str, Any]:
    """The review of the current stamped cycle of ``domain``. ``state`` is 'ready' only when there is something to say."""
    from backend.app.services.lifestyle.a3_weekly_plan_projection import build_lifestyle_weekly_plan_projection

    lang = _lang(language)
    proj = build_lifestyle_weekly_plan_projection(db, int(user_id), now_utc=now_utc)
    state = proj.get("state")
    base = {"domain": domain, "state": state, "review_due": bool(proj.get("review_due"))}
    if state in ("empty", "unavailable") or not proj.get("cycle_start"):
        return base
    items: list[dict] = []
    for day in proj.get("days") or []:
        items.extend(day.get(domain) or [])
    try:
        up_to = date.fromisoformat(str(proj.get("today_local") or ""))
    except ValueError:
        up_to = None
    c = _counts(items, up_to=up_to)
    reviewed = c["done"] + c["skipped"]
    best = None
    if c["per_weekday"]:
        top = max(c["per_weekday"].values())
        best = min(wd for wd, n in c["per_weekday"].items() if n == top)
    top_reason = max(c["reasons"], key=lambda k: c["reasons"][k]) if c["reasons"] else None
    prev = _previous_percent(db, user_id, domain, str(proj["cycle_start"]))
    delta = (c["percent"] - prev) if (prev is not None and reviewed >= 3) else None
    return {
        **base,
        "state": "ready" if c["total"] else state,
        "cycle_start": proj.get("cycle_start"),
        "cycle_end": proj.get("cycle_end"),
        "done": c["done"],
        "skipped": c["skipped"],
        "pending": c["pending"],
        "total": c["total"],
        "percent": c["percent"],
        "reasons": c["reasons"],
        "best_weekday": best,
        "previous_percent": prev,
        "delta": delta,
        "message": _message(lang, c["percent"], reviewed, best, top_reason),
    }

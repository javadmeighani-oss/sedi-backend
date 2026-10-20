"""I7 derived signals for the short / medium / long-term memory layers (Stage 06 / B2-C1).

DAILY summaries (short term) now carry small, numeric/keyed `signals` — plan adherence, notification feedback
and health topics (verified I5 concept keys) — instead of only turn counts. WEEKLY / MONTHLY / YEARLY summaries
(medium / long term) are merged from their finalized parents, so trends survive after raw turns expire.
Not a transcript: no message text, only counts, bounded reasons and concept keys. A summary without any signal
keeps its previous payload byte-for-byte (existing integrity digests are unaffected).

Consumers: I1 topic carry-over (`recent_topic_concept_keys`), I8 composer (adherence), I10 digest/reminders.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from backend.app import models

MAX_TOPICS = 5
MAX_TURNS_SCANNED = 20

# R-011: coarse, surface-level wellbeing categories the user themself voiced in chat (fa/en/ar). A turn counts
# once per category. These are derived, unconfirmed signals — never diagnoses, never stored as facts.
WELLBEING_CATEGORIES = ("low_mood", "stress", "fatigue", "sleep_issue", "pain", "positive")
_WELLBEING_CUES: dict = {
    "low_mood": (
        "ناراحت", "غمگین", "دلگیر", "دلم گرفته", "غصه", "افسرده", "تنهام", "گریه", "ناامید", "دلتنگ", "حالم بد", "حالم خوب نیست",
        "sad", "depress", "lonely", "hopeless", "crying", "down today", "feel low",
        "حزين", "حزينة", "مكتئب", "وحيد", "يائس", "أبكي",
    ),
    "stress": (
        "استرس", "نگران", "اضطراب", "کلافه", "عصبی", "فشار روانی", "می‌ترسم", "میترسم",
        "stress", "anxious", "anxiety", "worried", "overwhelmed", "panic",
        "قلق", "متوتر", "خائف", "ضغط نفسي",
    ),
    "fatigue": (
        "خسته", "بی‌حال", "بی حال", "بی‌انرژی", "بی انرژی", "کم‌انرژی", "حوصله ندارم",
        "tired", "exhausted", "no energy", "fatigue", "burned out", "burnt out",
        "تعبان", "تعبت", "مرهق", "لا طاقة",
    ),
    "sleep_issue": (
        "خوابم نمیاد", "خوابم نمی‌آد", "خوابم نمیبره", "خوابم نمی‌بره", "بی‌خوابی", "بیخوابی", "کم خوابیدم", "خواب ندارم",
        "can't sleep", "cannot sleep", "insomnia", "didn't sleep", "barely slept", "trouble sleeping",
        "لا أنام", "أرق", "لم أنم",
    ),
    "pain": (
        "درد دارم", "دردم", "دردش", "درد می‌کنه", "درد میکنه", "درد می‌کند", "درد میکند",
        "pain", "hurts", "aching", "sore ",
        "ألم", "يؤلمني", "وجع",
    ),
    "positive": (
        "خوشحالم", "خوبم", "عالیم", "حالم خوبه", "خیلی خوب بود", "خوش گذشت", "انرژی دارم", "سر حالم", "امیدوارم",
        "i'm happy", "im happy", "feeling good", "feel great", "feeling great", "good day", "great day", "i feel better",
        "سعيد", "بخير", "سعيدة", "مرتاح",
    ),
}


def _wellbeing_signal(turns: Iterable[Any]) -> dict:
    """Per-category count of the day's user turns that voiced it (counts only; {} when nothing was voiced)."""
    counts: Counter = Counter()
    for t in list(turns)[:MAX_TURNS_SCANNED]:
        text = " ".join(str(getattr(t, "user_message", "") or "").lower().split())
        if not text:
            continue
        for cat, cues in _WELLBEING_CUES.items():
            if any(c in text for c in cues):
                counts[cat] += 1
    return {k: int(v) for k, v in counts.items() if v}


def decide_wellbeing_trend(summed: dict) -> dict:
    """Pure decision over summed category counts of the recent window.

    trend = "low" when strain (low mood + stress + fatigue) clearly outweighs positive voices;
            "good" when positive clearly outweighs strain; else None. `concerns` lists recurring physical/sleep topics.
    """
    strain = int(summed.get("low_mood", 0)) + int(summed.get("stress", 0)) + int(summed.get("fatigue", 0))
    positive = int(summed.get("positive", 0))
    trend = None
    if strain >= 3 and strain > positive:
        trend = "low"
    elif positive >= 2 and positive > strain:
        trend = "good"
    concerns = [c for c in ("sleep_issue", "pain") if int(summed.get(c, 0)) >= 2]
    return {"trend": trend, "concerns": concerns}


def _loads(raw: Optional[str]) -> dict:
    try:
        v = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def _plan_signal(db: Session, user_id: int, local_day: date) -> dict:
    from backend.app.services.i10.plan_progress import day_progress

    p = day_progress(db, user_id, local_day)
    if not p:
        return {}
    return {"done": p["done"], "skipped": p["skipped"], "pending": p["pending"], "total": p["total"]}


def _feedback_signal(db: Session, user_id: int, local_day: date) -> dict:
    start = datetime(local_day.year, local_day.month, local_day.day)
    rows = (
        db.query(models.NotificationFeedback)
        .filter(
            models.NotificationFeedback.user_id == user_id,
            models.NotificationFeedback.created_at >= start,
            models.NotificationFeedback.created_at < start + timedelta(days=1),
        )
        .all()
    )
    if not rows:
        return {}
    likes = sum(1 for r in rows if r.action == "like")
    dislikes = [r for r in rows if r.action == "dislike"]
    reasons = Counter(str(_loads(r.meta_json).get("reason") or "") for r in dislikes)
    reasons.pop("", None)
    out = {"likes": likes, "dislikes": len(dislikes)}
    if reasons:
        out["dislike_reasons"] = dict(reasons)
    return out


def _topic_signal(db: Session, user_id: int, turns: Iterable[Any]) -> list:
    """Verified I5 concept keys named in the day's eligible user turns (keys only, never text)."""
    try:
        from backend.app.services.i5.know02.taxonomy import resolve_verified_concept_authority

        user = db.query(models.User).filter(models.User.id == user_id).first()
        lang = (getattr(user, "preferred_language", None) or "fa").split("-")[0]
        keys: list = []
        for t in list(turns)[:MAX_TURNS_SCANNED]:
            auth = resolve_verified_concept_authority(db, str(getattr(t, "user_message", "") or ""), lang)
            if auth is not None and auth.concept_key not in keys:
                keys.append(auth.concept_key)
            if len(keys) >= MAX_TOPICS:
                break
        return keys
    except Exception:
        return []


def collect_daily_signals(db: Session, user_id: int, local_day: date, turns: Iterable[Any]) -> dict:
    """Non-empty signals of one local day, or {} (then the DAILY payload is unchanged)."""
    out: dict = {}
    for name, fn in (
        ("plan", lambda: _plan_signal(db, user_id, local_day)),
        ("feedback", lambda: _feedback_signal(db, user_id, local_day)),
    ):
        try:
            val = fn()
        except Exception:
            val = {}
        if val:
            out[name] = val
    topics = _topic_signal(db, user_id, turns)
    if topics:
        out["topics"] = topics
    try:
        wellbeing = _wellbeing_signal(turns)
    except Exception:
        wellbeing = {}
    if wellbeing:
        out["wellbeing"] = wellbeing
    return out


def merge_signals(parts: Iterable[dict]) -> dict:
    """Pure merge of child signals into a parent period (sums, reason counts, topic frequency)."""
    plan = Counter()
    fb = Counter()
    reasons: Counter = Counter()
    topics: Counter = Counter()
    days_with_plan = 0
    wellbeing: Counter = Counter()
    days_with_wellbeing = 0
    for s in parts:
        if not s:
            continue
        w = s.get("wellbeing") or {}
        if w:
            days_with_wellbeing += 1
            for k in WELLBEING_CATEGORIES:
                wellbeing[k] += int(w.get(k, 0) or 0)
        p = s.get("plan") or {}
        if p:
            days_with_plan += 1
            for k in ("done", "skipped", "pending", "total"):
                plan[k] += int(p.get(k, 0) or 0)
        f = s.get("feedback") or {}
        for k in ("likes", "dislikes"):
            fb[k] += int(f.get(k, 0) or 0)
        reasons.update({k: int(v) for k, v in (f.get("dislike_reasons") or {}).items()})
        topics.update(s.get("topics") or [])
    out: dict = {}
    if plan:
        reviewed = plan["done"] + plan["skipped"] + plan["pending"]
        out["plan"] = {**dict(plan), "days": days_with_plan, "percent": round(100 * plan["done"] / reviewed) if reviewed else 0}
    if fb or reasons:
        out["feedback"] = {**dict(fb), **({"dislike_reasons": dict(reasons)} if reasons else {})}
    if topics:
        out["topics"] = [k for k, _ in topics.most_common(MAX_TOPICS)]
    if sum(wellbeing.values()):
        out["wellbeing"] = {**{k: v for k, v in wellbeing.items() if v}, "days": days_with_wellbeing}
    return out


def signals_of(summary: Any) -> dict:
    return _loads(getattr(summary, "structured_summary_json", None)).get("signals") or {}


def recent_wellbeing_trend(db: Session, user_id: int, *, days: int = 7) -> dict:
    """Short-term wellbeing read from the newest active DAILY summaries ({} when none / nothing voiced)."""
    rows = (
        db.query(models.UserPeriodSummary)
        .filter(
            models.UserPeriodSummary.user_id == user_id,
            models.UserPeriodSummary.summary_type == "DAILY",
            models.UserPeriodSummary.status == "active",
        )
        .order_by(models.UserPeriodSummary.period_start.desc())
        .limit(days)
        .all()
    )
    summed: Counter = Counter()
    for r in rows:
        for k, v in (signals_of(r).get("wellbeing") or {}).items():
            if k in WELLBEING_CATEGORIES:
                summed[k] += int(v or 0)
    if not sum(summed.values()):
        return {}
    return decide_wellbeing_trend(dict(summed))


def recent_topic_concept_keys(db: Session, user_id: int, *, limit: int = 3) -> list:
    """Most recent concept keys from the user's active DAILY, then WEEKLY, summaries (newest first)."""
    for stype in ("DAILY", "WEEKLY"):
        rows = (
            db.query(models.UserPeriodSummary)
            .filter(
                models.UserPeriodSummary.user_id == user_id,
                models.UserPeriodSummary.summary_type == stype,
                models.UserPeriodSummary.status == "active",
            )
            .order_by(models.UserPeriodSummary.period_start.desc())
            .limit(14)
            .all()
        )
        keys: list = []
        for r in rows:
            for k in signals_of(r).get("topics", []):
                if k not in keys:
                    keys.append(k)
        if keys:
            return keys[:limit]
    return []

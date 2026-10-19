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
    return out


def merge_signals(parts: Iterable[dict]) -> dict:
    """Pure merge of child signals into a parent period (sums, reason counts, topic frequency)."""
    plan = Counter()
    fb = Counter()
    reasons: Counter = Counter()
    topics: Counter = Counter()
    days_with_plan = 0
    for s in parts:
        if not s:
            continue
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
    return out


def signals_of(summary: Any) -> dict:
    return _loads(getattr(summary, "structured_summary_json", None)).get("signals") or {}


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

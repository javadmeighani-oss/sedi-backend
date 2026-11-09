"""R-074 step 5b (A): ONE weekly progress report per user, from what the user actually marked (R-038, R-031).

Nothing new is recorded here (R-005): the numbers come from the owners that already exist -
I7 ``user_done`` (done / not-done ledger of every kind: medication, events, plan items) for the last 7 local days and
the I8 weekly plan review (nutrition / exercise percent and change against the previous week). Read-only, consent
already applied where the ledger is written, fail-open per part, deterministic text from the copy catalog (R-043).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import sedi_copy

WEEK_DAYS = 7
PLAN_DOMAINS = ("nutrition", "exercise")


def _percent(done: int, not_done: int) -> Optional[int]:
    total = done + not_done
    return round(100 * done / total) if total else None


def _split_not_done(counts: dict[str, int]) -> tuple[dict[str, int], dict[str, int]]:
    by_domain: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for key, n in counts.items():
        if key.startswith("reason."):
            reasons[key.split(".", 1)[1]] = reasons.get(key.split(".", 1)[1], 0) + int(n)
        else:
            by_domain[key] = by_domain.get(key, 0) + int(n)
    return by_domain, reasons


def _plan_part(db: Session, user_id: int, domain: str, language: Optional[str], now_utc: Optional[datetime]) -> dict[str, Any]:
    try:
        from backend.app.services.i8.weekly_review import build_weekly_review

        r = build_weekly_review(db, user_id, domain, language=language, now_utc=now_utc)
        return {k: r.get(k) for k in ("state", "percent", "previous_percent", "delta", "done", "skipped", "total")}
    except Exception:  # noqa: BLE001 - one broken part must not hide the rest of the week
        return {"state": "unavailable"}


def build_weekly_user_report(
    db: Session,
    user_id: int,
    *,
    language: Optional[str] = None,
    now_utc: Optional[datetime] = None,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """The last 7 local days (today included). ``state`` is 'ready' only when the user marked something."""
    from backend.app.services.i7 import user_done

    if today is None:
        try:
            from backend.app.services.i8.local_day import local_today_for_user

            today = local_today_for_user(db, user_id, now_utc=now_utc)[1]
        except Exception:  # noqa: BLE001
            today = (now_utc or datetime.utcnow()).date()
    days = [today - timedelta(days=i) for i in range(WEEK_DAYS - 1, -1, -1)]

    done_parts: list[dict[str, int]] = []
    notdone_parts: list[dict[str, int]] = []
    for day in days:
        try:
            done_parts.append(user_done.done_counts_for_day(db, user_id, day))
            notdone_parts.append(user_done.not_done_counts_for_day(db, user_id, day))
        except Exception:  # noqa: BLE001
            continue
    done_by_domain = user_done.merge_done_counts(done_parts)
    not_done_raw = user_done.merge_done_counts(notdone_parts)
    not_done_by_domain, reasons = _split_not_done(not_done_raw)

    domains = sorted(set(done_by_domain) | set(not_done_by_domain))
    by_domain = {
        d: {
            "done": done_by_domain.get(d, 0),
            "not_done": not_done_by_domain.get(d, 0),
            "percent": _percent(done_by_domain.get(d, 0), not_done_by_domain.get(d, 0)),
        }
        for d in domains
    }
    done = sum(done_by_domain.values())
    not_done = sum(not_done_by_domain.values())
    ready = (done + not_done) > 0
    lang = language or "fa"
    message = (
        sedi_copy.t("weekly_report.summary.active", lang, done=done, not_done=not_done)
        if ready
        else sedi_copy.t("weekly_report.summary.quiet", lang)
    )
    return {
        "state": "ready" if ready else "empty",
        "week_start": days[0].isoformat(),
        "week_end": days[-1].isoformat(),
        "totals": {"done": done, "not_done": not_done, "percent": _percent(done, not_done)},
        "by_domain": by_domain,
        "reasons": dict(sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))),
        "plans": {d: _plan_part(db, user_id, d, language, now_utc) for d in PLAN_DOMAINS},
        "message": message,
    }

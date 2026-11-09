"""R-074 step 5b (B): weekly LAYER report for Javad (governed self-training loop R-060: collect outcomes -> evaluate -> propose).

Aggregate counts only (no statement text, no user ids, no health data), read-only, fail-open per layer. It complements -
and does not duplicate - ``weekly_growth_report`` (library growth per domain x language, R-044):

- L3 RAG books: ELIGIBLE knowledge units per language (the library the answers stand on);
- L4 agent hands: notifications created/sent/opened in the last 7 days, what users marked done / not done
  (I7 ledger), follow-up commitments opened (I10 care follow-up tasks) and how many are still open;
- L1/L2 (answer depth in fa/en): measured by the read-only production battery (workflow ``i5-depth-audit-readonly``), not in-app -
  the report says so instead of inventing a number;
- L5 state contract: the guarded list of modules that may read the user's context pack (step 5a).

The weekly hook logs one ``i5_weekly_layers_report`` line; the CLI prints one ``PROBE|layers_report|...`` line.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

PACKAGE_ID = "I5-R074-WEEKLY-LAYERS-REPORT-V1"
WINDOW_DAYS = 7
MAX_LEDGER_USERS = 5000  # bound of the weekly aggregation
DEPTH_AUDIT_NOTE = "measured by workflow i5-depth-audit-readonly (CI, read-only battery); not computable in-app"


def _safe(fn) -> dict[str, Any]:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - one broken layer must not hide the rest
        return {"state": "unavailable", "error": type(exc).__name__}


def _rate(part: int, whole: int) -> Optional[float]:
    return round(part / whole, 3) if whole else None


def _l3_knowledge(db: Any, m: Any) -> dict[str, Any]:
    rows = (
        db.query(m.KnowledgeUnit.language)
        .filter(m.KnowledgeUnit.runtime_eligibility == "ELIGIBLE")
        .all()
    )
    by_lang = Counter(str(r[0] or "unknown") for r in rows)
    return {"state": "ok", "eligible_total": sum(by_lang.values()), "eligible_by_language": dict(sorted(by_lang.items()))}


def _l4_notifications(db: Any, m: Any, since: datetime) -> dict[str, Any]:
    # Each count uses its own event time (Codex P2): created by created_at, delivered by sent_at, opened by opened_at.
    created = db.query(m.Notification).filter(m.Notification.created_at >= since).count()
    sent = db.query(m.Notification).filter(m.Notification.is_sent.is_(True), m.Notification.sent_at >= since).count()
    opened = db.query(m.Notification).filter(m.Notification.opened_at >= since.replace(tzinfo=timezone.utc)).count()
    by_category = Counter(str(r[0] or "none") for r in db.query(m.Notification.category).filter(m.Notification.created_at >= since).all())
    return {
        "state": "ok",
        "created": created,
        "sent": sent,
        "opened": opened,
        "open_rate_of_sent": _rate(opened, sent),
        "by_category": dict(sorted(by_category.items())),
    }


def _l4_ledger(db: Any, m: Any, since: datetime) -> dict[str, Any]:
    from backend.app.services.i7 import user_done

    # Resolved outcomes (Codex P2): a done-then-undone occurrence must not count twice, so every user's days go through the
    # I7 helpers that resolve the CURRENT state of each occurrence.
    user_ids = [
        int(r[0])
        for r in db.query(m.InteractionEvent.user_id)
        .filter(m.InteractionEvent.source == user_done.LEDGER_SOURCE, m.InteractionEvent.created_at >= since)
        .distinct()
        .limit(MAX_LEDGER_USERS)
        .all()
    ]
    days = [(since + timedelta(days=i)).date() for i in range(WINDOW_DAYS + 1)]
    done = not_done = 0
    for uid in user_ids:
        for day in days:
            done += sum(user_done.done_counts_for_day(db, uid, day).values())
            nd = user_done.not_done_counts_for_day(db, uid, day)
            not_done += sum(v for k, v in nd.items() if not k.startswith("reason."))
    return {"state": "ok", "users": len(user_ids), "done": done, "not_done": not_done, "done_rate": _rate(done, done + not_done)}


def _l4_commitments(db: Any, m: Any, since: datetime) -> dict[str, Any]:
    from backend.app.services.i10.commitment_followup import _OPEN_STATUSES, COMMITMENT_KIND

    # Commitments only (Codex P2): assurance / post-event tasks share the table, so filter by the follow-up kind marker.
    rows = (
        db.query(m.CareFollowUpTask.status, m.CareFollowUpTask.source)
        .filter(
            m.CareFollowUpTask.created_at >= since,
            m.CareFollowUpTask.description.contains(f'"follow_up_kind":"{COMMITMENT_KIND}"'),
        )
        .all()
    )
    by_status = Counter(str(r[0] or "none") for r in rows)
    by_source = Counter(str(r[1] or "none") for r in rows)
    opened = sum(by_status.values())
    return {
        "state": "ok",
        "opened_this_week": opened,
        "still_open": sum(by_status.get(s, 0) for s in _OPEN_STATUSES),  # open + notified (awaiting the user's answer)
        "by_status": dict(sorted(by_status.items())),
        "by_source": dict(sorted(by_source.items())),
    }


def _l5_state_contract() -> dict[str, Any]:
    from backend.app.services.user_context import user_state

    return {"state": "ok", "contract": user_state.UserState.__name__, "fields": len(user_state.UserState.__dataclass_fields__)}


def build_weekly_layers_report(db: Any, models: Any = None, *, now_utc: Optional[datetime] = None) -> dict[str, Any]:
    if models is None:
        import importlib

        models = importlib.import_module("backend.app.models")
    now = (now_utc or datetime.utcnow()).replace(tzinfo=None)
    since = now - timedelta(days=WINDOW_DAYS)
    return {
        "package_id": PACKAGE_ID,
        "generated_at": now.isoformat(timespec="seconds"),
        "window_days": WINDOW_DAYS,
        "layers": {
            "L1_L2_answer_depth": {"state": "external", "note": DEPTH_AUDIT_NOTE},
            "L3_rag_books": _safe(lambda: _l3_knowledge(db, models)),
            "L4_agent_hands": {
                "notifications": _safe(lambda: _l4_notifications(db, models, since)),
                "user_done": _safe(lambda: _l4_ledger(db, models, since)),
                "commitments": _safe(lambda: _l4_commitments(db, models, since)),
            },
            "L5_state_contract": _safe(_l5_state_contract),
        },
    }


def log_weekly_layers_report(db: Any, models: Any = None) -> Optional[dict[str, Any]]:
    """Weekly-tick hook: one log line; never breaks the weekly run."""
    if db is None:
        return None
    try:
        report = build_weekly_layers_report(db, models)
        logger.info("i5_weekly_layers_report %s", json.dumps(report, sort_keys=True, ensure_ascii=False))
        return report
    except Exception as exc:  # noqa: BLE001 - observability only
        logger.warning("i5_weekly_layers_report_failed %s", type(exc).__name__)
        return None


def main() -> int:
    """Read-only CLI for the production probe: prints one PROBE line, writes nothing."""
    from backend.app.database import get_db

    db = next(get_db())
    try:
        print("PROBE|layers_report|" + json.dumps(build_weekly_layers_report(db), sort_keys=True, ensure_ascii=False))
        return 0
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

"""READ-ONLY diagnostics: did notification reactions (tray buttons, reasons) reach the backend, and what did they change?

Runs inside the backend container via stdin (rollback only). Prints counts, ids, template keys, action/reason codes and times only:
no message text, no user text, no tokens. Output lines start with `DEPTH|` (so the audit workflow's success marker works).
"""
from __future__ import annotations

import json

from sqlalchemy import text


def cols(db, table):
    return {r[0] for r in db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name=:t"), {"t": table})}


def pick(have, wanted):
    return [c for c in wanted if c in have]


def emit(tag, obj):
    print("DEPTH|" + tag + "|" + json.dumps(obj, ensure_ascii=False, default=str)[:3000])


def main() -> None:
    from backend.app.database import get_db

    db = next(get_db())
    try:
        n_cols = cols(db, "notifications")
        e_cols = cols(db, "interaction_events")
        emit("columns", {"notifications": sorted(n_cols)[:60], "interaction_events": sorted(e_cols)[:60]})

        sel = pick(n_cols, ["id", "user_id", "template_key", "channel", "notification_type", "status", "created_at", "sent_at", "delivered_at", "read_at"])
        rows = db.execute(text(f"SELECT {', '.join(sel)} FROM notifications WHERE created_at > now() - interval '72 hours' ORDER BY id DESC LIMIT 40")).mappings().all()
        emit("notifications_72h", {"count": len(rows)})
        for r in rows:
            emit("notif", dict(r))

        e_sel = pick(e_cols, ["id", "user_id", "source_notification_id", "event_type", "reaction", "action_id", "reason", "canonical_verb", "created_at", "occurred_at"])
        order = "created_at" if "created_at" in e_cols else "id"
        ev = db.execute(text(f"SELECT {', '.join(e_sel)} FROM interaction_events WHERE {order} > now() - interval '72 hours' ORDER BY id DESC LIMIT 60")).mappings().all()
        emit("interaction_events_72h", {"count": len(ev)})
        for r in ev:
            emit("event", dict(r))

        by_type = db.execute(text(f"SELECT event_type, COUNT(*) c FROM interaction_events WHERE {order} > now() - interval '7 days' GROUP BY event_type ORDER BY c DESC LIMIT 25")).all()
        emit("event_types_7d", {k: v for k, v in by_type})

        # which notifications got a reaction at all (last 72h)
        got = db.execute(text(
            "SELECT n.template_key, COUNT(DISTINCT n.id) total, COUNT(DISTINCT e.source_notification_id) with_event "
            "FROM notifications n LEFT JOIN interaction_events e ON e.source_notification_id = n.id "
            "WHERE n.created_at > now() - interval '72 hours' GROUP BY n.template_key ORDER BY total DESC LIMIT 25"
        )).all()
        emit("reaction_rate_by_template_72h", {r[0]: [r[1], r[2]] for r in got})

        # push token / device rows (existence only)
        for t in ("device_tokens", "fcm_tokens", "user_devices", "push_tokens"):
            try:
                emit("tokens_" + t, {"rows": db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()})
            except Exception:
                db.rollback()
        print("DEPTH|done|PASS")
    finally:
        db.rollback()
        db.close()


main()

"""A3 Smart Notifications sent-history projection (G1).

Canonical user Inbox = successfully FCM-sent notifications within the visible
retention window. Queued/future/failed/db-only rows remain in DB but are excluded.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Query, Session

from backend.app.models import Notification

# Locked G1 policy (runtime defaults; env override for tests only).
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
USER_VISIBLE_HISTORY_DAYS = int(
    os.getenv("SEDI_A3_INBOX_VISIBLE_DAYS", "180")
)


def visible_cutoff(now: Optional[datetime] = None) -> datetime:
    """Inclusive lower bound for sent_at in the normal A3 Inbox window."""
    ref = now or datetime.utcnow()
    return ref - timedelta(days=USER_VISIBLE_HISTORY_DAYS)


def clamp_limit(limit: Optional[int]) -> int:
    if limit is None:
        return DEFAULT_PAGE_SIZE
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_PAGE_SIZE
    if value < 1:
        return DEFAULT_PAGE_SIZE
    return min(value, MAX_PAGE_SIZE)


def encode_inbox_cursor(*, sent_at: datetime, notification_id: int) -> str:
    """Opaque cursor: base64url(sent_at_iso|id). No new dependency."""
    raw = f"{sent_at.isoformat()}|{int(notification_id)}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_inbox_cursor(cursor: str) -> tuple[datetime, int]:
    padded = (cursor or "").strip() + "=" * ((4 - len((cursor or "").strip()) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        ts_raw, id_raw = raw.split("|", 1)
        sent_at = datetime.fromisoformat(ts_raw)
        return sent_at, int(id_raw)
    except Exception as exc:  # noqa: BLE001 — map to ValueError for HTTP 400
        raise ValueError("INVALID_INBOX_CURSOR") from exc


def apply_sent_history_filters(
    query: Query,
    *,
    now: Optional[datetime] = None,
) -> Query:
    """Filter to normal A3 user history: FCM sent + sent_at present + within window."""
    cutoff = visible_cutoff(now)
    return query.filter(
        Notification.is_sent.is_(True),
        Notification.status == "sent",
        Notification.provider == "fcm",
        Notification.sent_at.isnot(None),
        Notification.sent_at >= cutoff,
    )


def apply_cursor_keyset(
    query: Query,
    *,
    cursor: Optional[str],
) -> Query:
    if not cursor:
        return query
    cursor_sent_at, cursor_id = decode_inbox_cursor(cursor)
    return query.filter(
        or_(
            Notification.sent_at < cursor_sent_at,
            and_(
                Notification.sent_at == cursor_sent_at,
                Notification.id < cursor_id,
            ),
        )
    )


def order_sent_history(query: Query) -> Query:
    return query.order_by(Notification.sent_at.desc(), Notification.id.desc())


def fetch_sent_history_page(
    db: Session,
    *,
    user_id: int,
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
    unread_only: bool = False,
    notification_type: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """
    Return page payload for A3 Inbox / unread list.

    Keys: notifications, next_cursor, has_more, limit, total, unread_count
    """
    page_size = clamp_limit(limit)
    base = db.query(Notification).filter(Notification.user_id == user_id)
    base = apply_sent_history_filters(base, now=now)

    total = base.count()
    unread_count = base.filter(Notification.is_read.is_(False)).count()

    page_q = base
    if unread_only:
        page_q = page_q.filter(Notification.is_read.is_(False))
    if notification_type:
        page_q = page_q.filter(Notification.type == notification_type)

    page_q = apply_cursor_keyset(page_q, cursor=cursor)
    page_q = order_sent_history(page_q)
    rows = page_q.limit(page_size + 1).all()
    has_more = len(rows) > page_size
    page_rows = rows[:page_size]
    next_cursor = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = encode_inbox_cursor(sent_at=last.sent_at, notification_id=last.id)

    return {
        "notifications": page_rows,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "limit": page_size,
        "total": total if not unread_only else unread_count,
        "unread_count": unread_count,
        "count": len(page_rows),
    }

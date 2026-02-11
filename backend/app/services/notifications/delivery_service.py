# app/services/notifications/delivery_service.py
"""
Notification delivery outbox: query unsent, send via pluggable adapter, mark is_sent.
Safe to run repeatedly (idempotent). Stage 16.6: FCM adapter for push.
Stage 16.6.2: Batching, timeouts, in-process retries, structured logs.
"""

import logging
import os
import time
from datetime import datetime
from typing import Optional, Protocol

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.app.models import Notification, PushDevice

logger = logging.getLogger(__name__)

# Stage 16.6.2: Env vars with safe defaults
_DELIVER_BATCH_SIZE = int(os.getenv("DELIVER_BATCH_SIZE", "200"))
_FCM_MAX_RETRIES = int(os.getenv("FCM_MAX_RETRIES", "2"))
_FCM_BACKOFF_SECONDS = int(os.getenv("FCM_BACKOFF_SECONDS", "10"))

# Lightweight health: last run timestamp (updated each deliver_pending)
last_deliver_pending_run_at: Optional[datetime] = None


class DeliveryAdapter(Protocol):
    """Pluggable adapter for sending a notification. Return True on success."""

    def send(self, notification: Notification) -> bool:
        ...


class LoggingOnlyAdapter:
    """Default adapter: log to stdout/logger, no external provider. channel='db_only'."""

    channel = "db_only"

    def send(self, notification: Notification) -> bool:
        logger.info(
            "[NOTIF] sent notification_id=%s user_id=%s channel=%s provider=db_only",
            notification.id, notification.user_id, (notification.channel or notification.type or "?"),
        )
        return True


default_logging_adapter = LoggingOnlyAdapter()


# -------------------- Stage 16.6: FCM Adapter --------------------
def _get_fcm_tokens_for_user(db: Session, user_id: int, limit: int = 10) -> list:
    """Return list of active FCM tokens for user (android)."""
    rows = (
        db.query(PushDevice.fcm_token)
        .filter(
            PushDevice.user_id == user_id,
            PushDevice.is_active == True,  # noqa: E712
            PushDevice.platform == "android",
        )
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows if r[0]]


class FCMAdapter:
    """Send notification via FCM HTTP v1; update notification status and provider fields."""

    channel = "fcm"

    def __init__(self, db: Session, timeout_sec: int = 15):
        self.db = db
        self.timeout_sec = timeout_sec

    def send(self, notification: Notification) -> bool:
        tokens = _get_fcm_tokens_for_user(self.db, notification.user_id)
        if not tokens:
            logger.info(
                "[NOTIF] failed notification_id=%s user_id=%s error=No active FCM tokens for user",
                notification.id, notification.user_id,
            )
            notification.provider = "fcm"
            notification.status = "failed"
            notification.last_error = "No active FCM tokens for user"
            return False

        title = (notification.title or notification.type or "Notification").strip() or "Sedi"
        body = (notification.body or "").strip() or "New notification"
        data = {
            "notification_id": str(notification.id),
            "channel": (notification.channel or notification.type or ""),
            "type": notification.type or "",
        }
        if notification.deeplink_url:
            data["deeplink_url"] = notification.deeplink_url[:512]
        if notification.actions_json:
            data["actions"] = notification.actions_json[:1024]

        from backend.app.services.notifications.fcm_client import send_push_to_tokens

        success_count, results = send_push_to_tokens(
            tokens=tokens,
            title=title,
            body=body,
            data=data,
            android_priority=notification.priority or "normal",
            ttl_seconds=notification.ttl_seconds,
            timeout_sec=self.timeout_sec,
        )
        now = datetime.utcnow()
        notification.provider = "fcm"
        notification.sent_at = now
        if success_count > 0:
            notification.is_sent = True
            notification.status = "sent"
            first_id = next((r[1] for r in results if r[1]), None)
            notification.provider_message_id = first_id
            notification.last_error = None
            if success_count < len(tokens):
                notification.last_error = f"Partial: {success_count}/{len(tokens)} sent"
            logger.info(
                "[NOTIF] sent notification_id=%s user_id=%s token_count=%s provider_id=%s",
                notification.id, notification.user_id, success_count, first_id or "?",
            )
            return True
        notification.is_sent = False
        notification.status = "failed"
        errs = [r[2] for r in results if r[2]]
        notification.last_error = errs[0][:500] if errs else "Send failed"
        logger.info(
            "[NOTIF] failed notification_id=%s user_id=%s error=%s",
            notification.id, notification.user_id, (errs[0][:200] if errs else "Send failed"),
        )
        return False


# -------------------- DeliveryService --------------------


def _fcm_timeout_sec() -> int:
    """Stage 16.6.2: FCM_TIMEOUT_SECONDS env (default 5)."""
    try:
        return int(os.getenv("FCM_TIMEOUT_SECONDS", "5"))
    except ValueError:
        return 5


def _default_adapter(db: Session) -> DeliveryAdapter:
    """Use FCM when configured (FCM_PROJECT_ID + credentials); else logging-only (Stage 16.6)."""
    if os.getenv("FCM_DISABLED", "").lower() in ("true", "1", "yes"):
        return default_logging_adapter
    if os.getenv("FCM_PROJECT_ID", "").strip() and os.getenv("FCM_SERVICE_ACCOUNT_JSON", "").strip():
        return FCMAdapter(db=db, timeout_sec=_fcm_timeout_sec())
    return default_logging_adapter


class DeliveryService:
    """Query unsent notifications, send via adapter, mark is_sent (and sent_at if present)."""

    def __init__(self, db: Session, adapter: Optional[DeliveryAdapter] = None):
        self.db = db
        self.adapter = adapter if adapter is not None else _default_adapter(db)

    def deliver_pending(self, limit: Optional[int] = None) -> int:
        """
        Select notifications where is_sent=false and (scheduled_for is null or scheduled_for <= now),
        send each via adapter (with in-process retries), mark is_sent=True on success.
        Stage 16.6.2: Uses DELIVER_BATCH_SIZE; in-process retry with backoff up to FCM_MAX_RETRIES.
        """
        global last_deliver_pending_run_at
        now = datetime.utcnow()
        batch_size = limit if limit is not None else _DELIVER_BATCH_SIZE
        batch_size = min(batch_size, _DELIVER_BATCH_SIZE)

        pending = (
            self.db.query(Notification)
            .filter(Notification.is_sent == False)  # noqa: E712
            .filter(or_(Notification.scheduled_for.is_(None), Notification.scheduled_for <= now))
            .order_by(Notification.created_at.asc())
            .limit(batch_size)
            .all()
        )
        last_deliver_pending_run_at = now
        logger.info("[NOTIF] deliver batch_size=%s pending_count=%s", batch_size, len(pending))

        sent_count = 0
        for notification in pending:
            success = False
            last_err = None
            for attempt in range(_FCM_MAX_RETRIES + 1):
                try:
                    if self.adapter.send(notification):
                        if not getattr(notification, "is_sent", None):
                            notification.is_sent = True
                        if not getattr(notification, "sent_at", None):
                            notification.sent_at = now
                        self.db.add(notification)
                        self.db.commit()
                        self.db.refresh(notification)
                        sent_count += 1
                        success = True
                        break
                    else:
                        self.db.rollback()
                        last_err = notification.last_error
                        if attempt < _FCM_MAX_RETRIES:
                            time.sleep(_FCM_BACKOFF_SECONDS)
                except Exception as e:
                    self.db.rollback()
                    last_err = str(e)
                    logger.warning(
                        "[NOTIF] failed notification_id=%s user_id=%s attempt=%s error=%s",
                        notification.id, notification.user_id, attempt + 1, str(e),
                    )
                    if attempt < _FCM_MAX_RETRIES:
                        time.sleep(_FCM_BACKOFF_SECONDS)
            if not success:
                try:
                    notification.status = "failed"
                    notification.last_error = (last_err or "Send failed")[:500]
                    self.db.add(notification)
                    self.db.commit()
                except Exception:
                    self.db.rollback()
        return sent_count

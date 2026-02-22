# app/services/notifications/delivery_service.py
"""
Notification delivery outbox: query unsent, send via pluggable adapter, mark is_sent.
Safe to run repeatedly (idempotent). Stage 16.6: FCM adapter for push.
Stage 16.6.2: Batching, timeouts, in-process retries, structured logs.
"""

import logging
import os
import threading
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

# Runtime lock: prevents re-entrancy (scheduler + HTTP endpoint). V1 overlap mitigation.
_deliver_pending_lock = threading.Lock()


class DeliveryAdapter(Protocol):
    """Pluggable adapter for sending a notification. Return True on success."""

    def send(self, notification: Notification) -> bool:
        ...


class LoggingOnlyAdapter:
    """Default adapter: log to stdout/logger, no external provider. channel='db_only'."""

    channel = "db_only"

    def send(self, notification: Notification) -> bool:
        notification.provider = "db_only"
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
        # Stage 19: device_disconnected without channel => engagement
        effective_channel = (notification.channel or "").strip()
        if not effective_channel and notification.type == "device_disconnected":
            effective_channel = "engagement"
        if not effective_channel:
            effective_channel = notification.type or ""
        data = {
            "notification_id": str(notification.id),
            "channel": effective_channel,
            "type": notification.type or "",
        }
        if notification.deeplink_url:
            data["deeplink_url"] = notification.deeplink_url[:512]
        if notification.actions_json:
            data["actions"] = notification.actions_json[:1024]

        from backend.app.services.notifications.fcm_client import (
            send_push_to_tokens,
            parse_fcm_error,
            FCM_DEACTIVATE_ERROR_CODES,
        )

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
        # Stage 19: deactivate tokens that FCM reports as UNREGISTERED/NOT_FOUND
        for fcm_token, _msg_id, err in results:
            if err:
                err_parsed = parse_fcm_error(err)
                if err_parsed and err_parsed.get("code") in FCM_DEACTIVATE_ERROR_CODES:
                    dev = self.db.query(PushDevice).filter(
                        PushDevice.fcm_token == fcm_token,
                        PushDevice.user_id == notification.user_id,
                    ).first()
                    if dev:
                        dev.is_active = False
                        dev.updated_at = datetime.utcnow()
                        self.db.add(dev)
                        logger.info(
                            "[NOTIF] token deactivated notification_id=%s user_id=%s reason=%s",
                            notification.id, notification.user_id, err_parsed.get("code"),
                        )
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()

        if success_count > 0:
            notification.sent_at = now
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
        V1: In-process lock prevents overlap (scheduler + HTTP); skip if already running.
        """
        if not _deliver_pending_lock.acquire(blocking=False):
            logger.info("[NOTIF] deliver_pending skipped: lock held (previous run in progress)")
            return 0
        try:
            return self._deliver_pending_impl(limit)
        finally:
            _deliver_pending_lock.release()

    def _deliver_pending_impl(self, limit: Optional[int] = None) -> int:
        """Inner implementation (called under _deliver_pending_lock)."""
        global last_deliver_pending_run_at
        t0 = time.perf_counter()
        now = datetime.utcnow()
        batch_size = limit if limit is not None else _DELIVER_BATCH_SIZE
        batch_size = min(batch_size, _DELIVER_BATCH_SIZE)

        pending = (
            self.db.query(Notification)
            .filter(Notification.is_sent == False)  # noqa: E712
            .filter(or_(Notification.scheduled_for.is_(None), Notification.scheduled_for <= now))
            # Do NOT retry permanent failures forever; only process fresh/queued items
            .filter(
                or_(
                    Notification.status.is_(None),
                    Notification.status == "queued",
                )
            )
            .order_by(Notification.created_at.asc())
            .limit(batch_size)
            .all()
        )
        last_deliver_pending_run_at = now
        logger.info("[NOTIF] deliver_pending start batch_size=%s pending_count=%s", batch_size, len(pending))

        sent_count = 0
        for notification in pending:
            success = False
            last_err = None
            nid = notification.id
            uid = notification.user_id
            for attempt in range(_FCM_MAX_RETRIES + 1):
                try:
                    if self.adapter.send(notification):
                        if not getattr(notification, "is_sent", None):
                            notification.is_sent = True
                        if not getattr(notification, "sent_at", None):
                            notification.sent_at = now
                        if getattr(notification, "status", None) != "sent":
                            notification.status = "sent"
                        # Deterministic persistence: always set provider from adapter channel on success.
                        # (Fixes cases where adapter mutates provider but ORM doesn't persist it reliably.)
                        notification.provider = getattr(self.adapter, "channel", None) or "db_only"
                        self.db.add(notification)
                        self.db.flush()
                        self.db.commit()
                        # refresh is optional; keep it only if you really need fresh DB state
                        # self.db.refresh(notification)
                        sent_count += 1
                        success = True
                        break
                    else:
                        # capture adapter-provided error BEFORE rollback (rollback may expire attrs)
                        last_err = notification.last_error
                        self.db.rollback()
                        if attempt < _FCM_MAX_RETRIES:
                            time.sleep(_FCM_BACKOFF_SECONDS)
                except Exception as e:
                    # Do not rollback: adapter failure is not a DB failure; rollback would expire
                    # the notification instance and break the final-failure persist and test fixtures.
                    last_err = repr(e)
                    logger.warning(
                        "[NOTIF] failed notification_id=%s user_id=%s attempt=%s error=%s",
                        nid, uid, attempt + 1, repr(e),
                    )
                    if attempt < _FCM_MAX_RETRIES:
                        time.sleep(_FCM_BACKOFF_SECONDS)
            if not success:
                try:
                    notification.status = "failed"
                    notification.last_error = (last_err or "Send failed")[:500]
                    notification.provider = getattr(self.adapter, "channel", None) or "db_only"
                    self.db.add(notification)
                    self.db.commit()
                except Exception:
                    self.db.rollback()
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info("[NOTIF] deliver_pending end duration_ms=%s sent_count=%s", duration_ms, sent_count)
        return sent_count

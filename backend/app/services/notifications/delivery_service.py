# app/services/notifications/delivery_service.py
"""
Notification delivery outbox: query unsent, send via pluggable adapter, mark is_sent.
Safe to run repeatedly (idempotent).
"""

import logging
from datetime import datetime
from typing import Optional, Protocol

from sqlalchemy.orm import Session

from app.models import Notification

logger = logging.getLogger(__name__)


class DeliveryAdapter(Protocol):
    """Pluggable adapter for sending a notification. Return True on success."""

    def send(self, notification: Notification) -> bool:
        ...


class LoggingOnlyAdapter:
    """Default adapter: log to stdout/logger, no external provider. channel='db_only'."""

    channel = "db_only"

    def send(self, notification: Notification) -> bool:
        logger.info(
            "[DELIVERY] channel=%s id=%s user_id=%s type=%s priority=%s title=%s",
            self.channel,
            notification.id,
            notification.user_id,
            notification.type,
            notification.priority,
            (notification.title or "")[:50],
        )
        return True


default_logging_adapter = LoggingOnlyAdapter()


class DeliveryService:
    """Query unsent notifications, send via adapter, mark is_sent (and sent_at if present)."""

    def __init__(self, db: Session, adapter: Optional[DeliveryAdapter] = None):
        self.db = db
        self.adapter = adapter or default_logging_adapter

    def deliver_pending(self, limit: int = 100) -> int:
        """
        Select notifications where is_sent=false (optionally scheduled_for <= now),
        send each via adapter, mark is_sent=True and sent_at=now on success.
        Returns count of notifications marked as sent.
        """
        now = datetime.utcnow()
        pending = (
            self.db.query(Notification)
            .filter(Notification.is_sent == False)  # noqa: E712
            .order_by(Notification.created_at.asc())
            .limit(limit)
            .all()
        )
        sent_count = 0
        for notification in pending:
            try:
                if self.adapter.send(notification):
                    notification.is_sent = True
                    notification.sent_at = now
                    self.db.add(notification)
                    self.db.commit()
                    self.db.refresh(notification)
                    sent_count += 1
                else:
                    self.db.rollback()
            except Exception as e:
                logger.warning(
                    "[DELIVERY] Failed to send notification id=%s: %s",
                    notification.id,
                    e,
                    exc_info=True,
                )
                self.db.rollback()
        return sent_count

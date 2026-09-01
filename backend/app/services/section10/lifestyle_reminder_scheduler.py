"""Lifestyle reminder generation — B13 delegates to I8 operational plan coaching (I10)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.services.section10 import feature_flags


def process_lifestyle_reminders(db: Session, now: Optional[datetime] = None) -> int:
    """Legacy scheduler entry — canonical path is I8 plan action coaching via I10."""
    if not feature_flags.lifestyle_reminder_scheduler_enabled():
        return 0
    from backend.app.services.i10.coaching_worker import process_i8_coaching_followups

    return process_i8_coaching_followups(db, now=now, force=True)

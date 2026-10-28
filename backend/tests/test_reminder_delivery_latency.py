"""Javad 2026-10-28 phone test: Sedi promised a reminder for 20:52 and it arrived at 20:59.

Cause: the reminder scheduler enqueued every 5 minutes and the notification outbox sent every 5 minutes, so a reminder could
be up to ~10 minutes late. The tick now polls every minute and flushes the outbox right after it queued something."""
from __future__ import annotations

import re
from pathlib import Path

SCHEDULER = Path(__file__).resolve().parents[1] / "app" / "core" / "scheduler.py"


def _tick_block() -> str:
    src = SCHEDULER.read_text(encoding="utf-8")
    start = src.index("def _section10_reminder_tick")
    end = src.index('id="section10_reminder_schedulers"', start)
    return src[start:end]


def test_reminder_tick_runs_every_minute():
    block = _tick_block()
    assert re.search(r"minutes=1\b", block), "reminders must be checked every minute"


def test_reminder_tick_flushes_the_outbox_when_it_queued_something():
    block = _tick_block()
    assert "run_deliver_pending()" in block
    assert "if created" in block
    # delivery problems must never break the reminder tick (fail-open, the regular outbox run retries)
    assert "except Exception" in block

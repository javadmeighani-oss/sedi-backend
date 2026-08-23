"""I8 environment feature flags (default OFF)."""

from __future__ import annotations

import os

_TRUE = frozenset({"1", "true", "yes", "on"})

I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG = "SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED"
I8_PROACTIVE_SCHEDULE_SCAN_BATCH_ENV = "SEDI_I8_PROACTIVE_SCHEDULE_SCAN_BATCH_SIZE"
I8_PROACTIVE_SCHEDULE_SCAN_INTERVAL_ENV = "SEDI_I8_PROACTIVE_SCHEDULE_SCAN_INTERVAL_MINUTES"

_DEFAULT_BATCH = 50
_MAX_BATCH = 200

# Historical registration default only — not a final product cadence decision.
_DEFAULT_INTERVAL_MINUTES = 15
_MIN_INTERVAL_MINUTES = 5
_MAX_INTERVAL_MINUTES = 1440


def _env_flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def i8_proactive_schedule_trigger_enabled() -> bool:
    """Default OFF. When false, schedule scan must not emit or evaluate."""
    return _env_flag_enabled(I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG)


def i8_proactive_schedule_scan_batch_size() -> int:
    raw = os.environ.get(I8_PROACTIVE_SCHEDULE_SCAN_BATCH_ENV, "").strip()
    if not raw:
        return _DEFAULT_BATCH
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_BATCH
    if value < 1:
        return 1
    return min(value, _MAX_BATCH)


def i8_proactive_schedule_scan_interval_minutes() -> int:
    """Configurable I8 schedule-scan cadence (minutes), bounded with safe fallback."""
    raw = os.environ.get(I8_PROACTIVE_SCHEDULE_SCAN_INTERVAL_ENV, "").strip()
    if not raw:
        return _DEFAULT_INTERVAL_MINUTES
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_INTERVAL_MINUTES
    if value < _MIN_INTERVAL_MINUTES:
        return _MIN_INTERVAL_MINUTES
    if value > _MAX_INTERVAL_MINUTES:
        return _MAX_INTERVAL_MINUTES
    return value

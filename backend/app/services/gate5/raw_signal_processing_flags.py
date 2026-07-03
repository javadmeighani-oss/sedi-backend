"""Gate 5-D — Environment-driven flags for raw signal processing operations (default OFF)."""

from __future__ import annotations

import os

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

ABSOLUTE_MAX_LIMIT = 25
DEFAULT_MAX_LIMIT = 10
DEFAULT_INTERVAL_MIN = 15


def _env_flag_enabled(name: str) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return raw in _TRUE_VALUES


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def raw_signal_processing_enabled() -> bool:
    """When True, register scheduler job for pending raw signal feature extraction."""
    return _env_flag_enabled("SEDI_RAW_SIGNAL_PROCESSING_ENABLED")


def raw_signal_processing_interval_minutes() -> int:
    """Scheduler tick interval when enabled (clamped 5–1440)."""
    value = _int_env("SEDI_RAW_SIGNAL_PROCESSING_INTERVAL_MIN", DEFAULT_INTERVAL_MIN)
    return max(5, min(24 * 60, value))


def raw_signal_processing_max_limit() -> int:
    """
    Per-run batch cap for ops and scheduler.
    Defaults to 10; invalid/zero/negative/>25 values fall back to 10.
    """
    value = _int_env("SEDI_RAW_SIGNAL_PROCESSING_MAX_LIMIT", DEFAULT_MAX_LIMIT)
    if value <= 0 or value > ABSOLUTE_MAX_LIMIT:
        return DEFAULT_MAX_LIMIT
    return value

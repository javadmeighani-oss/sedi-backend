"""API vs scheduler process-role helpers (capacity hardening).

Preserves existing ``SEDI_DISABLE_SCHEDULER`` semantics.
Optional ``SEDI_PROCESS_ROLE`` clarifies multi-worker deployment:

- ``api`` — never start APScheduler (safe for N uvicorn workers)
- ``scheduler`` — start APScheduler (exactly one such process)
- ``combined`` / unset — legacy single-process behavior
"""

from __future__ import annotations

import os
from typing import Literal

ProcessRole = Literal["api", "scheduler", "combined"]


def resolve_process_role() -> ProcessRole:
    raw = (os.getenv("SEDI_PROCESS_ROLE") or "").strip().lower()
    if raw in ("api", "api_worker", "web"):
        return "api"
    if raw in ("scheduler", "background", "worker_scheduler"):
        return "scheduler"
    return "combined"


def scheduler_env_disabled() -> bool:
    """True when SEDI_DISABLE_SCHEDULER requests scheduler off."""
    v = os.getenv("SEDI_DISABLE_SCHEDULER", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def should_start_scheduler() -> bool:
    """Return False for tests, API role, or explicit disable; True otherwise."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False
    if resolve_process_role() == "api":
        return False
    if scheduler_env_disabled():
        return False
    return True


def uvicorn_workers_configured() -> int:
    """Configurable worker count hint (not activated for production by this Gate)."""
    for key in ("UVICORN_WORKERS", "WEB_CONCURRENCY", "SEDI_API_WORKERS"):
        raw = (os.getenv(key) or "").strip()
        if not raw:
            continue
        try:
            n = int(raw)
        except ValueError:
            continue
        if n >= 1:
            return n
    return 1

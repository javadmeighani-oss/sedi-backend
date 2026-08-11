"""KNOW-05 operational modes — Production weekly is never authorized here."""

from __future__ import annotations

from enum import Enum


class Know05Mode(str, Enum):
    DRY_RUN = "DRY_RUN"
    LIVE_CANARY = "LIVE_CANARY"
    BOUNDED_INGESTION = "BOUNDED_INGESTION"
    WEEKLY_REHEARSAL = "WEEKLY_REHEARSAL"
    PRODUCTION_WEEKLY = "PRODUCTION_WEEKLY"


AUTHORIZED_MODES = frozenset(
    {
        Know05Mode.DRY_RUN,
        Know05Mode.LIVE_CANARY,
        Know05Mode.BOUNDED_INGESTION,
        Know05Mode.WEEKLY_REHEARSAL,
    }
)


class Know05ModeError(PermissionError):
    pass


def assert_mode_authorized(mode: Know05Mode | str) -> Know05Mode:
    m = Know05Mode(mode)
    if m == Know05Mode.PRODUCTION_WEEKLY:
        raise Know05ModeError("PRODUCTION_WEEKLY_NOT_AUTHORIZED")
    if m not in AUTHORIZED_MODES:
        raise Know05ModeError(f"MODE_NOT_AUTHORIZED:{m.value}")
    return m


def production_activation_flags() -> dict[str, bool]:
    return {
        "production_write": False,
        "production_migration_run": False,
        "production_crawler_activated": False,
        "production_scheduler_activated": False,
        "production_rag_activated": False,
        "production_weekly": False,
    }

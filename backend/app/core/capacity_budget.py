"""DB connection budget helpers for multi-worker capacity planning.

Formula (documented + tested; production values NOT activated by this Gate):

TOTAL_POTENTIAL_APP_CONNECTIONS =
  API_WORKERS × (POOL_SIZE + MAX_OVERFLOW)
  + BACKGROUND_PROCESS_DB_CAPACITY
  + RESERVED_OPERATIONAL_MARGIN
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple


_POOL_SIZE_DEFAULT = 5
_MAX_OVERFLOW_DEFAULT = 10
_POOL_RECYCLE_DEFAULT = 1800
_POOL_TIMEOUT_DEFAULT = 30

# Hard caps to prevent accidental worker×pool explosion via env typos.
_POOL_SIZE_MAX = 50
_MAX_OVERFLOW_MAX = 50
_API_WORKERS_MAX = 32


def _parse_int_env(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> Tuple[int, str]:
    """Parse int env. Invalid/out-of-range → deterministic default fallback."""
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default, "default"
    try:
        val = int(str(raw).strip())
    except ValueError:
        return default, "invalid_fallback"
    if val < minimum or val > maximum:
        return default, "range_fallback"
    return val, "env"


def resolve_pool_size() -> Tuple[int, str]:
    return _parse_int_env(
        "SEDI_DB_POOL_SIZE",
        _POOL_SIZE_DEFAULT,
        minimum=1,
        maximum=_POOL_SIZE_MAX,
    )


def resolve_max_overflow() -> Tuple[int, str]:
    return _parse_int_env(
        "SEDI_DB_MAX_OVERFLOW",
        _MAX_OVERFLOW_DEFAULT,
        minimum=0,
        maximum=_MAX_OVERFLOW_MAX,
    )


def resolve_pool_recycle() -> Tuple[int, str]:
    return _parse_int_env(
        "SEDI_DB_POOL_RECYCLE",
        _POOL_RECYCLE_DEFAULT,
        minimum=60,
        maximum=7200,
    )


def resolve_pool_timeout() -> Tuple[int, str]:
    return _parse_int_env(
        "SEDI_DB_POOL_TIMEOUT",
        _POOL_TIMEOUT_DEFAULT,
        minimum=1,
        maximum=120,
    )


@dataclass(frozen=True)
class ConnectionBudget:
    api_workers: int
    pool_size: int
    max_overflow: int
    background_process_db_capacity: int
    reserved_operational_margin: int

    @property
    def per_api_worker_capacity(self) -> int:
        return int(self.pool_size) + int(self.max_overflow)

    @property
    def total_potential_app_connections(self) -> int:
        return (
            int(self.api_workers) * self.per_api_worker_capacity
            + int(self.background_process_db_capacity)
            + int(self.reserved_operational_margin)
        )


def compute_connection_budget(
    *,
    api_workers: int,
    pool_size: int,
    max_overflow: int,
    background_process_db_capacity: int,
    reserved_operational_margin: int = 5,
) -> ConnectionBudget:
    if api_workers < 1 or api_workers > _API_WORKERS_MAX:
        raise ValueError("api_workers out of safe planning range")
    if pool_size < 1 or pool_size > _POOL_SIZE_MAX:
        raise ValueError("pool_size out of safe planning range")
    if max_overflow < 0 or max_overflow > _MAX_OVERFLOW_MAX:
        raise ValueError("max_overflow out of safe planning range")
    if background_process_db_capacity < 0:
        raise ValueError("background_process_db_capacity must be >= 0")
    if reserved_operational_margin < 0:
        raise ValueError("reserved_operational_margin must be >= 0")
    return ConnectionBudget(
        api_workers=int(api_workers),
        pool_size=int(pool_size),
        max_overflow=int(max_overflow),
        background_process_db_capacity=int(background_process_db_capacity),
        reserved_operational_margin=int(reserved_operational_margin),
    )


def budget_from_env(
    *,
    api_workers: Optional[int] = None,
    background_process_db_capacity: Optional[int] = None,
    reserved_operational_margin: int = 5,
) -> ConnectionBudget:
    """Build budget using current env pool defaults (no production activation)."""
    from backend.app.core.process_role import uvicorn_workers_configured

    workers = int(api_workers) if api_workers is not None else uvicorn_workers_configured()
    pool_size, _ = resolve_pool_size()
    max_overflow, _ = resolve_max_overflow()
    # One scheduler/background process uses the same pool settings by default.
    bg = (
        int(background_process_db_capacity)
        if background_process_db_capacity is not None
        else (pool_size + max_overflow)
    )
    return compute_connection_budget(
        api_workers=workers,
        pool_size=pool_size,
        max_overflow=max_overflow,
        background_process_db_capacity=bg,
        reserved_operational_margin=reserved_operational_margin,
    )


CONNECTION_BUDGET_FORMULA = (
    "TOTAL_POTENTIAL_APP_CONNECTIONS = "
    "API_WORKERS × (POOL_SIZE + MAX_OVERFLOW) "
    "+ BACKGROUND_PROCESS_DB_CAPACITY "
    "+ RESERVED_OPERATIONAL_MARGIN"
)

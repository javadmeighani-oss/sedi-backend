"""Lightweight capacity observability (structured logs only; no PHI).

No external monitoring platform dependency.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger("sedi.capacity")

_inflight_lock = threading.Lock()
_inflight = 0
_inflight_peak = 0


def _safe_fields(**kwargs: Any) -> Dict[str, Any]:
    """Drop None and never accept reserved sensitive keys."""
    banned = {
        "message",
        "body",
        "prompt",
        "token",
        "password",
        "phone",
        "chunk",
        "rag_chunk",
        "measurement",
        "raw",
        "authorization",
        "api_key",
    }
    out: Dict[str, Any] = {}
    for k, v in kwargs.items():
        lk = str(k).lower()
        if lk in banned or any(b in lk for b in ("phone", "token", "password", "secret")):
            continue
        if v is None:
            continue
        out[k] = v
    return out


def log_event(event: str, **kwargs: Any) -> None:
    fields = _safe_fields(**kwargs)
    parts = [f"event={event}"] + [f"{k}={v}" for k, v in fields.items()]
    logger.info("capacity " + " ".join(parts))


def inflight_inc() -> int:
    global _inflight, _inflight_peak
    with _inflight_lock:
        _inflight += 1
        if _inflight > _inflight_peak:
            _inflight_peak = _inflight
        return _inflight


def inflight_dec() -> int:
    global _inflight
    with _inflight_lock:
        _inflight = max(0, _inflight - 1)
        return _inflight


def inflight_snapshot() -> Dict[str, int]:
    with _inflight_lock:
        return {"inflight": _inflight, "inflight_peak": _inflight_peak}


@contextmanager
def track_request(route: str) -> Iterator[None]:
    n = inflight_inc()
    t0 = time.perf_counter()
    status = "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        left = inflight_dec()
        log_event(
            "http_request",
            route=route,
            duration_ms=duration_ms,
            status=status,
            inflight_start=n,
            inflight_end=left,
        )


@contextmanager
def track_span(event: str, **kwargs: Any) -> Iterator[Dict[str, Any]]:
    t0 = time.perf_counter()
    meta: Dict[str, Any] = dict(kwargs)
    status = "ok"
    error_class: Optional[str] = None
    try:
        yield meta
    except Exception as exc:
        status = "error"
        error_class = type(exc).__name__
        raise
    finally:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        log_event(
            event,
            duration_ms=duration_ms,
            status=status,
            error_class=error_class,
            **meta,
        )


def pool_visibility(engine) -> Dict[str, Any]:
    """Best-effort SQLAlchemy pool checked-out / overflow visibility."""
    out: Dict[str, Any] = {}
    try:
        pool = engine.pool
        checked_out = getattr(pool, "checkedout", None)
        if callable(checked_out):
            out["pool_checked_out"] = int(checked_out())
        size = getattr(pool, "size", None)
        if callable(size):
            out["pool_size"] = int(size())
        overflow = getattr(pool, "overflow", None)
        if callable(overflow):
            out["pool_overflow"] = int(overflow())
    except Exception:
        out["pool_visibility"] = "unavailable"
    return out

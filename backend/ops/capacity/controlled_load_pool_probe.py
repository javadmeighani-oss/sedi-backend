"""Harness-only SQLAlchemy QueuePool probe (shared file counters).

Installed in controlled-load ASGI workers. Not a production dependency.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict

_STATS_PATH = Path(os.environ.get("SEDI_CAPACITY_POOL_STATS_FILE", "/tmp/sedi_pool_probe.json"))
_lock = threading.Lock()
_local = {
    "checkout_peak": 0,
    "overflow_peak": 0,
    "timeouts": 0,
    "connection_errors": 0,
    "checkouts": 0,
    "worker_pid": os.getpid(),
}


def _flush() -> None:
    payload = {
        "ts": time.time(),
        "pid": os.getpid(),
        **_local,
    }
    try:
        _STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATS_PATH.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        # Aggregate file: append-only JSONL for harness to reduce
        with open(str(_STATS_PATH) + "l", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
        tmp.replace(_STATS_PATH)
    except Exception:  # noqa: BLE001
        pass


def install_pool_probe(engine) -> None:
    """Attach checkout peak + TimeoutError counters to engine pool."""
    from sqlalchemy import event
    from sqlalchemy.exc import TimeoutError as SATimeoutError

    pool = engine.pool

    @event.listens_for(pool, "checkout")
    def _on_checkout(dbapi_conn, connection_rec, connection_proxy):  # noqa: ARG001
        with _lock:
            _local["checkouts"] += 1
            try:
                co = int(pool.checkedout())
                ov = int(pool.overflow())
            except Exception:  # noqa: BLE001
                co, ov = 0, 0
            _local["checkout_peak"] = max(_local["checkout_peak"], co)
            _local["overflow_peak"] = max(_local["overflow_peak"], ov)
            if _local["checkouts"] % 25 == 0:
                _flush()

    # Wrap _do_get to classify QueuePool timeouts directly
    if getattr(pool, "_sedi_probe_wrapped", False):
        return
    orig = pool._do_get

    def _do_get_probed():  # type: ignore[no-untyped-def]
        try:
            return orig()
        except SATimeoutError:
            with _lock:
                _local["timeouts"] += 1
            _flush()
            raise
        except Exception as exc:
            name = type(exc).__name__
            if "Timeout" in name or "timeout" in str(exc).lower():
                with _lock:
                    _local["timeouts"] += 1
                    _local["connection_errors"] += 1
                _flush()
            else:
                with _lock:
                    _local["connection_errors"] += 1
            raise

    pool._do_get = _do_get_probed  # type: ignore[method-assign]
    pool._sedi_probe_wrapped = True  # type: ignore[attr-defined]
    _flush()


def read_aggregated_pool_stats() -> Dict[str, Any]:
    """Harness-side aggregation across worker JSONL samples."""
    path = Path(str(_STATS_PATH) + "l")
    peak_co = 0
    peak_ov = 0
    timeouts = 0
    conn_err = 0
    by_pid: Dict[int, Dict[str, int]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            pid = int(row.get("pid") or 0)
            cur = by_pid.setdefault(pid, {"checkout_peak": 0, "overflow_peak": 0, "timeouts": 0, "connection_errors": 0})
            cur["checkout_peak"] = max(cur["checkout_peak"], int(row.get("checkout_peak") or 0))
            cur["overflow_peak"] = max(cur["overflow_peak"], int(row.get("overflow_peak") or 0))
            cur["timeouts"] = max(cur["timeouts"], int(row.get("timeouts") or 0))
            cur["connection_errors"] = max(cur["connection_errors"], int(row.get("connection_errors") or 0))
    for cur in by_pid.values():
        peak_co = max(peak_co, cur["checkout_peak"])
        peak_ov = max(peak_ov, cur["overflow_peak"])
        timeouts += cur["timeouts"]
        conn_err += cur["connection_errors"]
    # Also sum checkout peaks across workers as envelope pressure
    sum_co = sum(c["checkout_peak"] for c in by_pid.values())
    return {
        "DB_POOL_CHECKOUT_PEAK": peak_co,
        "DB_POOL_CHECKOUT_PEAK_SUM_WORKERS": sum_co,
        "DB_POOL_OVERFLOW_PEAK": peak_ov,
        "DB_POOL_TIMEOUTS": timeouts,
        "DB_CONNECTION_ERRORS": conn_err,
        "worker_samples": by_pid,
        "measured": bool(by_pid),
    }


def reset_pool_stats_files() -> None:
    for p in (_STATS_PATH, Path(str(_STATS_PATH) + "l")):
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass

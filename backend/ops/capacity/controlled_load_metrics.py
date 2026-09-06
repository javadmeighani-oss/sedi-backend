"""Controlled-load metrics helpers (Gate load validation only)."""

from __future__ import annotations

import json
import math
import statistics
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def percentile(sorted_vals: Sequence[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    return float(sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f))


@dataclass
class LatencyBucket:
    name: str
    latencies_ms: List[float] = field(default_factory=list)
    ok: int = 0
    fail: int = 0
    timeout: int = 0
    status_codes: Dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, ms: float, code: int, *, timed_out: bool = False) -> None:
        with self._lock:
            self.latencies_ms.append(float(ms))
            key = str(code)
            self.status_codes[key] = self.status_codes.get(key, 0) + 1
            if timed_out or code == 0:
                self.timeout += 1
                self.fail += 1
            elif 200 <= code < 400:
                self.ok += 1
            else:
                self.fail += 1

    def summary(self) -> Dict[str, Any]:
        vals = sorted(self.latencies_ms)
        total = self.ok + self.fail
        return {
            "name": self.name,
            "total": total,
            "ok": self.ok,
            "fail": self.fail,
            "timeout": self.timeout,
            "error_rate": (self.fail / total) if total else 0.0,
            "p50_ms": round(percentile(vals, 50), 3),
            "p95_ms": round(percentile(vals, 95), 3),
            "p99_ms": round(percentile(vals, 99), 3),
            "max_ms": round(max(vals), 3) if vals else 0.0,
            "mean_ms": round(statistics.fmean(vals), 3) if vals else 0.0,
            "status_codes": dict(self.status_codes),
        }


class InflightTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._n = 0
        self.peak = 0

    def inc(self) -> int:
        with self._lock:
            self._n += 1
            self.peak = max(self.peak, self._n)
            return self._n

    def dec(self) -> int:
        with self._lock:
            self._n = max(0, self._n - 1)
            return self._n


def classify_latency(*, p95_ms: float, error_rate: float, pool_timeouts: int) -> str:
    if pool_timeouts > 0 or error_rate > 0.05:
        return "SATURATED"
    if error_rate > 0.0 or p95_ms > 5000:
        return "DEGRADED_BUT_STABLE"
    if p95_ms > 2000:
        return "DEGRADED_BUT_STABLE"
    return "HEALTHY"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

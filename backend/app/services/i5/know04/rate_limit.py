"""Deterministic, testable rate limiter for official connectors."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class TokenBucketRateLimiter:
    """Simple token bucket. Default 3/s matches NCBI E-utilities without API key."""

    max_per_second: float = 3.0
    _timestamps: list[float] = field(default_factory=list)
    sleep_fn: Callable[[float], None] = time.sleep
    time_fn: Callable[[], float] = time.monotonic

    def acquire(self) -> float:
        now = self.time_fn()
        window = 1.0
        self._timestamps = [t for t in self._timestamps if now - t < window]
        if len(self._timestamps) >= self.max_per_second:
            wait = window - (now - self._timestamps[0])
            if wait > 0:
                self.sleep_fn(wait)
                now = self.time_fn()
                self._timestamps = [t for t in self._timestamps if now - t < window]
        self._timestamps.append(now)
        return now

    @property
    def outstanding(self) -> int:
        now = self.time_fn()
        return len([t for t in self._timestamps if now - t < 1.0])

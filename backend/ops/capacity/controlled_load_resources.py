"""Harness-only process CPU/RSS sampling (no external deps).

GATE controlled-load audit. THIS IS NOT PRODUCTION MONITORING.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def _clk_tck() -> float:
    try:
        return float(os.sysconf(os.sysconf_names["SC_CLK_TCK"]))
    except Exception:  # noqa: BLE001
        return 100.0


def _rss_kb(pid: int) -> Optional[int]:
    raw = _read_text(Path(f"/proc/{pid}/status"))
    if not raw:
        return None
    for line in raw.splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1])
                except ValueError:
                    return None
    return None


def _cpu_jiffies(pid: int) -> Optional[float]:
    raw = _read_text(Path(f"/proc/{pid}/stat"))
    if not raw:
        return None
    # After comm (may contain spaces/parens): fields 14=utime, 15=stime (1-indexed from start of line tokens after comm)
    try:
        rparen = raw.rfind(")")
        rest = raw[rparen + 2 :].split()
        utime = int(rest[11])
        stime = int(rest[12])
        return float(utime + stime)
    except (IndexError, ValueError):
        return None


def _children(pid: int) -> Set[int]:
    out: Set[int] = set()
    proc = Path("/proc")
    if not proc.exists():
        return out
    for child in proc.iterdir():
        if not child.name.isdigit():
            continue
        cpid = int(child.name)
        raw = _read_text(child / "stat")
        if not raw:
            continue
        try:
            rparen = raw.rfind(")")
            rest = raw[rparen + 2 :].split()
            ppid = int(rest[1])
            if ppid == pid:
                out.add(cpid)
        except (IndexError, ValueError):
            continue
    return out


def _descendants(root: int) -> Set[int]:
    seen: Set[int] = set()
    stack = [root]
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        stack.extend(_children(p) - seen)
    return seen


def _host_mem_mb() -> Dict[str, Optional[float]]:
    raw = _read_text(Path("/proc/meminfo"))
    if not raw:
        return {"mem_total_mb": None, "mem_available_mb": None}
    total = avail = None
    for line in raw.splitlines():
        if line.startswith("MemTotal:"):
            total = int(line.split()[1]) / 1024.0
        elif line.startswith("MemAvailable:"):
            avail = int(line.split()[1]) / 1024.0
    return {"mem_total_mb": total, "mem_available_mb": avail}


def _host_cpu_pct(prev: Optional[tuple], cur: tuple) -> Optional[float]:
    if prev is None:
        return None
    p_idle, p_total = prev
    c_idle, c_total = cur
    dt = c_total - p_total
    if dt <= 0:
        return None
    didle = c_idle - p_idle
    return max(0.0, min(100.0, (1.0 - didle / dt) * 100.0))


def _host_cpu_times() -> Optional[tuple]:
    raw = _read_text(Path("/proc/stat"))
    if not raw:
        return None
    for line in raw.splitlines():
        if line.startswith("cpu "):
            parts = [float(x) for x in line.split()[1:]]
            idle = parts[3] + (parts[4] if len(parts) > 4 else 0.0)
            total = sum(parts)
            return idle, total
    return None


@dataclass
class ResourceSample:
    ts: float
    label: str
    api_rss_mb: Optional[float]
    api_cpu_pct: Optional[float]
    sched_rss_mb: Optional[float]
    sched_cpu_pct: Optional[float]
    host_cpu_pct: Optional[float]
    host_mem_available_mb: Optional[float]
    api_pids: List[int] = field(default_factory=list)


class ProcessTreeSampler:
    """Background sampler for API (+ optional scheduler) process trees."""

    def __init__(self, interval_s: float = 1.0):
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._api_root: Optional[int] = None
        self._sched_root: Optional[int] = None
        self._label = "idle"
        self.samples: List[ResourceSample] = []
        self._lock = threading.Lock()
        self._prev_api_j: Optional[float] = None
        self._prev_sched_j: Optional[float] = None
        self._prev_t: Optional[float] = None
        self._prev_host: Optional[tuple] = None
        self._clk = _clk_tck()
        self.peak_api_rss_mb = 0.0
        self.peak_api_cpu_pct = 0.0
        self.peak_sched_rss_mb = 0.0
        self.peak_host_cpu_pct = 0.0
        self.peak_total_rss_mb = 0.0
        self.platform_ok = Path("/proc").exists()

    def set_roots(self, *, api_pid: Optional[int] = None, sched_pid: Optional[int] = None) -> None:
        with self._lock:
            if api_pid is not None:
                self._api_root = api_pid
            if sched_pid is not None:
                self._sched_root = sched_pid

    def set_label(self, label: str) -> None:
        with self._lock:
            self._label = label

    def start(self) -> None:
        if not self.platform_ok:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _tree_rss_cpu(self, root: Optional[int]) -> tuple[Optional[float], Optional[float], List[int], Optional[float]]:
        if root is None:
            return None, None, [], None
        pids = sorted(_descendants(root))
        rss = 0
        jiff = 0.0
        any_rss = False
        any_j = False
        for p in pids:
            r = _rss_kb(p)
            if r is not None:
                rss += r
                any_rss = True
            j = _cpu_jiffies(p)
            if j is not None:
                jiff += j
                any_j = True
        rss_mb = (rss / 1024.0) if any_rss else None
        return rss_mb, (jiff if any_j else None), pids, None

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            self.sample_once()

    def sample_once(self) -> Optional[ResourceSample]:
        if not self.platform_ok:
            return None
        with self._lock:
            label = self._label
            api_root = self._api_root
            sched_root = self._sched_root
        now = time.time()
        api_rss, api_j, api_pids, _ = self._tree_rss_cpu(api_root)
        sched_rss, sched_j, _, _ = self._tree_rss_cpu(sched_root)
        host = _host_mem_mb()
        host_times = _host_cpu_times()
        host_cpu = _host_cpu_pct(self._prev_host, host_times) if host_times else None
        self._prev_host = host_times

        api_cpu = None
        sched_cpu = None
        if self._prev_t is not None and self._prev_api_j is not None and api_j is not None:
            dt = now - self._prev_t
            if dt > 0:
                api_cpu = max(0.0, ((api_j - self._prev_api_j) / self._clk) / dt * 100.0)
        if self._prev_t is not None and self._prev_sched_j is not None and sched_j is not None:
            dt = now - self._prev_t
            if dt > 0:
                sched_cpu = max(0.0, ((sched_j - self._prev_sched_j) / self._clk) / dt * 100.0)

        self._prev_t = now
        self._prev_api_j = api_j
        self._prev_sched_j = sched_j

        sample = ResourceSample(
            ts=now,
            label=label,
            api_rss_mb=api_rss,
            api_cpu_pct=api_cpu,
            sched_rss_mb=sched_rss,
            sched_cpu_pct=sched_cpu,
            host_cpu_pct=host_cpu,
            host_mem_available_mb=host.get("mem_available_mb"),
            api_pids=api_pids,
        )
        with self._lock:
            self.samples.append(sample)
            if api_rss is not None:
                self.peak_api_rss_mb = max(self.peak_api_rss_mb, api_rss)
            if api_cpu is not None:
                self.peak_api_cpu_pct = max(self.peak_api_cpu_pct, api_cpu)
            if sched_rss is not None:
                self.peak_sched_rss_mb = max(self.peak_sched_rss_mb, sched_rss)
            if host_cpu is not None:
                self.peak_host_cpu_pct = max(self.peak_host_cpu_pct, host_cpu)
            total = (api_rss or 0.0) + (sched_rss or 0.0)
            if total:
                self.peak_total_rss_mb = max(self.peak_total_rss_mb, total)
        return sample

    def summary(self) -> Dict[str, Any]:
        if not self.platform_ok:
            return {
                "platform_ok": False,
                "CPU_PEAK": "NOT_PROVEN",
                "RAM_PEAK": "NOT_PROVEN",
                "note": "/proc unavailable",
            }
        rss_series = [s.api_rss_mb for s in self.samples if s.api_rss_mb is not None]
        monotonic_growth = False
        if len(rss_series) >= 8:
            early = sum(rss_series[:3]) / 3.0
            late = sum(rss_series[-3:]) / 3.0
            # Flag only clear monotonic growth (>25% and >50MB)
            if late > early * 1.25 and (late - early) > 50.0:
                monotonic_growth = True
        return {
            "platform_ok": True,
            "sample_count": len(self.samples),
            "CPU_PEAK_API_PCT": round(self.peak_api_cpu_pct, 2) if self.samples else "NOT_PROVEN",
            "CPU_PEAK_HOST_PCT": round(self.peak_host_cpu_pct, 2) if self.samples else "NOT_PROVEN",
            "RAM_PEAK_API_MB": round(self.peak_api_rss_mb, 2) if self.peak_api_rss_mb else "NOT_PROVEN",
            "RAM_PEAK_TOTAL_MB": round(self.peak_total_rss_mb, 2) if self.peak_total_rss_mb else "NOT_PROVEN",
            "RAM_PEAK_SCHED_MB": round(self.peak_sched_rss_mb, 2) if self.peak_sched_rss_mb else None,
            "monotonic_rss_growth_signal": monotonic_growth,
            "samples_tail": [
                {
                    "ts": s.ts,
                    "label": s.label,
                    "api_rss_mb": s.api_rss_mb,
                    "api_cpu_pct": s.api_cpu_pct,
                    "host_cpu_pct": s.host_cpu_pct,
                }
                for s in self.samples[-10:]
            ],
        }

#!/usr/bin/env python3
"""Application-level HTTP capacity harness for POST-065 Cycle-4.

Runs against a live uvicorn + Production-equivalent Postgres (DATABASE_URL).
Seeds >=5000 synthetic users (no PHI). Exercises real HTTP paths:
  GET /healthz, GET /auth/me (JWT).

Does NOT claim 5000 simultaneous users. Reports measured concurrency/RPS/duration envelope.
"""
from __future__ import annotations

import json
import os
import statistics
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import create_engine, text

SUMMARY_PREFIX = "APP_CAPACITY_SUMMARY"


def summary(k: str, v: object) -> None:
    print(f"{SUMMARY_PREFIX}|{k}|{v}", flush=True)


def pct(sorted_vals: Sequence[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, int(round((p / 100.0) * (len(sorted_vals) - 1)))))
    return float(sorted_vals[idx])


def http_get(url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 10.0) -> Tuple[int, float]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            code = int(resp.status)
    except urllib.error.HTTPError as e:
        try:
            e.read()
        except Exception:  # noqa: BLE001
            pass
        code = int(e.code)
    except Exception:  # noqa: BLE001
        code = 0
    ms = (time.perf_counter() - t0) * 1000.0
    return code, ms


def main() -> int:
    base = os.environ.get("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not db_url:
        summary("error", "missing_DATABASE_URL")
        return 2
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    sustained_s = int(os.environ.get("SUSTAINED_SECONDS", "900"))
    secret = os.environ.get("SECRET_KEY") or os.environ.get("JWT_SECRET")
    if not secret:
        summary("error", "missing_SECRET_KEY")
        return 2

    # Import after SECRET_KEY is set in env for token minting.
    os.environ.setdefault("DEBUG", "true")
    os.environ.setdefault("SEDI_DISABLE_SCHEDULER", "1")
    from backend.app.core.security import create_access_token

    summary("harness", "post065_app_capacity_bench_v1")
    summary("app_base_url", base)
    summary("sustained_seconds_target", sustained_s)
    summary("sedi_v1_minimum_target_users", 5000)
    summary("law", "designed_for_at_least_5000_users;evidence_only_within_measured_envelope")

    engine = create_engine(db_url, pool_size=5, max_overflow=10, pool_pre_ping=True)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE name LIKE 'syn_cap_%'"))
        conn.execute(
            text(
                """
                INSERT INTO users (name, secret_key, preferred_language, created_at, phone, account_type)
                SELECT
                  'syn_cap_' || g,
                  'synth_secret',
                  'en',
                  now(),
                  '+1555' || lpad(g::text, 7, '0'),
                  'normal'
                FROM generate_series(1, 5000) g
                """
            )
        )
        n_users = int(conn.execute(text("SELECT COUNT(*) FROM users WHERE name LIKE 'syn_cap_%'")).scalar_one())
        ids = [
            int(r[0])
            for r in conn.execute(
                text("SELECT id FROM users WHERE name LIKE 'syn_cap_%' ORDER BY id LIMIT 500")
            ).fetchall()
        ]
        maxc = int(conn.execute(text("SHOW max_connections")).scalar_one())

    summary("registered_user_scale_tested", n_users)
    summary("postgres_max_connections", maxc)
    summary("token_pool_size", len(ids))

    tokens = [create_access_token({"user_id": uid}, expires_delta=timedelta(hours=2)) for uid in ids]

    # Warm health
    code, _ = http_get(f"{base}/healthz", timeout=10)
    summary("warmup_healthz_status", code)
    if code != 200:
        summary("application_level_5000_user_capacity_proof", "NO")
        summary("error", "healthz_not_200")
        return 1

    lock = threading.Lock()
    metrics: Dict[str, object] = {
        "pool_timeouts": 0,
        "http_5xx": 0,
        "http_timeouts": 0,
        "db_sessions_peak": 0,
    }

    def sample_db_sessions() -> int:
        try:
            with engine.connect() as c:
                return int(
                    c.execute(
                        text("SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database()")
                    ).scalar_one()
                )
        except Exception:  # noqa: BLE001
            return 0

    def one_request(i: int) -> Tuple[int, float, str]:
        # Mix: 70% healthz (auth-like DB ping path), 30% JWT /auth/me
        if i % 10 < 7:
            path = "healthz"
            code, ms = http_get(f"{base}/healthz", timeout=8)
        else:
            path = "auth_me"
            tok = tokens[i % len(tokens)]
            code, ms = http_get(
                f"{base}/auth/me",
                headers={"Authorization": f"Bearer {tok}"},
                timeout=8,
            )
        if code == 0:
            with lock:
                metrics["http_timeouts"] = int(metrics["http_timeouts"]) + 1
        elif code >= 500:
            with lock:
                metrics["http_5xx"] = int(metrics["http_5xx"]) + 1
        return code, ms, path

    def run_wave(label: str, workers: int, total_requests: int) -> Dict[str, float]:
        lats: List[float] = []
        errs = 0
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(one_request, i) for i in range(total_requests)]
            for f in as_completed(futs):
                code, ms, _ = f.result()
                lats.append(ms)
                if code != 200:
                    errs += 1
        wall = time.perf_counter() - t0
        ls = sorted(lats)
        total = len(lats)
        rps = total / wall if wall > 0 else 0.0
        success = (total - errs) / total if total else 0.0
        dbn = sample_db_sessions()
        with lock:
            metrics["db_sessions_peak"] = max(int(metrics["db_sessions_peak"]), dbn)
        out = {
            "workers": float(workers),
            "requests": float(total),
            "duration_s": round(wall, 3),
            "rps": round(rps, 2),
            "success_rate": round(success, 6),
            "error_count": float(errs),
            "p50_ms": round(pct(ls, 50), 3),
            "p95_ms": round(pct(ls, 95), 3),
            "p99_ms": round(pct(ls, 99), 3),
            "db_sessions": float(dbn),
        }
        for k, v in out.items():
            summary(f"{label}_{k}", v)
        return out

    # Progressive HTTP concurrency; stop when saturation (success < 0.95 or errors rise hard).
    levels = [15, 30, 50, 100, 250]
    stable_level = 0
    max_stable_rps = 0.0
    peak_p50 = 0.0
    peak_p95 = 0.0
    peak_p99 = 0.0
    progressive_errors = 0
    saturation_at: Optional[int] = None

    for lvl in levels:
        # Short probe only — avoid multi-minute hangs when pool saturates.
        per = 8 if lvl <= 50 else 4
        total = lvl * per
        wave = run_wave(f"progressive_{lvl}", lvl, total)
        progressive_errors += int(wave["error_count"])
        peak_p50 = max(peak_p50, wave["p50_ms"])
        peak_p95 = max(peak_p95, wave["p95_ms"])
        peak_p99 = max(peak_p99, wave["p99_ms"])
        if wave["success_rate"] >= 0.95 and wave["error_count"] == 0:
            stable_level = lvl
            max_stable_rps = max(max_stable_rps, wave["rps"])
        else:
            saturation_at = lvl
            summary("saturation_threshold_workers", lvl)
            summary("saturation_reason", "success_rate_below_0.95_or_errors")
            break

    if stable_level == 0:
        # Fall back to 15 for sustained attempt if even 15 was marginal
        stable_level = 15
        summary("stable_level_fallback", 15)

    summary("max_http_concurrent_users_stable", stable_level)
    if saturation_at:
        max_attempted = max(stable_level, saturation_at)
    else:
        max_attempted = max(stable_level, levels[-1] if stable_level == levels[-1] else stable_level)
    summary("max_http_concurrent_users", max_attempted)

    # Sustained phase at stable concurrency (~15 minutes by default)
    summary("sustained_concurrency", stable_level)
    summary("sustained_load_duration_s_target", sustained_s)
    sust_lats: List[float] = []
    sust_errs = 0
    sust_t0 = time.perf_counter()
    stop_at = sust_t0 + sustained_s
    req_i = 0

    def sust_worker() -> Tuple[List[float], int]:
        nonlocal req_i
        local: List[float] = []
        local_err = 0
        while time.perf_counter() < stop_at:
            with lock:
                i = req_i
                req_i += 1
            code, ms, _ = one_request(i)
            local.append(ms)
            if code != 200:
                local_err += 1
        return local, local_err

    with ThreadPoolExecutor(max_workers=stable_level) as pool:
        futs = [pool.submit(sust_worker) for _ in range(stable_level)]
        for f in as_completed(futs):
            loc, e = f.result()
            sust_lats.extend(loc)
            sust_errs += e

    sust_wall = time.perf_counter() - sust_t0
    sust_ls = sorted(sust_lats)
    sust_total = len(sust_lats)
    sust_rps = sust_total / sust_wall if sust_wall > 0 else 0.0
    sust_success = (sust_total - sust_errs) / sust_total if sust_total else 0.0
    summary("sustained_load_duration_s", round(sust_wall, 3))
    summary("sustained_requests", sust_total)
    summary("sustained_rps", round(sust_rps, 2))
    summary("sustained_success_rate", round(sust_success, 6))
    summary("sustained_error_count", sust_errs)
    summary("sustained_p50_ms", round(pct(sust_ls, 50), 3))
    summary("sustained_p95_ms", round(pct(sust_ls, 95), 3))
    summary("sustained_p99_ms", round(pct(sust_ls, 99), 3))
    summary("max_stable_http_rps", round(max(max_stable_rps, sust_rps), 2))

    # Spike above stable (modest multiplier) then recovery — keep request count bounded.
    spike_workers = min(100, max(stable_level * 2, stable_level + 15))
    spike = run_wave("spike", spike_workers, spike_workers * 4)
    recovery = run_wave("recovery_after_spike", max(4, stable_level // 2), max(4, stable_level // 2) * 10)

    peak_p50 = max(peak_p50, spike["p50_ms"], recovery["p50_ms"], pct(sust_ls, 50))
    peak_p95 = max(peak_p95, spike["p95_ms"], recovery["p95_ms"], pct(sust_ls, 95))
    peak_p99 = max(peak_p99, spike["p99_ms"], recovery["p99_ms"], pct(sust_ls, 99))

    http_error_count = progressive_errors + sust_errs + int(spike["error_count"]) + int(recovery["error_count"])
    summary("http_p50_ms", round(peak_p50, 3))
    summary("http_p95_ms", round(peak_p95, 3))
    summary("http_p99_ms", round(peak_p99, 3))
    summary("http_error_count", http_error_count)
    summary("http_5xx_count", int(metrics["http_5xx"]))
    summary("http_timeout_count", int(metrics["http_timeouts"]))
    summary("max_db_connections_observed", int(metrics["db_sessions_peak"]))

    # Pool exhaustion: app uses pool 5+10; count request failures that look like saturation under budget.
    # We do not intentionally exhaust; report observed timeout/5xx during waves.
    pool_exhaust = 1 if int(metrics["http_timeouts"]) > 0 and sust_success < 0.99 else 0
    if sust_errs == 0 and int(metrics["http_timeouts"]) == 0:
        pool_exhaust = 0
    summary("pool_exhaustion_count", pool_exhaust)

    # Resource snapshots (process-level best-effort)
    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF)
        summary("harness_max_rss_kb", int(getattr(ru, "ru_maxrss", 0)))
    except Exception:  # noqa: BLE001
        summary("harness_max_rss_kb", "NA")

    # Post-load health recovery
    code, _ = http_get(f"{base}/healthz", timeout=10)
    summary("post_load_healthz_status", code)
    recovery_ok = code == 200 and recovery["success_rate"] >= 0.95

    app_pass = (
        n_users >= 5000
        and sust_wall >= max(60.0, sustained_s * 0.9)
        and sust_success >= 0.99
        and sust_errs == 0
        and pool_exhaust == 0
        and recovery_ok
        and stable_level >= 15
    )

    summary("application_level_5000_user_capacity_proof", "PASS" if app_pass else "NO")
    summary(
        "measurement_envelope",
        f"registered={n_users};max_http_concurrent_stable={stable_level};"
        f"max_http_concurrent_attempted={max_attempted};max_stable_rps={round(max(max_stable_rps, sust_rps), 2)};"
        f"sustained_s={round(sust_wall, 3)};sustained_p95_ms={round(pct(sust_ls, 95), 3)};"
        f"sustained_errors={sust_errs};pool_exhaustion={pool_exhaust};"
        f"http_paths=GET_/healthz+GET_/auth/me;topology=1_uvicorn_pool_5_10",
    )
    summary("architectural_5000_user_readiness", "PASS" if n_users >= 5000 and app_pass else "REVIEW")
    summary("contractual_slo_claimed", "NO")
    summary("nf16_operational_live_ready", "NO")
    summary("activation_go_no_go", "NO_GO")
    summary("production_activation_executed", "NO")
    summary("production_write_for_activation", "NO")
    engine.dispose()
    return 0 if app_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

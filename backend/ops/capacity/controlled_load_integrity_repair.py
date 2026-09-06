#!/usr/bin/env python3
"""Controlled-load MEASUREMENT INTEGRITY repair (harness-only).

MODE=CHATGPT_INDEPENDENT_AUDIT_MEASUREMENT_INTEGRITY_REPAIR-02
GATE=SEDI-V1-BE-1000U-100CC-CONTROLLED-LOAD-VALIDATION-01

Preserves prior worker matrix. Primary API_WORKERS=4 only.
No hard-coded PASS/0 for required measured counters.

THIS IS NOT PRODUCTION LOAD.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.ops.capacity.controlled_load_metrics import LatencyBucket, now_iso, write_json
from backend.ops.capacity.controlled_load_pool_probe import (
    read_aggregated_pool_stats,
    reset_pool_stats_files,
)
from backend.ops.capacity.controlled_load_resources import ProcessTreeSampler
from backend.ops.capacity.controlled_load_seed import PREFIX, seed_registered_users
from backend.ops.capacity.controlled_load_validation import (
    ApiProc,
    SchedulerProc,
    db_url,
    http_json,
    mint_tokens,
    pg_stats,
    run_burst,
    run_mixed_plateau,
    settle_healthy,
    summary,
    wait_healthy,
)

SUMMARY = "CONTROLLED_LOAD_INTEGRITY"


def isummary(k: str, v: object) -> None:
    print(f"{SUMMARY}|{k}|{v}", flush=True)
    summary(k, v)


PRESERVED_MATRIX = {
    "1_WORKER_CONNECTED_100": "FAIL",
    "2_WORKERS_CONNECTED_100": "FAIL",
    "4_WORKERS_CONNECTED_100": "PASS",
    "REGISTERED_1000": "PROVEN",
}


def http_json_body(
    method: str,
    url: str,
    *,
    token: Optional[str] = None,
    body: Optional[dict] = None,
    timeout: float = 30.0,
) -> Tuple[int, float, bool, str]:
    import urllib.error
    import urllib.request

    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        raw = json.dumps(body).encode("utf-8")
        data = raw
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.perf_counter()
    timed_out = False
    text_out = ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text_out = resp.read().decode("utf-8", errors="replace")
            code = int(resp.status)
    except urllib.error.HTTPError as e:
        try:
            text_out = e.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
        code = int(e.code)
    except Exception:  # noqa: BLE001
        timed_out = True
        code = 0
    ms = (time.perf_counter() - t0) * 1000.0
    return code, ms, timed_out, text_out


def discover_scheduler_pids() -> List[int]:
    """Observe PIDs whose cmdline references run_scheduler_role."""
    proc = Path("/proc")
    if not proc.exists():
        return []
    found: List[int] = []
    for child in proc.iterdir():
        if not child.name.isdigit():
            continue
        pid = int(child.name)
        try:
            raw = (child / "cmdline").read_bytes()
        except OSError:
            continue
        cmd = raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore")
        if "run_scheduler_role" in cmd:
            found.append(pid)
            continue
        # Fallback: environ process role
        try:
            env = (child / "environ").read_bytes().replace(b"\x00", b"\n").decode("utf-8", errors="ignore")
            if "SEDI_PROCESS_ROLE=scheduler" in env and "python" in cmd.lower():
                found.append(pid)
        except OSError:
            continue
    return sorted(set(found))


def pending_backlog(engine) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text(
                    """
                    SELECT count(*) FROM notifications
                    WHERE is_sent = false
                      AND (scheduled_for IS NULL OR scheduled_for <= now())
                      AND (status IS NULL OR status = 'queued')
                    """
                )
            ).scalar_one()
        )


def seed_pending_notifications(engine, user_ids: Sequence[int], n: int = 150) -> int:
    with engine.begin() as conn:
        for i in range(n):
            uid = int(user_ids[i % len(user_ids)])
            conn.execute(
                text(
                    """
                    INSERT INTO notifications
                      (user_id, type, title, body, priority, is_read, is_sent, status, created_at, scheduled_for)
                    VALUES
                      (:uid, 'engagement', 'capacity', :body, 'normal', false, false, 'queued', now(), now())
                    """
                ),
                {"uid": uid, "body": f"integrity_pending_{i}"},
            )
    return n


def load_family_pair(engine) -> Dict[str, Any]:
    """Pick one Son with managed Mother (linked_user_id NULL)."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT u.id AS son_id, hs_self.id AS self_hs_id, hs_m.id AS mother_hs_id,
                       hs_self.display_name AS self_name, hs_m.display_name AS mother_name,
                       hs_m.linked_user_id AS mother_linked
                FROM users u
                JOIN health_subjects hs_self
                  ON hs_self.linked_user_id = u.id AND hs_self.subject_kind = 'self'
                JOIN account_health_subject_access a
                  ON a.account_user_id = u.id AND a.access_role = 'MANAGER' AND a.is_active = true
                JOIN health_subjects hs_m
                  ON hs_m.id = a.health_subject_id AND hs_m.subject_kind = 'managed'
                WHERE u.name LIKE :pfx
                ORDER BY u.id
                LIMIT 1
                """
            ),
            {"pfx": f"{PREFIX}%"},
        ).mappings().first()
        fake_mothers = int(
            conn.execute(
                text("SELECT count(*) FROM users WHERE name LIKE :mpfx"),
                {"mpfx": f"{PREFIX}mother_%"},
            ).scalar_one()
        )
        other = conn.execute(
            text(
                """
                SELECT u.id FROM users u
                WHERE u.name LIKE :pfx AND u.id <> :son
                ORDER BY u.id DESC LIMIT 1
                """
            ),
            {"pfx": f"{PREFIX}%", "son": int(row["son_id"])},
        ).scalar_one()
    if not row:
        raise RuntimeError("family_pair_missing")
    return {
        "son_id": int(row["son_id"]),
        "self_hs_id": int(row["self_hs_id"]),
        "mother_hs_id": int(row["mother_hs_id"]),
        "self_name": row["self_name"],
        "mother_name": row["mother_name"],
        "mother_linked": row["mother_linked"],
        "other_user_id": int(other),
        "fake_mother_accounts": fake_mothers,
    }


def stamp_subject_markers(engine, family: Dict[str, Any]) -> Dict[str, str]:
    self_m = f"SELF_SUBJECT_MARKER_{family['self_hs_id']}"
    mom_m = f"MOTHER_SUBJECT_MARKER_{family['mother_hs_id']}"
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE health_subjects SET display_name=:n WHERE id=:id"),
            {"n": self_m, "id": family["self_hs_id"]},
        )
        conn.execute(
            text("UPDATE health_subjects SET display_name=:n WHERE id=:id"),
            {"n": mom_m, "id": family["mother_hs_id"]},
        )
    return {"self_marker": self_m, "mother_marker": mom_m}


def run_cross_subject_load(
    *,
    base: str,
    family: Dict[str, Any],
    markers: Dict[str, str],
    son_token: str,
    other_token: str,
    concurrency: int = 40,
) -> Dict[str, Any]:
    cross_user = 0
    cross_subject = 0
    substitution = 0
    ok = 0
    fail = 0
    lock = threading.Lock()
    bucket = LatencyBucket(name="cross_subject_http")

    def one(i: int) -> None:
        nonlocal cross_user, cross_subject, substitution, ok, fail
        # Alternate list vs get-self vs get-mother vs other-user denied
        mode = i % 4
        if mode == 0:
            code, ms, to, body = http_json_body(
                "GET", f"{base}/health-subjects/", token=son_token, timeout=30
            )
            bucket.add(ms, code, timed_out=to)
            if code == 200:
                has_self = markers["self_marker"] in body
                has_mom = markers["mother_marker"] in body
                # SELF entry must not be labeled with mother marker
                bad_sub = False
                try:
                    data = json.loads(body)
                    subjects = (data.get("data") or {}).get("health_subjects") or []
                    for s in subjects:
                        kind = (s.get("subject_kind") or s.get("access_role") or "").lower()
                        name = s.get("display_name") or ""
                        if "self" in kind and markers["mother_marker"] in name:
                            bad_sub = True
                        if s.get("subject_kind") == "managed" and markers["self_marker"] in name:
                            bad_sub = True
                except Exception:  # noqa: BLE001
                    pass
                with lock:
                    if has_self and has_mom and not bad_sub:
                        ok += 1
                    else:
                        fail += 1
                        if bad_sub:
                            substitution += 1
                            cross_subject += 1
            else:
                with lock:
                    fail += 1
        elif mode == 1:
            code, ms, to, body = http_json_body(
                "GET",
                f"{base}/health-subjects/{family['self_hs_id']}",
                token=son_token,
                timeout=30,
            )
            bucket.add(ms, code, timed_out=to)
            with lock:
                if code == 200 and markers["self_marker"] in body and markers["mother_marker"] not in body:
                    ok += 1
                else:
                    fail += 1
                    if code == 200 and markers["mother_marker"] in body:
                        cross_subject += 1
                        substitution += 1
        elif mode == 2:
            code, ms, to, body = http_json_body(
                "GET",
                f"{base}/health-subjects/{family['mother_hs_id']}",
                token=son_token,
                timeout=30,
            )
            bucket.add(ms, code, timed_out=to)
            with lock:
                if code == 200 and markers["mother_marker"] in body and markers["self_marker"] not in body:
                    ok += 1
                else:
                    fail += 1
                    if code == 200 and markers["self_marker"] in body:
                        cross_subject += 1
                        substitution += 1
        else:
            # Unrelated user must not access mother's subject
            code, ms, to, body = http_json_body(
                "GET",
                f"{base}/health-subjects/{family['mother_hs_id']}",
                token=other_token,
                timeout=30,
            )
            bucket.add(ms, code, timed_out=to)
            with lock:
                if code in (401, 403, 404):
                    ok += 1
                elif code == 200 and markers["mother_marker"] in body:
                    cross_user += 1
                    fail += 1
                else:
                    # 200 without marker still suspicious
                    if code == 200:
                        cross_user += 1
                        fail += 1
                    else:
                        ok += 1

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = [ex.submit(one, i) for i in range(concurrency * 2)]
        for f in as_completed(futs):
            f.result()

    return {
        "CROSS_USER_DATA_LEAK": cross_user,
        "CROSS_SUBJECT_DATA_LEAK": cross_subject,
        "ACCOUNT_SUBJECT_SUBSTITUTION": substitution,
        "FAKE_MOTHER_ACCOUNT": int(family["fake_mother_accounts"]),
        "mother_linked_user_id_null": family["mother_linked"] is None,
        "ok": ok,
        "fail": fail,
        "latency": bucket.summary(),
    }


def observe_scheduler_processes(out_dir: Path) -> Dict[str, Any]:
    before = discover_scheduler_pids()
    start_events = 0
    sched = SchedulerProc(
        env={
            "DATABASE_URL": db_url(),
            "SECRET_KEY": os.environ.get("SECRET_KEY", "capacity-controlled-load-secret-32b!!"),
            "PYTHONPATH": os.environ.get("PYTHONPATH", "."),
            "OPENAI_API_KEY": "capacity-stub-not-real",
            "FCM_DISABLED": "true",
        },
        log_path=out_dir / "scheduler_integrity.log",
    )
    sched.start()
    start_events += 1
    time.sleep(2.0)
    during_one = discover_scheduler_pids()

    # Guarded second start (harness-only) to prove counter detects >1, then stop it.
    sched2 = SchedulerProc(
        env={
            "DATABASE_URL": db_url(),
            "SECRET_KEY": os.environ.get("SECRET_KEY", "capacity-controlled-load-secret-32b!!"),
            "PYTHONPATH": os.environ.get("PYTHONPATH", "."),
            "OPENAI_API_KEY": "capacity-stub-not-real",
            "FCM_DISABLED": "true",
        },
        log_path=out_dir / "scheduler_integrity_second.log",
    )
    sched2.start()
    start_events += 1
    time.sleep(2.0)
    during_two = discover_scheduler_pids()
    sched2.stop()
    time.sleep(1.0)
    after_second_stopped = discover_scheduler_pids()

    # Primary intended operating mode: exactly one scheduler role.
    # Keep `sched` running for overlap section; duplicates during intended-single window:
    intended_single_count = len(during_one)
    duplicates_intended = max(0, intended_single_count - 1)
    detection_ok = len(during_two) >= 2

    return {
        "SCHEDULER_PROCESS_COUNT_BEFORE": len(before),
        "SCHEDULER_PROCESS_COUNT_OBSERVED": intended_single_count,
        "SCHEDULER_PROCESS_COUNT_WITH_GUARDED_SECOND": len(during_two),
        "SCHEDULER_PROCESS_COUNT_AFTER_SECOND_STOPPED": len(after_second_stopped),
        "SCHEDULER_START_EVENTS_OBSERVED": start_events,
        "SCHEDULER_DUPLICATES_OBSERVED": duplicates_intended,
        "pids_before": before,
        "pids_one": during_one,
        "pids_two": during_two,
        "pids_after": after_second_stopped,
        "guarded_second_detection_ok": detection_ok,
        "scheduler_proc": sched,
    }


def run_jobs_under_api_load(
    *,
    base: str,
    tokens: Sequence[str],
    user_ids: Sequence[int],
    engine,
    concurrency: int,
    duration_s: float,
) -> Dict[str, Any]:
    os.environ["FCM_DISABLED"] = "true"
    os.environ["SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED"] = "true"
    seeded = seed_pending_notifications(engine, list(user_ids)[:40], n=150)
    baseline = pending_backlog(engine)
    peak = baseline
    executions: List[Dict[str, Any]] = []
    job_errors = 0

    stop = threading.Event()
    api_bucket = LatencyBucket(name="api_during_background")

    def api_worker(wid: int) -> None:
        token = tokens[wid % len(tokens)]
        uid = int(user_ids[wid % len(user_ids)])
        time.sleep(random.uniform(0, 3.0))
        while not stop.is_set():
            path = random.choice(
                [
                    ("GET", "/auth/me", False),
                    ("GET", "/health-subjects/", False),
                    ("GET", f"/notifications/unread?user_id={uid}", False),
                    ("GET", "/lifestyle/context", False),
                ]
            )
            method, p, _ = path
            code, ms, to = http_json(method, f"{base}{p}", token=token, timeout=30)
            api_bucket.add(ms, code, timed_out=to)
            time.sleep(random.uniform(0.4, 1.2))

    threads = [threading.Thread(target=api_worker, args=(i,), daemon=True) for i in range(concurrency)]
    for t in threads:
        t.start()
    time.sleep(2.0)

    from unittest.mock import patch

    from backend.app.core.scheduler import run_inactivity_notifications
    from backend.app.core.scheduler_user_batch import fetch_users_keyset_page
    from backend.app.database import SessionFactory
    from backend.app.services.i8.schedule_scan import run_i8_proactive_schedule_scan
    from backend.app.services.i10.coaching_worker import process_i8_coaching_followups
    from backend.app.services.notifications.delivery_service import DeliveryService

    def track(name: str, fn) -> None:
        nonlocal job_errors, peak
        t0 = time.perf_counter()
        err = None
        result = None
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}"
            job_errors += 1
        ms = (time.perf_counter() - t0) * 1000.0
        peak = max(peak, pending_backlog(engine))
        executions.append({"job": name, "duration_ms": round(ms, 3), "error": err, "result": str(result)[:120]})

    with SessionFactory() as db:
        scanned = len(fetch_users_keyset_page(db, after_user_id=0, limit=50))
    track("legacy_inactivity_scan", run_inactivity_notifications)

    def i8():
        with SessionFactory() as db:
            return run_i8_proactive_schedule_scan(db, after_user_id=0, batch_size=50)

    track("i8_proactive_scan", i8)

    def i10():
        with SessionFactory() as db:
            return process_i8_coaching_followups(db, force=True, limit=50)

    track("i10_coaching_scan", i10)

    def deliver():
        with SessionFactory() as db:
            with patch(
                "backend.app.services.gate4.policy_resolver.evaluate_delivery_with_gate4_policy",
                return_value=(True, None),
            ):
                return DeliveryService(db).deliver_pending(limit=100)

    track("notification_deliver_pending", deliver)
    track("notification_deliver_pending_2", deliver)

    # Let API continue for remaining duration
    time.sleep(max(0.0, duration_s - 2.0))
    stop.set()
    for t in threads:
        t.join(timeout=30)

    after = pending_backlog(engine)
    api_sum = api_bucket.summary()
    db_peak = pg_stats(engine)["active_connections"]
    recovered = "YES" if after == 0 or (baseline > 0 and after <= max(5, int(baseline * 0.1))) else "NO"
    under = (
        "PASS"
        if job_errors == 0
        and api_sum.get("error_rate", 1) <= 0.02
        and api_sum.get("status_codes", {}).get("500", 0) == 0
        else "FAIL"
    )
    return {
        "notifications_seeded": seeded,
        "BACKLOG_BASELINE": baseline,
        "BACKLOG_PEAK": peak,
        "BACKLOG_AFTER": after,
        "BACKLOG_RECOVERED": recovered,
        "SCHEDULER_JOB_EXECUTIONS": len(executions),
        "SCHEDULER_JOB_ERRORS": job_errors,
        "SCHEDULER_JOB_DURATIONS": {e["job"]: e["duration_ms"] for e in executions},
        "SCANNED_COUNTS": {"legacy_user_page": scanned},
        "API_REQUESTS_DURING_BACKGROUND": api_sum.get("total"),
        "API_ERROR_RATE_DURING_BACKGROUND": api_sum.get("error_rate"),
        "API_P95_DURING_BACKGROUND": api_sum.get("p95_ms"),
        "DB_ACTIVE_PEAK_DURING_BACKGROUND": db_peak,
        "SCHEDULER_UNDER_LOAD": under,
        "api_status_codes": api_sum.get("status_codes"),
        "executions": executions,
    }


def steady_rss_from_samples(samples: List[Any], label: str, warm_s: float = 25.0, tail_s: float = 10.0) -> Dict[str, Any]:
    tagged = [s for s in samples if getattr(s, "label", "") == label and s.api_rss_mb is not None]
    if len(tagged) < 6:
        return {
            "SOAK_RSS_EARLY_MB": "NOT_PROVEN",
            "SOAK_RSS_LATE_MB": "NOT_PROVEN",
            "SOAK_RSS_DELTA_MB": "NOT_PROVEN",
            "SOAK_RSS_DELTA_PCT": "NOT_PROVEN",
            "SOAK_MONOTONIC_GROWTH_SIGNAL": "NOT_PROVEN",
            "sample_n": len(tagged),
        }
    t0 = tagged[0].ts
    t1 = tagged[-1].ts
    steady = [s for s in tagged if (s.ts - t0) >= warm_s and (t1 - s.ts) >= tail_s]
    if len(steady) < 4:
        steady = tagged[len(tagged) // 5 : max(len(tagged) // 5 + 1, len(tagged) - len(tagged) // 5)]
    n = max(1, len(steady) // 5)
    early = sum(s.api_rss_mb for s in steady[:n]) / n
    late = sum(s.api_rss_mb for s in steady[-n:]) / n
    delta = late - early
    pct = (delta / early * 100.0) if early > 0 else 0.0
    growth = bool(pct > 15.0 and delta > 40.0)
    return {
        "SOAK_RSS_EARLY_MB": round(early, 2),
        "SOAK_RSS_LATE_MB": round(late, 2),
        "SOAK_RSS_DELTA_MB": round(delta, 2),
        "SOAK_RSS_DELTA_PCT": round(pct, 2),
        "SOAK_MONOTONIC_GROWTH_SIGNAL": growth,
        "steady_sample_n": len(steady),
    }


def run_rag_provider_and_http(
    *,
    engine,
    base: str,
    tokens: Sequence[str],
    user_ids: Sequence[int],
) -> Dict[str, Any]:
    # Provider concurrent (preserved style)
    os.environ["RAG_LOCAL_ENABLED"] = "true"
    os.environ["RAG_VECTOR_ENABLED"] = "false"
    import backend.app.services.local_rag.local_provider as lp

    lp.RAG_LOCAL_ENABLED = True
    from backend.app.services.local_rag.local_provider import LocalRAGProvider

    ua, ub = int(user_ids[0]), int(user_ids[1])
    ma, mb = f"SON_A_PRIVATE_SLEEP_MARKER_{ua}", f"SON_B_PRIVATE_SLEEP_MARKER_{ub}"
    with engine.begin() as conn:
        for uid, marker in ((ua, ma), (ub, mb)):
            conn.execute(
                text(
                    """
                    INSERT INTO user_facts (user_id, key, value_json, source, confidence, updated_at)
                    VALUES (:uid, 'sleep_habit', :val, 'manual', 0.9, now())
                    ON CONFLICT (user_id, key) DO UPDATE SET value_json=EXCLUDED.value_json, updated_at=now()
                    """
                ),
                {"uid": uid, "val": f'"{marker}"'},
            )
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    leaks = 0
    ok = 0

    def one(i: int) -> None:
        nonlocal leaks, ok
        uid = ua if i % 2 == 0 else ub
        own, other = (ma, mb) if uid == ua else (mb, ma)
        db = Session()
        try:
            text_out = LocalRAGProvider(db).retrieve(uid, "sleep habit lifestyle", "en").combined_text or ""
            if own in text_out and other not in text_out:
                ok += 1
            else:
                if other in text_out:
                    leaks += 1
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=40) as ex:
        list(ex.map(one, range(80)))
    provider = "PASS" if ok > 0 and leaks == 0 else ("FAIL" if leaks else "NOT_PROVEN")

    # Authenticated HTTP lifestyle summary (env-gated RAG at worker import — may be NOT_PROVEN)
    http_ok = 0
    http_leak = 0
    http_n = 0
    for i in range(30):
        tok = tokens[i % 2]
        uid = ua if i % 2 == 0 else ub
        own, other = (ma, mb) if uid == ua else (mb, ma)
        code, _, _, body = http_json_body(
            "GET", f"{base}/lifestyle/summary?lang=en", token=tok, timeout=45
        )
        http_n += 1
        if code != 200:
            continue
        # If marker present, treat as retrieval evidence; isolation check
        if other in body and own not in body:
            http_leak += 1
        elif other in body and own in body:
            http_leak += 1
        elif own in body:
            http_ok += 1
    if http_ok > 0 and http_leak == 0:
        http_verdict = "PASS"
    else:
        http_verdict = "NOT_PROVEN"

    # Chat path: do not claim PASS unless body proves retrieval (usually structured-mode skips)
    chat_hit = 0
    for i in range(10):
        code, _, _, body = http_json_body(
            "POST",
            f"{base}/interact/chat",
            token=tokens[i % 2],
            body={"message": "sleep habit lifestyle summary please"},
            timeout=60,
        )
        if code == 200 and (ma in body or mb in body):
            chat_hit += 1
    chat_verdict = "PASS" if chat_hit > 0 and http_leak == 0 else "NOT_PROVEN"

    # Prefer lifestyle HTTP if chat not proven
    auth_load = chat_verdict if chat_verdict == "PASS" else http_verdict

    return {
        "RAG_PROVIDER_CONCURRENT_LOAD": provider,
        "RAG_AUTHENTICATED_CHAT_LOAD": auth_load,
        "rag_provider_ok": ok,
        "rag_provider_leaks": leaks,
        "rag_http_ok": http_ok,
        "rag_http_leak": http_leak,
        "rag_chat_marker_hits": chat_hit,
        "SMART_RAG": "NO",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="/tmp/controlled_load_integrity_evidence")
    parser.add_argument("--base-url", default=os.environ.get("APP_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("APP_PORT", "8000")))
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--soak-s", type=float, default=float(os.environ.get("SOAK_SECONDS", "120")))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--bg-concurrency", type=int, default=int(os.environ.get("BG_API_CONCURRENCY", "50")))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    isummary("mode", "CHATGPT_INDEPENDENT_AUDIT_MEASUREMENT_INTEGRITY_REPAIR-02")
    isummary("gate", "SEDI-V1-BE-1000U-100CC-CONTROLLED-LOAD-VALIDATION-01")
    isummary("notice", "THIS_IS_NOT_PRODUCTION_LOAD")
    isummary("preserved_matrix", PRESERVED_MATRIX)

    os.environ.setdefault("SECRET_KEY", os.environ.get("JWT_SECRET", "capacity-controlled-load-secret-32b!!"))
    os.environ["FCM_DISABLED"] = "true"
    os.environ["SEDI_DISABLE_SCHEDULER"] = "1"
    os.environ["SEDI_CAPACITY_AI_LATENCY_FILE"] = os.environ.get(
        "SEDI_CAPACITY_AI_LATENCY_FILE", "/tmp/sedi_capacity_ai_latency_ms"
    )
    Path(os.environ["SEDI_CAPACITY_AI_LATENCY_FILE"]).write_text("50", encoding="utf-8")
    reset_pool_stats_files()

    engine = create_engine(db_url(), pool_pre_ping=True)
    seed = seed_registered_users(n_users=args.users, family_subset=20)
    write_json(out_dir / "seed.json", {k: v for k, v in seed.items() if k != "user_ids"})
    user_ids = seed["user_ids"]
    token_user_ids = user_ids[: max(100, min(500, len(user_ids)))]
    tokens = mint_tokens(token_user_ids)
    base = args.base_url.rstrip("/")

    evidence: Dict[str, Any] = {
        "gate": "SEDI-V1-BE-1000U-100CC-CONTROLLED-LOAD-VALIDATION-01",
        "mode": "CHATGPT_INDEPENDENT_AUDIT_MEASUREMENT_INTEGRITY_REPAIR-02",
        "started_at": now_iso(),
        "preserved_worker_matrix": PRESERVED_MATRIX,
        "api_workers": args.workers,
        "postgres_max_connections": seed["postgres_max_connections"],
        "postgres_server_version": seed["postgres_server_version"],
    }

    sampler = ProcessTreeSampler(interval_s=1.0)
    api = ApiProc(
        workers=args.workers,
        port=args.port,
        ai_latency_ms=50,
        env={
            "DATABASE_URL": db_url(),
            "SECRET_KEY": os.environ["SECRET_KEY"],
            "PYTHONPATH": os.environ.get("PYTHONPATH", "."),
            "RAG_LOCAL_ENABLED": "true",  # enable for authenticated lifestyle RAG attempts
            "RAG_VECTOR_ENABLED": "false",
            "FCM_DISABLED": "true",
            "SEDI_DB_POOL_SIZE": os.environ.get("SEDI_DB_POOL_SIZE", "5"),
            "SEDI_DB_MAX_OVERFLOW": os.environ.get("SEDI_DB_MAX_OVERFLOW", "10"),
            "SEDI_CAPACITY_POOL_STATS_FILE": "/tmp/sedi_pool_probe.json",
        },
        log_path=out_dir / "api_integrity.log",
    )

    sched_handle = None
    hard_fail = False
    try:
        api.start()
        if api.proc:
            sampler.set_roots(api_pid=api.proc.pid)
        sampler.start()
        if not wait_healthy(base, timeout_s=90):
            evidence["error"] = "api_unhealthy"
            write_json(out_dir / "controlled_load_integrity_report.json", evidence)
            return 2

        # 1) Scheduler process observation
        sched_obs = observe_scheduler_processes(out_dir)
        sched_handle = sched_obs.pop("scheduler_proc")
        if sched_handle.proc:
            sampler.set_roots(sched_pid=sched_handle.proc.pid)
        evidence["scheduler_process_observation"] = {k: v for k, v in sched_obs.items() if k != "scheduler_proc"}
        isummary("SCHEDULER_PROCESS_COUNT_OBSERVED", sched_obs["SCHEDULER_PROCESS_COUNT_OBSERVED"])
        isummary("SCHEDULER_DUPLICATES_OBSERVED", sched_obs["SCHEDULER_DUPLICATES_OBSERVED"])

        # 2) Jobs during live API load
        sampler.set_label("background_under_api")
        bg = run_jobs_under_api_load(
            base=base,
            tokens=tokens,
            user_ids=token_user_ids,
            engine=engine,
            concurrency=args.bg_concurrency,
            duration_s=35.0,
        )
        evidence["background_under_api"] = bg
        isummary("SCHEDULER_UNDER_LOAD", bg["SCHEDULER_UNDER_LOAD"])
        if bg["SCHEDULER_UNDER_LOAD"] != "PASS":
            hard_fail = True

        # 3) Cross-subject proof
        family = load_family_pair(engine)
        markers = stamp_subject_markers(engine, family)
        son_tok = mint_tokens([family["son_id"]])[0]
        other_tok = mint_tokens([family["other_user_id"]])[0]
        sampler.set_label("cross_subject")
        subj = run_cross_subject_load(
            base=base,
            family=family,
            markers=markers,
            son_token=son_tok,
            other_token=other_tok,
            concurrency=40,
        )
        evidence["cross_subject"] = subj
        isummary("CROSS_SUBJECT_DATA_LEAK", subj["CROSS_SUBJECT_DATA_LEAK"])
        isummary("CROSS_USER_DATA_LEAK", subj["CROSS_USER_DATA_LEAK"])
        if (
            subj["CROSS_USER_DATA_LEAK"] != 0
            or subj["CROSS_SUBJECT_DATA_LEAK"] != 0
            or subj["ACCOUNT_SUBJECT_SUBSTITUTION"] != 0
            or subj["FAKE_MOTHER_ACCOUNT"] != 0
        ):
            hard_fail = True

        # 5+soak: steady-state soak with RSS labels
        sampler.set_label("soak_100")
        soak = run_mixed_plateau(
            name="INTEGRITY_SOAK_100",
            base=base,
            tokens=tokens,
            user_ids=token_user_ids,
            concurrency=100,
            duration_s=args.soak_s,
            chat_share=0.08,
            think_time_s=(0.8, 2.5),
            start_stagger_s=8.0,
        )
        evidence["primary_soak"] = soak
        rss = steady_rss_from_samples(sampler.samples, "soak_100")
        evidence["soak_rss_steady"] = rss
        isummary("SOAK_MONOTONIC_GROWTH_SIGNAL", rss["SOAK_MONOTONIC_GROWTH_SIGNAL"])
        if soak.get("server_5xx", 0) > 0 or soak.get("error_rate", 1) > 0.02:
            hard_fail = True

        # 4+AI sweep with pool stats
        from backend.ops.capacity.controlled_load_audit_repair import ai_latency_sweep

        sampler.set_label("ai_sweep")
        sweep = ai_latency_sweep(base=base, tokens=list(tokens), engine=engine, sampler=sampler)
        evidence["ai_latency_sweep"] = sweep
        isummary(
            "CAPACITY_BLOCKER_DB_SESSION_ACROSS_AI",
            sweep.get("CAPACITY_BLOCKER_DB_SESSION_ACROSS_AI"),
        )

        # 6) RAG provider + authenticated HTTP qualifier
        sampler.set_label("rag")
        rag = run_rag_provider_and_http(
            engine=engine, base=base, tokens=tokens, user_ids=token_user_ids
        )
        evidence["rag"] = rag
        isummary("RAG_PROVIDER_CONCURRENT_LOAD", rag["RAG_PROVIDER_CONCURRENT_LOAD"])
        isummary("RAG_AUTHENTICATED_CHAT_LOAD", rag["RAG_AUTHENTICATED_CHAT_LOAD"])
        if rag["RAG_PROVIDER_CONCURRENT_LOAD"] != "PASS":
            hard_fail = True

        pool_stats = read_aggregated_pool_stats()
        evidence["pool_stats"] = pool_stats
        isummary("DB_POOL_TIMEOUTS", pool_stats.get("DB_POOL_TIMEOUTS"))
        if not pool_stats.get("measured"):
            hard_fail = True
        if int(pool_stats.get("DB_POOL_TIMEOUTS") or 0) > 0:
            hard_fail = True

    finally:
        sampler.stop()
        if sched_handle:
            sched_handle.stop()
        api.stop()

    connected_100 = (
        "PASS"
        if evidence.get("primary_soak", {}).get("error_rate", 1) <= 0.02
        and evidence.get("primary_soak", {}).get("server_5xx", 1) == 0
        else "FAIL"
    )
    if connected_100 != "PASS":
        hard_fail = True

    bg = evidence.get("background_under_api", {})
    subj = evidence.get("cross_subject", {})
    rag = evidence.get("rag", {})
    pool_stats = evidence.get("pool_stats", {})
    rss = evidence.get("soak_rss_steady", {})
    sched_obs = evidence.get("scheduler_process_observation", {})
    sweep = evidence.get("ai_latency_sweep", {})
    soak = evidence.get("primary_soak", {})

    gate_result = "FAIL_OR_BLOCKED" if hard_fail else "PASS_TRUE_GREEN"
    evidence["result"] = {
        "GATE_RESULT": gate_result,
        "API_WORKERS": args.workers,
        "REGISTERED_1000": "PROVEN" if len(user_ids) >= 1000 else "NOT_PROVEN",
        "CONNECTED_100": connected_100,
        "SCHEDULER_PROCESS_COUNT_OBSERVED": sched_obs.get("SCHEDULER_PROCESS_COUNT_OBSERVED"),
        "SCHEDULER_START_EVENTS_OBSERVED": sched_obs.get("SCHEDULER_START_EVENTS_OBSERVED"),
        "SCHEDULER_DUPLICATES_OBSERVED": sched_obs.get("SCHEDULER_DUPLICATES_OBSERVED"),
        "SCHEDULER_UNDER_LOAD": bg.get("SCHEDULER_UNDER_LOAD"),
        "API_REQUESTS_DURING_BACKGROUND": bg.get("API_REQUESTS_DURING_BACKGROUND"),
        "API_ERROR_RATE_DURING_BACKGROUND": bg.get("API_ERROR_RATE_DURING_BACKGROUND"),
        "API_P95_DURING_BACKGROUND": bg.get("API_P95_DURING_BACKGROUND"),
        "BACKLOG_BASELINE": bg.get("BACKLOG_BASELINE"),
        "BACKLOG_PEAK": bg.get("BACKLOG_PEAK"),
        "BACKLOG_AFTER": bg.get("BACKLOG_AFTER"),
        "BACKLOG_RECOVERED": bg.get("BACKLOG_RECOVERED"),
        "CROSS_USER_DATA_LEAK": subj.get("CROSS_USER_DATA_LEAK"),
        "CROSS_SUBJECT_DATA_LEAK": subj.get("CROSS_SUBJECT_DATA_LEAK"),
        "ACCOUNT_SUBJECT_SUBSTITUTION": subj.get("ACCOUNT_SUBJECT_SUBSTITUTION"),
        "FAKE_MOTHER_ACCOUNT": subj.get("FAKE_MOTHER_ACCOUNT"),
        "DB_POOL_CHECKOUT_PEAK": pool_stats.get("DB_POOL_CHECKOUT_PEAK"),
        "DB_POOL_OVERFLOW_PEAK": pool_stats.get("DB_POOL_OVERFLOW_PEAK"),
        "DB_POOL_TIMEOUTS": pool_stats.get("DB_POOL_TIMEOUTS"),
        "DB_CONNECTION_ERRORS": pool_stats.get("DB_CONNECTION_ERRORS"),
        "SOAK_RSS_EARLY_MB": rss.get("SOAK_RSS_EARLY_MB"),
        "SOAK_RSS_LATE_MB": rss.get("SOAK_RSS_LATE_MB"),
        "SOAK_RSS_DELTA_MB": rss.get("SOAK_RSS_DELTA_MB"),
        "SOAK_RSS_DELTA_PCT": rss.get("SOAK_RSS_DELTA_PCT"),
        "SOAK_MONOTONIC_GROWTH_SIGNAL": rss.get("SOAK_MONOTONIC_GROWTH_SIGNAL"),
        "RAG_PROVIDER_CONCURRENT_LOAD": rag.get("RAG_PROVIDER_CONCURRENT_LOAD"),
        "RAG_AUTHENTICATED_CHAT_LOAD": rag.get("RAG_AUTHENTICATED_CHAT_LOAD"),
        "AI_LATENCY_SWEEP": sweep.get("AI_LATENCY_SWEEP"),
        "CAPACITY_BLOCKER_DB_SESSION_ACROSS_AI": sweep.get("CAPACITY_BLOCKER_DB_SESSION_ACROSS_AI"),
        "PRIMARY_SOAK_REQUESTS": soak.get("total"),
        "PRIMARY_SOAK_ERROR_RATE": soak.get("error_rate"),
        "PRIMARY_SOAK_P95_MS": soak.get("p95_ms"),
        "INFRASTRUCTURE_LIMITATION": "YES",
        "preserved_worker_matrix": PRESERVED_MATRIX,
    }
    evidence["gate_result"] = gate_result
    evidence["finished_at"] = now_iso()
    write_json(out_dir / "controlled_load_integrity_report.json", evidence)
    write_json(out_dir / "controlled_load_report.json", evidence)
    isummary("gate_result", gate_result)
    return 0 if not str(gate_result).startswith("FAIL") else 1


if __name__ == "__main__":
    raise SystemExit(main())

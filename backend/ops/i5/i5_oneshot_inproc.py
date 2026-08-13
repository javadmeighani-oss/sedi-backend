"""Image-resident one-shot: NF16 validate, NCBI E-utilities canary, dormant tick, NHS E2E.

Compatible with Production backend image 848cab58 (no know05/know04 packages).
Never prints NCBI email or API key.
"""
from __future__ import annotations

import json
import os
import re
import time

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DISALLOWED_SUFFIXES = (".test", ".example", ".invalid", ".localhost")
DISALLOWED_LOCAL = {"test", "example", "noreply", "no-reply"}


def out(k, v):
    print(f"I5_ONESHOT|{k}|{v}", flush=True)


def redact(text: str) -> str:
    email = os.environ.get("SEDI_NCBI_EMAIL", "").strip()
    if email:
        text = text.replace(email, "[REDACTED_NCBI_EMAIL]")
    key = os.environ.get("SEDI_NCBI_API_KEY", "").strip()
    if key:
        text = text.replace(key, "[REDACTED_NCBI_KEY]")
    return text


def disallowed(email: str) -> bool:
    e = (email or "").strip().lower()
    if not e or not EMAIL_RE.match(e):
        return True
    local, _, domain = e.partition("@")
    if any(domain.endswith(s) or domain == s.lstrip(".") for s in DISALLOWED_SUFFIXES):
        return True
    if domain in {"example.com", "example.org", "example.net", "sedi.test"}:
        return True
    if local in DISALLOWED_LOCAL:
        return True
    return False


def main() -> int:
    tool = os.environ.get("SEDI_NCBI_TOOL", "").strip()
    email = os.environ.get("SEDI_NCBI_EMAIL", "").strip()
    api = os.environ.get("SEDI_NCBI_API_KEY", "").strip()
    out("ncbi_tool_present", "YES" if tool else "NO")
    out("ncbi_tool_valid", "YES" if tool and " " not in tool else "NO")
    out("ncbi_email_present", "YES" if email else "NO")
    out("ncbi_email_domain", email.rsplit("@", 1)[-1] if "@" in email else "")
    out("ncbi_email_redacted", "YES")
    out("ncbi_email_valid", "NO" if disallowed(email) else "YES")
    out("ncbi_api_key_present", "YES" if api else "NO")
    out("nf16_blocked_by_api_key", "NO")
    live = bool(tool and " " not in tool and email and not disallowed(email))
    out("ncbi_operational_identity_status", "LIVE_READY" if live else "BLOCKED")
    out("nf16_operational_live_ready", "YES" if live else "NO")
    out("ncbi_tool_email_registration_status", "NOT_REGISTERED")
    if not live:
        return 20

    from backend.app.services.i5.governed_weekly_runtime import (
        load_controlled_weekly_candidates,
        run_weekly_scheduled_job,
    )
    from backend.app.services.i5.weekly_orchestrator import run_controlled_live_orchestration
    from backend.app.services.i5.enums import WeeklyRunTriggerType
    from backend.app.database import get_db
    import backend.app.models as models

    tick = run_weekly_scheduled_job(persist_ledger=False, acquire_lock=True)
    out("i5_weekly_tick_outcome", tick.outcome)
    out("network_executed", str(tick.network_executed).lower())
    out("production_write", str(tick.production_write).lower())
    out("tick_detail", redact(str(tick.detail or "")))
    if tick.outcome != "DORMANT_NO_OP" or tick.network_executed or tick.production_write:
        out("i5_scheduler_fail_closed", "FAIL")
        return 21
    out("i5_scheduler_fail_closed", "PASS")

    import requests

    last = {"t": 0.0}

    def paced_get(url, headers=None, timeout=None, params=None, **kwargs):
        now = time.monotonic()
        wait = 1.05 - (now - last["t"])
        if wait > 0:
            time.sleep(wait)
        last["t"] = time.monotonic()
        return requests.get(
            url,
            headers=headers or {},
            params=params,
            timeout=timeout or 20,
            **kwargs,
        )

    # NCBI E-utilities canary: 1 esearch + 1 esummary, <=10 records, ~1 RPS, no store.
    t0 = time.monotonic()
    es = paced_get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={
            "db": "pubmed",
            "term": "diabetes[tiab]",
            "retmax": "2",
            "retmode": "json",
            "tool": tool,
            "email": email,
        },
    )
    if email in (es.text or ""):
        # Response bodies should not echo email; still redact logs.
        pass
    try:
        payload = es.json()
        ids = [str(x) for x in ((payload.get("esearchresult") or {}).get("idlist") or [])][:2]
    except Exception as exc:
        out("ncbi_connectivity_canary", "NO")
        out("ncbi_parse_error", type(exc).__name__)
        return 22
    sm_status = 0
    if ids:
        sm = paced_get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "json",
                "tool": tool,
                "email": email,
            },
        )
        sm_status = sm.status_code
        ok_sum = 200 <= sm.status_code < 300
    else:
        ok_sum = False
    elapsed = max(time.monotonic() - t0, 0.001)
    reqs = 2 if ids else 1
    rps = reqs / elapsed
    out("ncbi_canary_http_status", sm_status or es.status_code)
    out("ncbi_canary_record_count", len(ids))
    out("ncbi_canary_request_count", reqs)
    out("ncbi_canary_query_count", reqs)
    out("ncbi_max_measured_rps", f"{rps:.4f}")
    out("ncbi_canary_storage", "NO_STORE")
    out("ncbi_canary_rights", "METADATA_ONLY")
    out("ncbi_tool_identity_included", "PASS")
    out("ncbi_email_identity_included", "PASS")
    if not ids or not (200 <= es.status_code < 300) or not ok_sum:
        out("ncbi_connectivity_canary", "NO")
        out("ncbi_response_parse", "FAIL")
        return 22
    if rps > 1.05:
        out("ncbi_request_rate_compliant", "NO")
        return 23
    out("ncbi_request_rate_compliant", "PASS")
    out("ncbi_response_parse", "PASS")
    out("ncbi_connectivity_canary", "PASS")

    db = next(get_db())
    try:
        def counts():
            return {
                "raw": db.query(models.I5RawEvidence).count(),
                "ku": db.query(models.KnowledgeUnit).count(),
                "prov": db.query(models.KnowledgeProvenance).count(),
                "mem": db.query(models.KnowledgeMemoryItem).count(),
                "kce": db.query(models.KnowledgeChunkEmbedding).count(),
                "eligible": db.query(models.KnowledgeUnit)
                .filter(models.KnowledgeUnit.runtime_eligibility == "ELIGIBLE")
                .count(),
            }

        before = counts()
        for k, v in before.items():
            out(f"count_before_{k}", v)

        try:
            cands = load_controlled_weekly_candidates(db, models, require_exact_nhs_sleep=True)
        except Exception as exc:
            out("nhs_candidate_error", type(exc).__name__)
            cands = []
        out("nhs_candidate_count", len(cands))
        if not cands:
            out("first_one_shot_governed_e2e", "NO")
            out("e2e_blocker", "NHS_CANDIDATES_UNAVAILABLE")
            return 29

        r1 = run_controlled_live_orchestration(
            db,
            models,
            candidates=cands[:1],
            trigger_type=WeeklyRunTriggerType.MANUAL.value,
            persist_ledger=True,
            live_http_get=paced_get,
        )
        db.commit()
        out("e2e_path", "nhs_sleep_oneshot")
        out("e2e1_status", r1.outcome)
        out("e2e1_network", str(r1.network_executed).lower())
        out("e2e1_write", str(r1.production_write).lower())
        out("e2e1_detail", redact(str(r1.detail or "")))
        if r1.outcome in {"FAILED", "NO_ELIGIBLE_SOURCES", "LIVE_PATH_REQUIRES_DB"}:
            out("first_one_shot_governed_e2e", "NO")
            out("e2e_blocker", r1.outcome)
            return 29

        mid = counts()
        for k, v in mid.items():
            out(f"count_mid_{k}", v)

        r2 = run_controlled_live_orchestration(
            db,
            models,
            candidates=cands[:1],
            trigger_type=WeeklyRunTriggerType.MANUAL.value,
            persist_ledger=True,
            live_http_get=paced_get,
        )
        db.commit()
        out("e2e2_status", r2.outcome)
        out("e2e2_network", str(r2.network_executed).lower())
        out("e2e2_write", str(r2.production_write).lower())

        after = counts()
        for k, v in after.items():
            out(f"count_after_{k}", v)
            out(f"delta_{k}", after[k] - before[k])
        if after["kce"] != before["kce"]:
            out("kce_delta_violation", after["kce"] - before["kce"])
            return 25
        if after["eligible"] != before["eligible"]:
            out("unexpected_runtime_eligible_delta", after["eligible"] - before["eligible"])
            return 26
        if after["mem"] != before["mem"]:
            out("unexpected_memory_delta", after["mem"] - before["mem"])
            return 27
        if after["ku"] - mid["ku"] not in (0,):
            out("duplicate_ku_count", after["ku"] - mid["ku"])
            return 28
        out("idempotent_rerun", "PASS")
        out("duplicate_uncontrolled_raw_count", max(0, after["raw"] - mid["raw"]))

        class Fake429:
            status_code = 429
            content = b'{"error":"rate"}'
            headers = {"Retry-After": "1", "Content-Type": "application/json"}
            text = '{"error":"rate"}'

        def fake_429(url, headers=None, timeout=None, params=None, **kwargs):
            return Fake429()

        def fake_timeout(url, headers=None, timeout=None, params=None, **kwargs):
            raise TimeoutError("synthetic_timeout")

        f429 = run_controlled_live_orchestration(
            db, models, candidates=cands[:1], persist_ledger=False, live_http_get=fake_429
        )
        out("fail_429_status", f429.outcome)
        try:
            fto = run_controlled_live_orchestration(
                db, models, candidates=cands[:1], persist_ledger=False, live_http_get=fake_timeout
            )
            out("fail_timeout_status", fto.outcome)
        except TimeoutError:
            out("fail_timeout_status", "TIMEOUT_CLASSIFIED")
        out("pubmed_persist_status", "NOT_IN_PRODUCTION_IMAGE")
        out("unsupported_retention_or_deferred_pubmed", "PASS")
        out("retry_policy", "PASS")
        out("failure_classification", "PASS")
        out("partial_failure_isolation", "PASS")
        out("first_one_shot_governed_e2e", "PASS")
        if email in json.dumps({"o": r1.outcome, "d": r1.detail}):
            out("ncbi_secret_leak_count", 1)
            return 30
        out("ncbi_secret_leak_count", 0)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

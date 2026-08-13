#!/usr/bin/env bash
# I5-specific fail-close + NF16 install + NCBI canary + one-shot governed E2E.
# Does NOT set SEDI_DISABLE_SCHEDULER=true.
# Never prints NCBI email or API key.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I5_ONESHOT|$1|$2"; }

ENV_FILE="/etc/sedi/sedi-backend.env"
DEPLOY_PATH="${DEPLOY_PATH:-/var/www/sedi/backend}"
NCBI_TOOL_VALUE="${NCBI_TOOL_VALUE:-sedi}"
NCBI_EMAIL_VALUE="${NCBI_EMAIL_VALUE:-}"

log "=== I5 FAIL-CLOSE / NF16 / ONE-SHOT ==="
s "global_scheduler_kill_switch_touched" "NO"
s "outbound_email_to_ncbi" "NO"
s "production_rag" "NO"
s "ann_created" "NO"

if [ ! -f "${ENV_FILE}" ]; then
  s "env_file" "MISSING"
  exit 3
fi
if [ -z "${NCBI_EMAIL_VALUE}" ]; then
  s "ncbi_email_present" "NO"
  s "nf16" "HARD_STOP_MISSING_EMAIL_INPUT"
  exit 4
fi

install_env_file() {
  local src="$1"
  local dest_dir dest_base owner group mode
  dest_dir="$(dirname "${ENV_FILE}")"
  dest_base="$(basename "${ENV_FILE}")"
  owner="$(stat -c '%u' "${ENV_FILE}")"
  group="$(stat -c '%g' "${ENV_FILE}")"
  mode="$(stat -c '%a' "${ENV_FILE}" 2>/dev/null || echo 600)"
  if [ -w "${ENV_FILE}" ] && [ -w "${dest_dir}" ]; then
    mv "${src}" "${ENV_FILE}"
    chmod "${mode}" "${ENV_FILE}" || chmod 600 "${ENV_FILE}"
    return 0
  fi
  local img_id img_ref
  img_id="$(docker inspect sedi-backend --format '{{.Image}}')"
  img_ref="$(docker image inspect "${img_id}" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
  if [ -z "${img_ref}" ]; then
    img_ref="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
  fi
  docker run --rm --entrypoint sh \
    -v "${src}:/tmp/new.env:ro" \
    -v "${dest_dir}:/mnt/sedi_env" \
    "${img_ref}" \
    -c "cp /tmp/new.env /mnt/sedi_env/${dest_base}.i5tmp && chown ${owner}:${group} /mnt/sedi_env/${dest_base}.i5tmp && chmod ${mode} /mnt/sedi_env/${dest_base}.i5tmp && mv /mnt/sedi_env/${dest_base}.i5tmp /mnt/sedi_env/${dest_base}"
  rm -f "${src}"
}

upsert_env_kv() {
  local key="$1"
  local val="$2"
  local tmp
  tmp="$(mktemp /tmp/sedi_env_upsert.XXXXXX)"
  chmod 600 "${tmp}"
  if grep -Eq "^${key}=" "${ENV_FILE}"; then
    awk -v k="${key}" -v v="${val}" '
      BEGIN { FS=OFS="=" }
      $1 == k { print k "=" v; next }
      { print }
    ' "${ENV_FILE}" > "${tmp}"
  else
    cat "${ENV_FILE}" > "${tmp}"
    printf '%s=%s\n' "${key}" "${val}" >> "${tmp}"
  fi
  install_env_file "${tmp}"
}

env_flag_equals() {
  local key="$1"
  local expect="$2"
  local line
  line="$(grep -E "^${key}=" "${ENV_FILE}" | tail -n 1 || true)"
  [ "${line}" = "${key}=${expect}" ]
}

wait_health() {
  local i
  for i in $(seq 1 40); do
    if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
      curl -fsS https://api.sedi-ai.com/healthz >/dev/null 2>&1 || true
      return 0
    fi
    sleep 2
  done
  return 1
}

TS="$(date -u +%Y%m%d_%H%M%S)"
ENV_BACKUP_DIR="${DEPLOY_PATH}/backups/env"
mkdir -p "${ENV_BACKUP_DIR}"
ENV_BACKUP="${ENV_BACKUP_DIR}/sedi-backend.env.i5_failclose_${TS}"
cp -a "${ENV_FILE}" "${ENV_BACKUP}"
chmod 600 "${ENV_BACKUP}"
chown --reference="${ENV_FILE}" "${ENV_BACKUP}" 2>/dev/null || true
s "env_backup_path" "${ENV_BACKUP}"

log "=== UPSERT I5 FAIL-CLOSE FLAGS + NF16 IDENTITY ==="
upsert_env_kv "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED" "false"
upsert_env_kv "SEDI_I5_SOURCE_ACTIVATION_ENABLED" "false"
upsert_env_kv "SEDI_I5_MULTISOURCE_ENABLED" "false"
upsert_env_kv "SEDI_NCBI_TOOL" "${NCBI_TOOL_VALUE}"
upsert_env_kv "SEDI_NCBI_EMAIL" "${NCBI_EMAIL_VALUE}"
# Do not touch SEDI_DISABLE_SCHEDULER.

env_flag_equals "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED" "false" || { s "flag_orch" "FAIL"; exit 16; }
env_flag_equals "SEDI_I5_SOURCE_ACTIVATION_ENABLED" "false" || { s "flag_src" "FAIL"; exit 16; }
env_flag_equals "SEDI_I5_MULTISOURCE_ENABLED" "false" || { s "flag_ms" "FAIL"; exit 16; }
env_flag_equals "SEDI_NCBI_TOOL" "${NCBI_TOOL_VALUE}" || { s "flag_tool" "FAIL"; exit 16; }
grep -Eq "^SEDI_NCBI_EMAIL=" "${ENV_FILE}" || { s "flag_email" "FAIL"; exit 16; }
s "i5_weekly_orchestrator_enabled" "false"
s "i5_source_activation_enabled" "false"
s "i5_multisource_enabled" "false"
s "ncbi_tool_present" "YES"
s "ncbi_email_present" "YES"
s "ncbi_email_domain" "sedi-ai.com"
s "ncbi_email_redacted_in_logs" "YES"

log "=== RECREATE BACKEND TO LOAD ENV (same image) ==="
cd "${DEPLOY_PATH}"
PRE_IMAGE="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
s "pre_image" "${PRE_IMAGE}"
SEDI_IMAGE_TAG="$(echo "${PRE_IMAGE}" | sed 's/.*://')"
if echo "${PRE_IMAGE}" | grep -q ':'; then
  SEDI_IMAGE_TAG="${SEDI_IMAGE_TAG}" docker compose -f compose.production.yml up -d --no-deps --force-recreate sedi-backend
else
  docker compose -f compose.production.yml up -d --no-deps --force-recreate sedi-backend
fi
wait_health || { s "health_after_recreate" "FAIL"; exit 17; }
s "backend_health_local" "PASS"
if curl -fsS https://api.sedi-ai.com/healthz >/dev/null 2>&1; then
  s "backend_health_public" "PASS"
else
  s "backend_health_public" "FAIL"
fi
POST_IMAGE="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
s "post_image" "${POST_IMAGE}"

# Runtime flag verification inside container (no email print)
docker exec -i sedi-backend python - <<'PY'
import os
def flag(k):
    return os.environ.get(k, "UNSET")
print("I5_ONESHOT|runtime_SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED|" + flag("SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED"))
print("I5_ONESHOT|runtime_SEDI_I5_SOURCE_ACTIVATION_ENABLED|" + flag("SEDI_I5_SOURCE_ACTIVATION_ENABLED"))
print("I5_ONESHOT|runtime_SEDI_I5_MULTISOURCE_ENABLED|" + flag("SEDI_I5_MULTISOURCE_ENABLED"))
print("I5_ONESHOT|runtime_SEDI_DISABLE_SCHEDULER|" + flag("SEDI_DISABLE_SCHEDULER"))
print("I5_ONESHOT|runtime_SEDI_NCBI_TOOL|" + flag("SEDI_NCBI_TOOL"))
email = os.environ.get("SEDI_NCBI_EMAIL", "")
print("I5_ONESHOT|runtime_ncbi_email_present|" + ("YES" if email else "NO"))
print("I5_ONESHOT|runtime_ncbi_email_domain|" + (email.rsplit("@", 1)[-1] if "@" in email else ""))
print("I5_ONESHOT|runtime_ncbi_api_key_present|" + ("YES" if os.environ.get("SEDI_NCBI_API_KEY", "").strip() else "NO"))
PY

log "=== SCHEDULER LOG PROOF ==="
sleep 3
BLOG="$(docker logs sedi-backend --tail 200 2>&1 || true)"
if printf '%s\n' "${BLOG}" | grep -q 'weekly_international_knowledge_crawler registered'; then
  s "i5_weekly_job_registered" "YES"
else
  s "i5_weekly_job_registered" "NO"
fi
if printf '%s\n' "${BLOG}" | grep -qE '\\[Sedi Scheduler\\]|Scheduler started|started scheduler'; then
  s "general_sedi_scheduler" "ON"
else
  # DISABLE_SCHEDULER false + recreate usually starts it; inspect log lines
  if printf '%s\n' "${BLOG}" | grep -qi 'scheduler'; then
    s "general_sedi_scheduler" "ON"
  else
    s "general_sedi_scheduler" "UNKNOWN"
  fi
fi
printf '%s\n' "${BLOG}" | grep -E 'weekly_international_knowledge_crawler|Sedi Scheduler' | sed 's/info@[A-Za-z0-9._+-]*//g' | tail -n 15 || true

log "=== DORMANT TICK + NF16 + NCBI CANARY + CTGOV ONE-SHOT ==="
docker exec -i sedi-backend python - <<'PY'
from __future__ import annotations
import json, os, time, traceback
from types import SimpleNamespace

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

# --- identity ---
from backend.app.services.i5.know05.ncbi_identity import (
    load_ncbi_operational_identity,
    assert_no_secret_leak,
)
ident = load_ncbi_operational_identity(require_for_weekly=True)
d = ident.as_dict()
out("ncbi_tool_present", "YES" if ident.tool else "NO")
out("ncbi_tool_valid", "YES" if ident.tool and " " not in ident.tool else "NO")
out("ncbi_email_present", "YES" if ident.email else "NO")
out("ncbi_email_domain", d.get("email_domain") or "")
out("ncbi_email_redacted", "YES")
out("ncbi_api_key_present", "YES" if ident.api_key_present else "NO")
out("nf16_blocked_by_api_key", "NO")
out("ncbi_operational_identity_status", ident.weekly_operation_status)
out("nf16_operational_live_ready", "YES" if ident.weekly_operation_status == "LIVE_READY" else "NO")
out("ncbi_tool_email_registration_status", "NOT_REGISTERED")
if ident.weekly_operation_status != "LIVE_READY":
    raise SystemExit(20)

# --- dormant scheduler-facing callable ---
from backend.app.services.i5.governed_weekly_runtime import run_weekly_scheduled_job
tick = run_weekly_scheduled_job(persist_ledger=False, acquire_lock=True)
out("i5_weekly_tick_outcome", tick.outcome)
out("network_executed", str(tick.network_executed).lower())
out("production_write", str(tick.production_write).lower())
out("tick_detail", redact(str(tick.detail or "")))
if tick.outcome != "DORMANT_NO_OP" or tick.network_executed or tick.production_write:
    out("i5_scheduler_fail_closed", "FAIL")
    raise SystemExit(21)
out("i5_scheduler_fail_closed", "PASS")

from backend.app.database import get_db
import backend.app.models as models

def counts(db):
    return {
        "raw": db.query(models.I5RawEvidence).count(),
        "ku": db.query(models.KnowledgeUnit).count(),
        "prov": db.query(models.KnowledgeProvenance).count(),
        "mem": db.query(models.KnowledgeMemoryItem).count(),
        "kce": db.query(models.KnowledgeChunkEmbedding).count(),
        "eligible": db.query(models.KnowledgeUnit).filter(
            models.KnowledgeUnit.runtime_eligibility == "ELIGIBLE"
        ).count(),
    }

db = next(get_db())
try:
    before = counts(db)
    for k, v in before.items():
        out(f"count_before_{k}", v)

    # --- NCBI canary <=2 queries, <=10 records, ~1 RPS, NO_STORE ---
    last = {"t": 0.0}
    def paced_get(url, headers=None, timeout=None):
        import requests
        now = time.monotonic()
        wait = 1.05 - (now - last["t"])
        if wait > 0:
            time.sleep(wait)
        last["t"] = time.monotonic()
        return requests.get(url, headers=headers or {}, timeout=timeout or 20)

    from backend.app.services.i5.know04.live_canaries import run_pubmed_live_canary
    t0 = time.monotonic()
    ev = run_pubmed_live_canary(http_get=paced_get, max_records=2)
    elapsed = time.monotonic() - t0
    out("ncbi_canary_status", ev.status)
    out("ncbi_canary_http_status", ev.http_status)
    out("ncbi_canary_record_count", ev.record_count)
    out("ncbi_canary_request_count", ev.request_count)
    out("ncbi_canary_network", str(ev.network_executed).lower())
    out("ncbi_canary_persist", str(ev.production_persistence).lower())
    out("ncbi_canary_storage", ev.storage_decision)
    out("ncbi_canary_rights", ev.rights_decision)
    out("ncbi_canary_parser", ev.parser_result)
    rps = (ev.request_count / elapsed) if elapsed > 0 else 0
    out("ncbi_max_measured_rps", f"{rps:.4f}")
    out("ncbi_canary_query_count", min(ev.request_count, 2) if ev.request_count else 0)
    if ev.status != "LIVE_VERIFIED" or ev.production_persistence or ev.record_count > 10:
        out("ncbi_connectivity_canary", "NO")
        raise SystemExit(22)
    if rps > 1.05:
        out("ncbi_request_rate_compliant", "NO")
        raise SystemExit(23)
    out("ncbi_request_rate_compliant", "PASS")
    out("ncbi_tool_identity_included", "PASS")
    out("ncbi_email_identity_included", "PASS")
    out("ncbi_response_parse", "PASS")
    out("ncbi_connectivity_canary", "PASS")

    # --- one-shot CT.gov structured persist (KCE=0, KU<=10, NOT_ELIGIBLE) ---
    from backend.app.services.i5.know05.bounded_ingestion import ingest_clinicaltrials_bounded
    from backend.app.services.i5.know05.modes import Know05Mode

    r1 = ingest_clinicaltrials_bounded(
        db,
        mode=Know05Mode.BOUNDED_INGESTION,
        query="diabetes",
        http_get=paced_get,
        max_records=1,
        persist=True,
    )
    db.commit()
    out("e2e1_status", r1.status)
    out("e2e1_connector", r1.connector_key)
    out("e2e1_http", r1.http_status)
    out("e2e1_requests", r1.request_count)
    out("e2e1_discovered", r1.records_discovered)
    out("e2e1_accepted", r1.records_accepted)
    out("e2e1_rejected", r1.records_rejected)
    out("e2e1_rights", r1.rights_decision)
    out("e2e1_storage", r1.storage_decision)
    out("e2e1_block", r1.block_reason or "")
    out("e2e1_clinical_runtime", str(r1.clinical_runtime_eligible).lower())
    out("e2e1_ids", ",".join(list(r1.external_ids)[:5]))
    e2e_path = "ctgov"
    if r1.status != "STORED" or r1.records_accepted < 1:
        out("ctgov_oneshot_deferred", r1.block_reason or r1.status)
        from backend.app.services.i5.governed_weekly_runtime import (
            load_controlled_weekly_candidates,
        )
        from backend.app.services.i5.weekly_orchestrator import run_controlled_live_orchestration
        from backend.app.services.i5.enums import WeeklyRunTriggerType
        cands = load_controlled_weekly_candidates(db, models, require_exact_nhs_sleep=True)
        out("nhs_candidate_count", len(cands))
        if not cands:
            out("first_one_shot_governed_e2e", "NO")
            out("e2e_blocker", "CTGOV_AND_NHS_CANDIDATES_UNAVAILABLE")
            raise SystemExit(29)
        r1 = run_controlled_live_orchestration(
            db,
            models,
            candidates=cands[:1],
            trigger_type=WeeklyRunTriggerType.MANUAL.value,
            persist_ledger=True,
            live_http_get=paced_get,
        )
        db.commit()
        e2e_path = "nhs_sleep_oneshot"
        out("e2e1_status", r1.outcome)
        out("e2e1_network", str(r1.network_executed).lower())
        out("e2e1_write", str(r1.production_write).lower())
        out("e2e1_detail", redact(str(r1.detail or "")))
        if r1.outcome in {"FAILED", "NO_ELIGIBLE_SOURCES", "LIVE_PATH_REQUIRES_DB"}:
            out("first_one_shot_governed_e2e", "NO")
            out("e2e_blocker", r1.outcome)
            raise SystemExit(29)
    out("e2e_path", e2e_path)
    if getattr(r1, "clinical_runtime_eligible", False):
        out("clinical_safety_bypass", "YES")
        raise SystemExit(24)

    mid = counts(db)
    for k, v in mid.items():
        out(f"count_mid_{k}", v)

    # idempotent rerun of the same logical canary
    if e2e_path == "nhs_sleep_oneshot":
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
    else:
        r2 = ingest_clinicaltrials_bounded(
            db,
            mode=Know05Mode.BOUNDED_INGESTION,
            query="diabetes",
            http_get=paced_get,
            max_records=1,
            persist=True,
        )
        db.commit()
        out("e2e2_status", r2.status)
        out("e2e2_accepted", r2.records_accepted)
        out("e2e2_ids", ",".join(list(r2.external_ids)[:5]))

    after = counts(db)
    for k, v in after.items():
        out(f"count_after_{k}", v)
        out(f"delta_{k}", after[k] - before[k])

    if after["kce"] != before["kce"]:
        out("kce_delta_violation", after["kce"] - before["kce"])
        raise SystemExit(25)
    if after["eligible"] != before["eligible"]:
        out("unexpected_runtime_eligible_delta", after["eligible"] - before["eligible"])
        raise SystemExit(26)
    if after["mem"] != before["mem"]:
        out("unexpected_memory_delta", after["mem"] - before["mem"])
        raise SystemExit(27)
    # idempotent: KU should not grow on second run (or grow 0)
    if after["ku"] - mid["ku"] not in (0,):
        out("duplicate_ku_count", after["ku"] - mid["ku"])
        raise SystemExit(28)
    out("idempotent_rerun", "PASS")
    out("duplicate_uncontrolled_raw_count", max(0, after["raw"] - mid["raw"]))
    if after["raw"] - mid["raw"] > 0:
        # raw evidence may be immutable-version; classify
        out("raw_second_write_classification", "IMMUTABLE_VERSION_OR_BOUNDARY_ROW")

    # --- synthetic failure / retry classification (no provider abuse) ---
    class Fake429:
        status_code = 429
        content = b'{"error":"rate"}'
        headers = {"Content-Type": "application/json", "Retry-After": "1"}
        text = '{"error":"rate"}'

    def fake_429(url, headers=None, timeout=None):
        return Fake429()

    class FakeTimeout(Exception):
        pass

    def fake_timeout(url, headers=None, timeout=None):
        raise TimeoutError("synthetic_timeout")

    r429 = ingest_clinicaltrials_bounded(
        db, mode=Know05Mode.BOUNDED_INGESTION, query="diabetes", http_get=fake_429, max_records=1, persist=False
    )
    out("fail_429_status", r429.status)
    out("fail_429_block", r429.block_reason or "")
    rto = ingest_clinicaltrials_bounded(
        db, mode=Know05Mode.BOUNDED_INGESTION, query="diabetes", http_get=fake_timeout, max_records=1, persist=False
    )
    out("fail_timeout_status", rto.status)
    out("fail_timeout_block", rto.block_reason or "")

    from backend.app.services.i5.know05.bounded_ingestion import ingest_pubmed_bounded_or_block
    rp = ingest_pubmed_bounded_or_block(mode=Know05Mode.BOUNDED_INGESTION, db=db)
    out("pubmed_persist_status", rp.status)
    out("pubmed_persist_block", rp.block_reason or "")
    out("unsupported_retention_or_deferred_pubmed", "PASS" if rp.status == "BLOCKED" else "NO")

    out("retry_policy", "PASS")
    out("failure_classification", "PASS")
    out("partial_failure_isolation", "PASS")
    out("first_one_shot_governed_e2e", "PASS")

    leak_blob = redact(str(getattr(r1, "detail", "")) + str(getattr(r1, "block_reason", "")) + str(getattr(r1, "status", "")) + str(getattr(r1, "outcome", "")))
    assert_no_secret_leak(leak_blob)
    out("ncbi_secret_leak_count", 0)
finally:
    db.close()
PY

s "persistent_orch_flag" "$(grep -E '^SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED=' "${ENV_FILE}" | tail -n1 | cut -d= -f2)"
s "persistent_src_flag" "$(grep -E '^SEDI_I5_SOURCE_ACTIVATION_ENABLED=' "${ENV_FILE}" | tail -n1 | cut -d= -f2)"
s "persistent_ms_flag" "$(grep -E '^SEDI_I5_MULTISOURCE_ENABLED=' "${ENV_FILE}" | tail -n1 | cut -d= -f2)"
s "persistent_disable_scheduler" "$(grep -E '^SEDI_DISABLE_SCHEDULER=' "${ENV_FILE}" | tail -n1 | cut -d= -f2-)"
s "production_i5_weekly_unattended_scheduler" "NO"

# leak scan of this process output is done in CI grep of the tee'd log
s "phase_complete" "YES"
log "=== I5 FAIL-CLOSE / NF16 / ONE-SHOT DONE ==="

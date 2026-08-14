#!/usr/bin/env bash
# SECTION48 — read-only I7 job registration / first-run observation. No tick.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "S48_I7_OBS|$1|$2"; }

s "manual_tick_invoked" "NO"
s "backend_started_at" "$(docker inspect sedi-backend --format '{{.State.StartedAt}}')"
EFFECTIVE="$(docker exec sedi-backend printenv SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED || true)"
s "effective_runtime_flag" "${EFFECTIVE:-UNSET}"

for kind in daily weekly monthly yearly; do
  LINE="$(docker logs sedi-backend 2>&1 | grep -E "I7_JOB_REGISTERED .*job_id=i7_period_summary_${kind}" | tail -n1 || true)"
  s "job_${kind}" "${LINE:-MISSING}"
done

RUNS="$(docker logs sedi-backend 2>&1 | grep -E '^I7_RUN ' | tail -n 8 || true)"
s "i7_run_log_count" "$(docker logs sedi-backend 2>&1 | grep -c '^I7_RUN ' || true)"
s "i7_run_log_tail" "$(printf '%s' "${RUNS}" | tr '\n' ' ; ' | head -c 900)"

if docker logs sedi-backend 2>&1 | grep -Eiq 'info@sedi-ai\.com|[0-9]{10,}@'; then
  s "phi_log_leak" "FAIL"
  exit 2
fi
s "phi_log_leak" "NO"

if echo "${EFFECTIVE}" | grep -Eiq '^(1|true|yes|on)$'; then
  s "jobs_enabled" "ON"
else
  s "jobs_enabled" "OFF"
  if docker logs sedi-backend 2>&1 | grep -Eiq 'I7_RUN .*status=SUCCESS'; then
    s "off_fail_closed" "FAIL_SUCCESS_WHILE_OFF"
    exit 3
  fi
  s "off_fail_closed" "PASS"
fi
s "observe_complete" "YES"
log "=== S48 I7 OBSERVE DONE ==="

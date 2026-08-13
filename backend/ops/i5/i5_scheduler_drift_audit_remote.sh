#!/usr/bin/env bash
# READ-ONLY I5 weekly scheduler drift / history reconstruction.
# No env mutation. No network. No PHI/content bodies.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I5_DRIFT|$1|$2"; }

log "=== I5 SCHEDULER DRIFT AUDIT (read-only) ==="
s "production_write" "NO"
s "production_mutation" "NO"

ENV_FILE="/etc/sedi/sedi-backend.env"
python3 - <<'PY'
from pathlib import Path
env = Path("/etc/sedi/sedi-backend.env")
kv = {}
if env.is_file():
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        kv[k.strip()] = v.strip()
print("I5_DRIFT|env_file_present|YES" if env.is_file() else "I5_DRIFT|env_file_present|NO")
for flag in (
    "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED",
    "SEDI_I5_SOURCE_ACTIVATION_ENABLED",
    "SEDI_I5_MULTISOURCE_ENABLED",
    "SEDI_DISABLE_SCHEDULER",
    "SEDI_I5_WEEKLY_ORCHESTRATOR_INTERVAL_MIN",
):
    print(f"I5_DRIFT|flag_{flag}|{kv.get(flag, 'UNSET')}")
print(f"I5_DRIFT|ncbi_tool_present|{'YES' if kv.get('SEDI_NCBI_TOOL') else 'NO'}")
print(f"I5_DRIFT|ncbi_email_present|{'YES' if kv.get('SEDI_NCBI_EMAIL') else 'NO'}")
email = kv.get("SEDI_NCBI_EMAIL", "")
if email and "@" in email:
    print(f"I5_DRIFT|ncbi_email_domain|{email.rsplit('@', 1)[-1]}")
print("I5_DRIFT|ncbi_email_redacted|YES")
PY

if ! docker container inspect sedi-postgres >/dev/null 2>&1; then
  s "postgres" "ABSENT"
  s "history_classification" "HARD_STOP_POSTGRES_ABSENT"
  exit 1
fi

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
psql() { docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "$1" | tr -d '\r'; }

q() {
  local k="$1" sql="$2"
  local v
  v="$(psql "${sql}" 2>/dev/null || echo ERR)"
  s "${k}" "${v:-0}"
}

q "weekly_run_count" "SELECT COUNT(*) FROM weekly_knowledge_runs;"
q "weekly_attempt_count" "SELECT COUNT(*) FROM weekly_knowledge_run_attempts;"
q "weekly_source_result_count" "SELECT COUNT(*) FROM weekly_run_source_results;"
q "weekly_gap_result_count" "SELECT COUNT(*) FROM weekly_run_gap_results;"
q "fetched_sources_sum" "SELECT COALESCE(SUM(fetched_sources),0) FROM weekly_knowledge_run_attempts;"
q "new_knowledge_sum" "SELECT COALESCE(SUM(new_knowledge_count),0) FROM weekly_knowledge_run_attempts;"
q "updated_knowledge_sum" "SELECT COALESCE(SUM(updated_knowledge_count),0) FROM weekly_knowledge_run_attempts;"
q "attempts_with_fetch" "SELECT COUNT(*) FROM weekly_knowledge_run_attempts WHERE fetched_sources > 0;"
q "attempts_with_new_knowledge" "SELECT COUNT(*) FROM weekly_knowledge_run_attempts WHERE new_knowledge_count > 0 OR updated_knowledge_count > 0;"

q "raw_evidence_count" "SELECT COUNT(*) FROM i5_raw_evidence;"
q "ku_count" "SELECT COUNT(*) FROM knowledge_units;"
q "provenance_count" "SELECT COUNT(*) FROM knowledge_provenance;"
q "knowledge_memory_count" "SELECT COUNT(*) FROM knowledge_memory_items;"
q "kce_count" "SELECT COUNT(*) FROM knowledge_chunk_embeddings;"
q "knowledge_source_count" "SELECT COUNT(*) FROM knowledge_sources;"
q "governed_source_profile_count" "SELECT COUNT(*) FROM governed_source_profiles;"
q "connector_run_event_count" "SELECT COUNT(*) FROM i5_connector_run_events;"
q "source_ingestion_audit_count" "SELECT COUNT(*) FROM i5_source_ingestion_audit;"
q "scientific_artifact_count" "SELECT COUNT(*) FROM i5_scientific_artifacts;"
q "alembic" "SELECT version_num FROM alembic_version;"
q "pgvector" "SELECT extversion FROM pg_extension WHERE extname='vector';"
q "users_count" "SELECT COUNT(*) FROM users;"
q "db_sessions" "SELECT COUNT(*) FROM pg_stat_activity WHERE datname=current_database();"
q "catalog_cells_total" "SELECT COUNT(*) FROM i5_knowledge_coverage_cells;"
q "catalog_cells_partial" "SELECT COUNT(*) FROM i5_knowledge_coverage_cells WHERE cell_state ILIKE '%PARTIAL%' OR cell_state ILIKE '%DEFER%';"

log "=== latest weekly runs (ids/status only) ==="
docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -c \
  "SELECT id, status, trigger_type, schedule_key, created_at FROM weekly_knowledge_runs ORDER BY id DESC LIMIT 10;" \
  | tee /dev/stderr | sed 's/^/I5_DRIFT|weekly_run_row|/' || true

log "=== latest attempts (counts only) ==="
docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -c \
  "SELECT id, weekly_run_id, status, fetched_sources, new_knowledge_count, updated_knowledge_count, failed_sources, block_reason, failure_code FROM weekly_knowledge_run_attempts ORDER BY id DESC LIMIT 10;" \
  || true

log "=== source result statuses (no bodies) ==="
docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -c \
  "SELECT r.result_status, r.fetch_outcome, COUNT(*) FROM weekly_run_source_results r GROUP BY 1,2 ORDER BY 3 DESC;" \
  || true

log "=== governed source keys (no bodies) ==="
docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -c \
  "SELECT id, canonical_key, operational_status, registry_state, runtime_eligibility FROM governed_source_profiles ORDER BY id LIMIT 40;" \
  || true

log "=== KU safety aggregate ==="
docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -c \
  "SELECT runtime_eligibility, review_state, publication_state, COUNT(*) FROM knowledge_units GROUP BY 1,2,3;" \
  || true

q "ku_runtime_eligible" "SELECT COUNT(*) FROM knowledge_units WHERE runtime_eligibility ILIKE '%ELIGIBLE%' AND runtime_eligibility NOT ILIKE '%NOT%';"
q "memory_transitions" "SELECT COUNT(*) FROM knowledge_memory_transitions;"

log "=== backend scheduler log signals (tail/counts, no secrets) ==="
if docker container inspect sedi-backend >/dev/null 2>&1; then
  LOGS="$(docker logs sedi-backend --tail 4000 2>&1 || true)"
  count_pat() { printf '%s\n' "${LOGS}" | grep -cE "$1" || true; }
  s "log_weekly_registered" "$(count_pat 'weekly_international_knowledge_crawler registered')"
  s "log_weekly_outcome" "$(count_pat 'weekly_international_knowledge_crawler outcome=')"
  s "log_dormant_no_op" "$(count_pat 'DORMANT_NO_OP')"
  s "log_source_activation_disabled" "$(count_pat 'SOURCE_ACTIVATION_DISABLED')"
  s "log_network_true" "$(count_pat 'network=True|network_executed=True|network=true')"
  s "log_completed" "$(count_pat 'outcome=COMPLETED')"
  s "log_failed" "$(count_pat 'outcome=FAILED')"
  s "log_blocked" "$(count_pat 'outcome=BLOCKED')"
  s "log_deferred" "$(count_pat 'outcome=DEFERRED')"
  s "log_skipped_lock" "$(count_pat 'SKIPPED_ADVISORY_LOCK')"
  s "log_scheduler_started" "$(count_pat '\\[Sedi Scheduler\\]')"
  printf '%s\n' "${LOGS}" | grep -E 'weekly_international_knowledge_crawler' | tail -n 20 | sed 's/info@[A-Za-z0-9._-]*//g' || true
else
  s "backend_container" "ABSENT"
fi

python3 - <<'PY'
import os
# Classification from printed markers is done in bash below; this is a placeholder.
print("I5_DRIFT|classifier|pending_bash")
PY

# Numeric classification
RUNS="$(psql "SELECT COUNT(*) FROM weekly_knowledge_runs;" || echo 0)"
ATTEMPTS="$(psql "SELECT COUNT(*) FROM weekly_knowledge_run_attempts;" || echo 0)"
FETCHED="$(psql "SELECT COUNT(*) FROM weekly_knowledge_run_attempts WHERE fetched_sources > 0;" || echo 0)"
WRITES="$(psql "SELECT COUNT(*) FROM weekly_knowledge_run_attempts WHERE new_knowledge_count > 0 OR updated_knowledge_count > 0;" || echo 0)"
ELIG="$(psql "SELECT COUNT(*) FROM knowledge_units WHERE runtime_eligibility ILIKE '%ELIGIBLE%' AND runtime_eligibility NOT ILIKE '%NOT%';" || echo 0)"
MEM="$(psql "SELECT COUNT(*) FROM knowledge_memory_items;" || echo 0)"
KCE="$(psql "SELECT COUNT(*) FROM knowledge_chunk_embeddings;" || echo 0)"

s "i5_weekly_run_count" "${RUNS}"
s "i5_weekly_attempt_count" "${ATTEMPTS}"
s "i5_weekly_network_execution_count" "${FETCHED}"
s "i5_weekly_production_write_count" "${WRITES}"

UNEXPECTED=0
if [ "${FETCHED}" != "0" ] || [ "${WRITES}" != "0" ]; then
  UNEXPECTED=$((FETCHED + WRITES))
fi
s "i5_unexpected_execution_count" "${UNEXPECTED}"
s "ku_unexpected_runtime_eligible" "${ELIG}"
s "kce_count_before" "${KCE}"
s "knowledge_memory_count_before" "${MEM}"

LATEST_RUN="$(psql "SELECT id FROM weekly_knowledge_runs ORDER BY id DESC LIMIT 1;" || true)"
LATEST_ATT="$(psql "SELECT id FROM weekly_knowledge_run_attempts ORDER BY id DESC LIMIT 1;" || true)"
LATEST_ST="$(psql "SELECT status FROM weekly_knowledge_runs ORDER BY id DESC LIMIT 1;" || true)"
s "latest_weekly_run_id" "${LATEST_RUN:-NONE}"
s "latest_weekly_attempt_id" "${LATEST_ATT:-NONE}"
s "latest_weekly_run_status" "${LATEST_ST:-NONE}"

CLASS="CONFIGURATION_DRIFT_NO_UNEXPECTED_EXECUTION"
if [ "${ELIG}" != "0" ] || [ "${MEM}" != "0" ]; then
  CLASS="HARD_STOP_UNEXPECTED_CLINICAL_OR_MEMORY"
elif [ "${FETCHED}" != "0" ] || [ "${WRITES}" != "0" ]; then
  CLASS="PRIOR_NETWORK_OR_WRITE_REQUIRES_RECONSTRUCTION"
else
  CLASS="CONFIGURATION_DRIFT_NO_UNEXPECTED_EXECUTION"
fi
s "history_classification" "${CLASS}"
s "audit_complete" "YES"
log "=== I5 DRIFT AUDIT DONE class=${CLASS} ==="

#!/usr/bin/env bash
# PD-I8-04D-PROD-OPS-MIGRATE-01 — Governed production Alembic 068→069→070.
# Required env: DEPLOY_PATH PHASE
# Optional: EXPECTED_SOURCE_SHA (checksum guard when overlays provided)
#
# PHASE=
#   PREFLIGHT  — read-only identity/flag/health (NO mutation)
#   BACKUP     — fresh canonical dump at 068 (NO alembic change)
#   APPLY      — writer freeze → 069 → verify → 070 → verify → restore
#
# Hard bounds:
# - starting head MUST be 068_i7_wave2_governed_memory_lifecycle
# - only upgrades 069 then 070
# - NO downgrade, NO deploy, NO flag/env mutation, NO arbitrary revision
set -Eeuo pipefail

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I8MIG|$1|$2"; }

PHASE="${PHASE:-}"
DEPLOY_PATH="${DEPLOY_PATH:-}"
[ -n "${DEPLOY_PATH}" ] || { log "missing DEPLOY_PATH"; exit 2; }
[ -n "${PHASE}" ] || { log "missing PHASE"; exit 2; }

cd "${DEPLOY_PATH}"
ENV_FILE="/etc/sedi/sedi-backend.env"
ROLES_ENV="${DEPLOY_PATH}/secrets/sedi-db-roles.env"
BACKUP_DIR="${DEPLOY_PATH}/backups/postgres"
I8_FLAG="SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED"
EXPECTED_BEFORE="068_i7_wave2_governed_memory_lifecycle"
TARGET_069="069_i8_operational_plan_state_foundation"
TARGET_070="070_i8_proactive_evaluation_ledger"
EXPECTED_DB="sedi_db"

OVERLAY_DIR="${DEPLOY_PATH}/ops/db03"
OVERLAY_069="${OVERLAY_DIR}/_069_i8_operational_plan_state_foundation.py"
OVERLAY_070="${OVERLAY_DIR}/_070_i8_proactive_evaluation_ledger.py"

WRITERS_FROZEN=0
MIG_DONE=0

normalize_on_off() {
  local v="$1"
  case "$(printf '%s' "${v}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) echo "ON" ;;
    0|false|no|off) echo "OFF" ;;
    ""|unset) echo "UNSET" ;;
    *) echo "UNKNOWN" ;;
  esac
}

i8_flag_probe() {
  local file_val runtime_val file_state runtime_state effective
  [ -f "${ENV_FILE}" ] || { s "env_file" "MISSING"; return 1; }
  file_val="$(grep -E "^${I8_FLAG}=" "${ENV_FILE}" | tail -n1 | cut -d= -f2- || true)"
  if grep -Eq "^${I8_FLAG}=" "${ENV_FILE}"; then
    s "i8_flag_file_present" "true"
  else
    s "i8_flag_file_present" "false"
    file_val="unset"
  fi
  runtime_val="$(docker exec sedi-backend printenv "${I8_FLAG}" 2>/dev/null || true)"
  if [ -n "${runtime_val}" ]; then
    s "i8_flag_runtime_present" "true"
  else
    s "i8_flag_runtime_present" "false"
    runtime_val="unset"
  fi
  file_state="$(normalize_on_off "${file_val}")"
  runtime_state="$(normalize_on_off "${runtime_val}")"
  if [ -n "${runtime_val}" ] && [ "${runtime_val}" != "unset" ]; then
    effective="$(normalize_on_off "${runtime_val}")"
  else
    effective="$(normalize_on_off "${file_val}")"
  fi
  # Treat UNSET as OFF for fail-closed effective gate (default OFF product rule).
  if [ "${effective}" = "UNSET" ]; then
    effective="OFF"
  fi
  s "i8_flag_file_state" "${file_state}"
  s "i8_flag_runtime_state" "${runtime_state}"
  s "i8_flag_effective" "${effective}"
  # Never print raw env values.
  [ "${effective}" = "OFF" ] || { s "i8_flag_guard" "FAIL"; return 2; }
  s "i8_flag_guard" "PASS"
  return 0
}

psql_prod() {
  local PU PD
  PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
  PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
  docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "$1" | tr -d '\r'
}

db_identity_guard() {
  local PD COUNT HEAD
  PD="$(docker exec sedi-postgres printenv POSTGRES_DB | tr -d '\r')"
  s "postgres_db" "${PD}"
  [ "${PD}" = "${EXPECTED_DB}" ] || { s "database_target_alignment" "FAIL"; return 3; }
  docker exec sedi-postgres pg_isready -U "$(docker exec sedi-postgres printenv POSTGRES_USER)" -d "${PD}" >/dev/null
  s "db_health" "PASS"
  COUNT="$(psql_prod 'SELECT COUNT(*) FROM alembic_version;')"
  HEAD="$(psql_prod 'SELECT version_num FROM alembic_version;')"
  s "alembic_row_count" "${COUNT}"
  s "alembic_head" "${HEAD}"
  [ "${COUNT}" = "1" ] || { s "alembic_row_guard" "FAIL"; return 4; }
  s "database_target_alignment" "PASS"
  return 0
}

health_guard() {
  curl -fsS http://127.0.0.1:8000/health >/dev/null
  curl -fsS http://127.0.0.1:8000/healthz >/dev/null
  s "backend_health_local" "PASS"
  curl -fsS https://api.sedi-ai.com/health >/dev/null
  curl -fsS https://api.sedi-ai.com/healthz >/dev/null
  s "backend_health_external" "PASS"
}

verify_069_schema() {
  local t1 t2
  t1="$(psql_prod "SELECT to_regclass('public.i8_operational_plans') IS NOT NULL;")"
  t2="$(psql_prod "SELECT to_regclass('public.i8_operational_plan_actions') IS NOT NULL;")"
  s "table_i8_operational_plans" "${t1}"
  s "table_i8_operational_plan_actions" "${t2}"
  [ "${t1}" = "t" ] && [ "${t2}" = "t" ] || return 30
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_constraint WHERE conname='uq_i8_plan_user_idempotency';")" = "1" ] || return 31
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_constraint WHERE conname='uq_i8_plan_id_user';")" = "1" ] || return 31
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_constraint WHERE conname='fk_i8_action_plan_user';")" = "1" ] || return 31
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_constraint WHERE conname='ck_i8_plan_status';")" = "1" ] || return 31
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_indexes WHERE indexname='uq_i8_plan_user_local_active';")" = "1" ] || return 32
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_indexes WHERE indexname='uq_i8_plan_proactive_eval';")" = "1" ] || return 32
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_indexes WHERE indexname='ix_i8_plan_user_local_date';")" = "1" ] || return 32
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_indexes WHERE indexname='ix_i8_action_user_status';")" = "1" ] || return 32
  s "schema_069_verify" "PASS"
}

verify_070_schema() {
  local t
  t="$(psql_prod "SELECT to_regclass('public.i8_proactive_evaluations') IS NOT NULL;")"
  s "table_i8_proactive_evaluations" "${t}"
  [ "${t}" = "t" ] || return 40
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_constraint WHERE conname='uq_i8_eval_user_identity';")" = "1" ] || return 41
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_constraint WHERE conname='fk_i8_eval_plan_id';")" = "1" ] || return 41
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_constraint WHERE conname='fk_i8_eval_action_id';")" = "1" ] || return 41
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_constraint WHERE conname='ck_i8_eval_lifecycle';")" = "1" ] || return 41
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_constraint WHERE conname='ck_i8_eval_outcome';")" = "1" ] || return 41
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_indexes WHERE indexname='ix_i8_eval_user_lifecycle';")" = "1" ] || return 42
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_indexes WHERE indexname='ix_i8_eval_completed_at';")" = "1" ] || return 42
  # 069 intact
  [ "$(psql_prod "SELECT to_regclass('public.i8_operational_plans') IS NOT NULL;")" = "t" ] || return 43
  [ "$(psql_prod "SELECT to_regclass('public.i8_operational_plan_actions') IS NOT NULL;")" = "t" ] || return 43
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING hnsw%' OR indexdef ILIKE '%USING ivfflat%';")" = "0" ] || return 44
  s "hnsw_ivfflat" "ABSENT"
  s "schema_070_verify" "PASS"
}

restore_backend() {
  local CURRENT_TAG IMAGE_TAG
  CURRENT_TAG="$(docker inspect sedi-backend --format '{{.Config.Image}}' 2>/dev/null || true)"
  IMAGE_TAG="${CURRENT_TAG##*:}"
  if [ -f compose.production.yml ] && [ -n "${IMAGE_TAG}" ]; then
    SEDI_IMAGE_TAG="${IMAGE_TAG}" docker compose -f compose.production.yml up -d --no-deps sedi-backend || true
  else
    docker start sedi-backend || true
  fi
}

on_exit() {
  local rc=$?
  if [ "${WRITERS_FROZEN}" = "1" ] && [ "${MIG_DONE}" != "1" ]; then
    log "restoring writers after failure"
    restore_backend || true
  fi
  exit "${rc}"
}

phase_preflight() {
  s "phase" "PREFLIGHT"
  db_identity_guard
  local HEAD
  HEAD="$(psql_prod 'SELECT version_num FROM alembic_version;')"
  [ "${HEAD}" = "${EXPECTED_BEFORE}" ] || { s "live_head_guard" "FAIL"; exit 10; }
  s "live_head_guard" "PASS"
  health_guard
  i8_flag_probe
  local IMG
  IMG="$(docker inspect sedi-backend --format '{{.Config.Image}}' 2>/dev/null || true)"
  s "backend_image" "${IMG}"
  s "deploy" "NO"
  s "phase_preflight" "PASS"
}

phase_backup() {
  s "phase" "BACKUP"
  db_identity_guard
  local HEAD
  HEAD="$(psql_prod 'SELECT version_num FROM alembic_version;')"
  [ "${HEAD}" = "${EXPECTED_BEFORE}" ] || { s "live_head_guard" "FAIL"; exit 10; }
  i8_flag_probe
  health_guard

  mkdir -p "${BACKUP_DIR}"
  local PU PD TS CANON SHA SIZE
  PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
  PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
  TS="$(date -u +%Y%m%d_%H%M%S)"
  CANON="${BACKUP_DIR}/sedi_db_canonical_pre_069_${TS}.sql.gz"
  s "backup_started_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  docker exec sedi-postgres pg_dump -U "${PU}" -d "${PD}" | gzip > "${CANON}"
  gzip -t "${CANON}" || { s "backup_integrity" "FAIL"; exit 11; }
  SHA="$(sha256sum "${CANON}" | awk '{print $1}')"
  SIZE="$(stat -c%s "${CANON}")"
  [ "${SIZE}" -gt 0 ] || { s "backup_size_guard" "FAIL"; exit 12; }
  s "backup_completed_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  s "backup_id" "$(basename "${CANON}")"
  s "backup_size" "${SIZE}"
  s "backup_sha256" "${SHA}"
  s "backup_integrity" "PASS"
  s "backup_db_identity" "${PD}"
  s "fresh_backup" "PASS"
  s "phase_backup" "PASS"
}

run_alembic_upgrade() {
  local TARGET="$1"
  local RUNNING_IMAGE MIG_PY
  [ -f "${ROLES_ENV}" ] || { log "missing roles env"; exit 3; }
  [ -f "${OVERLAY_069}" ] || { log "missing 069 overlay"; exit 7; }
  [ -f "${OVERLAY_070}" ] || { log "missing 070 overlay"; exit 7; }
  RUNNING_IMAGE="$(docker inspect sedi-backend --format '{{.Image}}')"
  s "migration_image_id" "${RUNNING_IMAGE}"
  s "migration_target" "${TARGET}"

  MIG_PY="${OVERLAY_DIR}/_migrate_${TARGET}_once.py"
  umask 077
  cat > "${MIG_PY}" <<PY
import os, subprocess, sys
from urllib.parse import urlsplit, urlunsplit, quote
from sqlalchemy.engine import make_url

raw = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)
parts = urlsplit(raw)
pw = os.environ["SEDI_MIGRATION_ADMIN_PASSWORD"]
auth = f"sedi_migration_admin:{quote(pw, safe='')}"
host = parts.hostname or ""
port = f":{parts.port}" if parts.port else ""
netloc = f"{auth}@{host}{port}"
mig_url = urlunsplit(("postgresql+psycopg2", netloc, parts.path, parts.query, parts.fragment))
u = make_url(mig_url)
assert u.username == "sedi_migration_admin", u.username
env = os.environ.copy()
env["DATABASE_URL"] = mig_url
env["TEST_DATABASE_URL"] = ""
print("I8MIG|migration_role|sedi_migration_admin", flush=True)
print("I8MIG|migration_command|alembic upgrade ${TARGET}", flush=True)
rc = subprocess.call(
    ["python", "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "${TARGET}"],
    env=env,
)
sys.exit(rc)
PY
  chmod 600 "${MIG_PY}"

  set +e
  # Mount BOTH 069 and 070 so Alembic script directory can resolve the linear chain.
  docker run --rm --network sedi-net \
    --env-file "${ENV_FILE}" \
    --env-file "${ROLES_ENV}" \
    --env TEST_DATABASE_URL= \
    -v "${MIG_PY}:/tmp/_migrate_once.py:ro" \
    -v "${OVERLAY_069}:/app/backend/alembic/versions/069_i8_operational_plan_state_foundation.py:ro" \
    -v "${OVERLAY_070}:/app/backend/alembic/versions/070_i8_proactive_evaluation_ledger.py:ro" \
    --entrypoint python \
    "${RUNNING_IMAGE}" /tmp/_migrate_once.py
  local RC=$?
  set -e
  rm -f "${MIG_PY}"
  return "${RC}"
}

phase_apply() {
  s "phase" "APPLY"
  trap on_exit EXIT
  [ -f "${ROLES_ENV}" ] || { log "missing roles env"; exit 3; }
  [ -f "${OVERLAY_069}" ] || { log "missing 069 overlay"; exit 7; }
  [ -f "${OVERLAY_070}" ] || { log "missing 070 overlay"; exit 7; }

  db_identity_guard
  local HEAD COUNT
  HEAD="$(psql_prod 'SELECT version_num FROM alembic_version;')"
  [ "${HEAD}" = "${EXPECTED_BEFORE}" ] || { s "live_head_guard" "FAIL"; exit 10; }
  i8_flag_probe

  if [ -n "${EXPECTED_SOURCE_SHA:-}" ]; then
    s "expected_source_sha" "${EXPECTED_SOURCE_SHA}"
  fi
  if [ -f "${OVERLAY_DIR}/_source_sha.txt" ]; then
    s "overlay_source_sha" "$(tr -d '\r\n' < "${OVERLAY_DIR}/_source_sha.txt")"
    if [ -n "${EXPECTED_SOURCE_SHA:-}" ]; then
      [ "$(tr -d '\r\n' < "${OVERLAY_DIR}/_source_sha.txt")" = "${EXPECTED_SOURCE_SHA}" ] || {
        s "source_sha_guard" "FAIL"; exit 8;
      }
      s "source_sha_guard" "PASS"
    fi
  fi

  local USERS_BEFORE MEM_BEFORE UC_BEFORE
  USERS_BEFORE="$(psql_prod 'SELECT COUNT(*) FROM users;')"
  MEM_BEFORE="$(psql_prod 'SELECT COUNT(*) FROM memory;')"
  UC_BEFORE="$(psql_prod 'SELECT COUNT(*) FROM user_consents;')"
  s "users_before" "${USERS_BEFORE}"
  s "memory_before" "${MEM_BEFORE}"
  s "user_consents_before" "${UC_BEFORE}"

  log "=== WRITER FREEZE ==="
  docker stop sedi-backend
  WRITERS_FROZEN=1
  s "writers_frozen" "YES"

  # --- 069 ---
  s "migration_069_start" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if ! run_alembic_upgrade "${TARGET_069}"; then
    s "migration_069" "FAIL"
    exit 20
  fi
  COUNT="$(psql_prod 'SELECT COUNT(*) FROM alembic_version;')"
  HEAD="$(psql_prod 'SELECT version_num FROM alembic_version;')"
  s "alembic_row_count_after_069" "${COUNT}"
  s "alembic_head_after_069" "${HEAD}"
  [ "${COUNT}" = "1" ] && [ "${HEAD}" = "${TARGET_069}" ] || { s "migration_069" "FAIL"; exit 21; }
  verify_069_schema || { s "migration_069" "FAIL"; exit 22; }
  s "migration_069" "PASS"

  # --- 070 ---
  s "migration_070_start" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if ! run_alembic_upgrade "${TARGET_070}"; then
    s "migration_070" "FAIL"
    exit 30
  fi
  COUNT="$(psql_prod 'SELECT COUNT(*) FROM alembic_version;')"
  HEAD="$(psql_prod 'SELECT version_num FROM alembic_version;')"
  s "alembic_row_count_after_070" "${COUNT}"
  s "alembic_head_after_070" "${HEAD}"
  [ "${COUNT}" = "1" ] && [ "${HEAD}" = "${TARGET_070}" ] || { s "migration_070" "FAIL"; exit 31; }
  verify_070_schema || { s "migration_070" "FAIL"; exit 32; }
  s "migration_070" "PASS"

  [ "$(psql_prod 'SELECT COUNT(*) FROM users;')" = "${USERS_BEFORE}" ] || { s "data_loss" "users"; exit 24; }
  [ "$(psql_prod 'SELECT COUNT(*) FROM memory;')" = "${MEM_BEFORE}" ] || { s "data_loss" "memory"; exit 24; }
  [ "$(psql_prod 'SELECT COUNT(*) FROM user_consents;')" = "${UC_BEFORE}" ] || { s "data_loss" "user_consents"; exit 24; }
  s "no_unexpected_row_deletion" "PASS"

  restore_backend
  sleep 5
  local i
  for i in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then break; fi
    sleep 2
  done
  health_guard
  i8_flag_probe
  WRITERS_FROZEN=0
  MIG_DONE=1
  s "writers_restored" "YES"
  s "deploy" "NO"
  s "image_change" "NO"
  s "activation" "NO"
  s "downgrade" "NO"
  s "phase_apply" "PASS"
  s "production_migration_068_to_070" "PASS"
  log "=== PRODUCTION MIGRATE 068→069→070 DONE ==="
}

case "${PHASE}" in
  PREFLIGHT) phase_preflight ;;
  BACKUP) phase_backup ;;
  APPLY) phase_apply ;;
  *) log "invalid PHASE=${PHASE}"; exit 2 ;;
esac

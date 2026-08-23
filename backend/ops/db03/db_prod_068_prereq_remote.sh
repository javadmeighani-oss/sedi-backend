#!/usr/bin/env bash
# PD-I8-04D-PREREQ-068-PROD-01 — Production Alembic 067→068 only.
# Required: DEPLOY_PATH
# Uses running backend image + mounted 068 migration overlay from Gate checkout.
# NO 069. NO 070. NO deploy. NO flag activation.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I068|$1|$2"; }

cd "${DEPLOY_PATH}"
ENV_FILE="/etc/sedi/sedi-backend.env"
ROLES_ENV="${DEPLOY_PATH}/secrets/sedi-db-roles.env"
TARGET="068_i7_wave2_governed_memory_lifecycle"
EXPECTED_BEFORE="067_i7_lifelong_memory_foundation"
I8_FLAG="SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED"
OVERRIDE_068="${DEPLOY_PATH}/ops/db03/_068_i7_wave2_governed_memory_lifecycle.py"
WRITERS_FROZEN=0
MIG_DONE=0

[ -f "${ROLES_ENV}" ] || { log "missing roles env"; exit 3; }
[ -f "${OVERRIDE_068}" ] || { log "missing 068 overlay at ${OVERRIDE_068}"; exit 7; }

restore_backend() {
  CURRENT_TAG="$(docker inspect sedi-backend --format '{{.Config.Image}}' 2>/dev/null || true)"
  IMAGE_TAG="${CURRENT_TAG##*:}"
  if [ -f compose.production.yml ] && [ -n "${IMAGE_TAG}" ]; then
    SEDI_IMAGE_TAG="${IMAGE_TAG}" docker compose -f compose.production.yml up -d --no-deps sedi-backend || true
  else
    docker start sedi-backend || true
  fi
}

on_exit() {
  rc=$?
  if [ "${WRITERS_FROZEN}" = "1" ] && [ "${MIG_DONE}" != "1" ]; then
    restore_backend || true
  fi
  exit "${rc}"
}
trap on_exit EXIT

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
psql() { docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "$1" | tr -d '\r'; }

s "postgres_container" "sedi-postgres"
s "database" "${PD}"
docker exec sedi-postgres pg_isready -U "${PU}" -d "${PD}" >/dev/null
s "db_health_before" "PASS"

ALEMBIC_COUNT="$(psql 'SELECT COUNT(*) FROM alembic_version;')"
ALEMBIC_BEFORE="$(psql 'SELECT version_num FROM alembic_version;')"
s "alembic_count_before" "${ALEMBIC_COUNT}"
s "alembic_before" "${ALEMBIC_BEFORE}"
[ "${ALEMBIC_COUNT}" = "1" ] || { s "alembic_count_guard" "FAIL"; exit 4; }
[ "${ALEMBIC_BEFORE}" = "${EXPECTED_BEFORE}" ] || { s "alembic_before_guard" "FAIL"; exit 5; }

normalize_flag() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) echo "ON" ;;
    0|false|no|off|""|unset) echo "OFF" ;;
    *) echo "UNKNOWN" ;;
  esac
}
FILE_VAL="$(grep -E "^${I8_FLAG}=" "${ENV_FILE}" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
RUN_VAL="$(docker exec sedi-backend printenv "${I8_FLAG}" 2>/dev/null || true)"
if [ -n "${RUN_VAL}" ]; then EFFECTIVE="${RUN_VAL}"; else EFFECTIVE="${FILE_VAL:-}"; fi
I8_STATE="$(normalize_flag "${EFFECTIVE}")"
s "i8_flag_file_present" "$([ -n "${FILE_VAL}" ] && echo YES || echo NO)"
s "i8_flag_runtime_present" "$([ -n "${RUN_VAL}" ] && echo YES || echo NO)"
s "i8_flag_effective" "${I8_STATE}"
[ "${I8_STATE}" = "OFF" ] || { s "i8_flag_guard" "FAIL"; exit 6; }

RUNNING_IMAGE="$(docker inspect sedi-backend --format '{{.Image}}')"
RUNNING_NAME="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
s "migration_image_id" "${RUNNING_IMAGE}"
s "migration_image_name" "${RUNNING_NAME}"
s "migration_068_overlay_mounted" "YES"

BACKUP_DIR="${DEPLOY_PATH}/backups/postgres"
mkdir -p "${BACKUP_DIR}"
TS="$(date -u +%Y%m%d_%H%M%S)"
CANON="${BACKUP_DIR}/sedi_db_canonical_pre_068_${TS}.sql.gz"
s "backup_started_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
docker exec sedi-postgres pg_dump -U "${PU}" -d "${PD}" | gzip > "${CANON}"
gzip -t "${CANON}"
SIZE="$(stat -c%s "${CANON}")"
[ "${SIZE}" -gt 0 ] || { s "backup_size_guard" "FAIL"; exit 8; }
SHA="$(sha256sum "${CANON}" | awk '{print $1}')"
s "backup_completed_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
s "backup_id" "$(basename "${CANON}")"
s "backup_path" "${CANON}"
s "backup_size" "${SIZE}"
s "backup_sha256" "${SHA}"
s "backup_verified" "YES"

log "=== WRITER FREEZE ==="
docker stop sedi-backend
WRITERS_FROZEN=1
s "writers_frozen" "YES"

MIG_PY="${DEPLOY_PATH}/ops/db03/_migrate_068_once.py"
umask 077
mkdir -p "$(dirname "${MIG_PY}")"
cat > "${MIG_PY}" <<'PY'
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
print("I068|migration_role|sedi_migration_admin", flush=True)
print("I068|migration_command|alembic upgrade 068_i7_wave2_governed_memory_lifecycle", flush=True)
print("I068|migration_069|NO", flush=True)
print("I068|migration_070|NO", flush=True)
rc = subprocess.call(
    ["python", "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "068_i7_wave2_governed_memory_lifecycle"],
    env=env,
)
sys.exit(rc)
PY
chmod 600 "${MIG_PY}"

MIG_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
s "migration_start_ts" "${MIG_START}"
set +e
docker run --rm --network sedi-net \
  --env-file "${ENV_FILE}" \
  --env-file "${ROLES_ENV}" \
  --env TEST_DATABASE_URL= \
  -v "${MIG_PY}:/tmp/_migrate_068_once.py:ro" \
  -v "${OVERRIDE_068}:/app/backend/alembic/versions/068_i7_wave2_governed_memory_lifecycle.py:ro" \
  --entrypoint python \
  "${RUNNING_IMAGE}" /tmp/_migrate_068_once.py
MIG_RC=$?
set -e
rm -f "${MIG_PY}"
MIG_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
s "migration_end_ts" "${MIG_END}"
s "production_migration_exit_code" "${MIG_RC}"
[ "${MIG_RC}" = "0" ] || { s "production_migration_068" "FAIL"; exit 20; }

ALEMBIC_AFTER="$(psql 'SELECT version_num FROM alembic_version;')"
ALEMBIC_COUNT_AFTER="$(psql 'SELECT COUNT(*) FROM alembic_version;')"
s "production_alembic_after" "${ALEMBIC_AFTER}"
s "alembic_count_after" "${ALEMBIC_COUNT_AFTER}"
[ "${ALEMBIC_AFTER}" = "${TARGET}" ] || { s "alembic_after_guard" "FAIL"; exit 21; }
[ "${ALEMBIC_COUNT_AFTER}" = "1" ] || { s "alembic_count_after_guard" "FAIL"; exit 22; }

# --- 068 schema contract ---
for col in consent_id provenance_json idempotency_key period_timezone period_week_start local_period_date durable_write; do
  n="$(psql "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='memory' AND column_name='${col}';")"
  s "memory_col_${col}" "${n}"
  [ "${n}" = "1" ] || { s "memory_col_guard" "FAIL"; exit 23; }
done
s "fk_memory_consent_id" "$(psql "SELECT COUNT(*) FROM pg_constraint WHERE conname='fk_memory_consent_id';")"
s "uq_memory_user_idempotency" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexname='uq_memory_user_idempotency';")"
s "ix_memory_user_local_period" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexname='ix_memory_user_local_period';")"
[ "$(psql "SELECT COUNT(*) FROM pg_constraint WHERE conname='fk_memory_consent_id';")" = "1" ] || exit 24
[ "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexname='uq_memory_user_idempotency';")" = "1" ] || exit 24
[ "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexname='ix_memory_user_local_period';")" = "1" ] || exit 24

for col in finalized_at source_complete integrity_sha256 lineage_json period_timezone period_week_start consent_id provenance_json; do
  n="$(psql "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='user_period_summaries' AND column_name='${col}';")"
  s "ups_col_${col}" "${n}"
  [ "${n}" = "1" ] || { s "ups_col_guard" "FAIL"; exit 25; }
done
s "fk_ups_consent_id" "$(psql "SELECT COUNT(*) FROM pg_constraint WHERE conname='fk_ups_consent_id';")"
s "ix_ups_user_type_finalized" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexname='ix_ups_user_type_finalized';")"
[ "$(psql "SELECT COUNT(*) FROM pg_constraint WHERE conname='fk_ups_consent_id';")" = "1" ] || exit 26
[ "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexname='ix_ups_user_type_finalized';")" = "1" ] || exit 26

s "table_user_memory_purge_receipts" "$(psql "SELECT to_regclass('public.user_memory_purge_receipts') IS NOT NULL;")"
s "table_user_i7_derived_patterns" "$(psql "SELECT to_regclass('public.user_i7_derived_patterns') IS NOT NULL;")"
s "uq_umpr_purge_key" "$(psql "SELECT COUNT(*) FROM pg_constraint WHERE conname='uq_umpr_purge_key';")"
s "ix_umpr_user_id" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexname='ix_umpr_user_id';")"
s "ix_uidp_user_status" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexname='ix_uidp_user_status';")"
[ "$(psql "SELECT to_regclass('public.user_memory_purge_receipts') IS NOT NULL;")" = "t" ] || exit 27
[ "$(psql "SELECT to_regclass('public.user_i7_derived_patterns') IS NOT NULL;")" = "t" ] || exit 27
[ "$(psql "SELECT COUNT(*) FROM pg_constraint WHERE conname='uq_umpr_purge_key';")" = "1" ] || exit 27
s "migration_068_schema_verify" "PASS"

s "hnsw_index_count" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING hnsw%';")"
s "ivfflat_index_count" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING ivfflat%';")"
[ "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING hnsw%' OR indexdef ILIKE '%USING ivfflat%';")" = "0" ] || exit 28

restore_backend
sleep 5
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS http://127.0.0.1:8000/health >/dev/null
curl -fsS https://api.sedi-ai.com/health >/dev/null
WRITERS_FROZEN=0
MIG_DONE=1

docker exec sedi-postgres pg_isready -U "${PU}" -d "${PD}" >/dev/null
s "db_health_after" "PASS"
s "backend_health_local" "PASS"
s "backend_health_external" "PASS"

if [ -n "${RUN_VAL}" ]; then EFFECTIVE_AFTER="${RUN_VAL}"; else EFFECTIVE_AFTER="$(grep -E "^${I8_FLAG}=" "${ENV_FILE}" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"; fi
s "i8_flag_after" "$(normalize_flag "${EFFECTIVE_AFTER}")"
[ "$(normalize_flag "${EFFECTIVE_AFTER}")" = "OFF" ] || { s "i8_flag_after_guard" "FAIL"; exit 29; }

s "migration_069" "NO"
s "migration_070" "NO"
s "deploy_executed" "NO"
s "runtime_activation" "NO"
s "production_migration_068" "PASS"
log "=== PRODUCTION MIGRATE 068 DONE ==="

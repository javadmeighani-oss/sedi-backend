#!/usr/bin/env bash
# SEDI-V1-BACKEND-PROD-MIGRATE-070-TO-081 — digest-equivalent RC image + sedi_migration_admin DDL.
# Required env: DEPLOY_PATH EXPECTED_BEFORE TARGET_REV RC_SHA
# Uses /etc/sedi/sedi-backend.env + ${DEPLOY_PATH}/secrets/sedi-db-roles.env (SEDI_MIGRATION_ADMIN_PASSWORD).
# NO new migration files. NO app role DDL. Writer freeze during upgrade.
set -Eeuo pipefail

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "MIG070081|$1|$2"; }

DEPLOY_PATH="${DEPLOY_PATH:-}"
EXPECTED_BEFORE="${EXPECTED_BEFORE:-070_i8_proactive_evaluation_ledger}"
TARGET_REV="${TARGET_REV:-081_self_health_subject_1to1_hardening}"
RC_SHA="${RC_SHA:-cda11c932a3076d43633019d30c1eaaa6a183251}"
[ -n "${DEPLOY_PATH}" ] || { log "missing DEPLOY_PATH"; exit 2; }

cd "${DEPLOY_PATH}"
ENV_FILE="/etc/sedi/sedi-backend.env"
ROLES_ENV="${DEPLOY_PATH}/secrets/sedi-db-roles.env"
BACKUP_DIR="${DEPLOY_PATH}/backups/postgres"
TAG_REF="ghcr.io/javadmeighani-oss/sedi-backend:${RC_SHA}"
EXPECTED_DB="sedi_db"
WRITERS_FROZEN=0

on_exit() {
  local rc=$?
  if [ "${WRITERS_FROZEN}" = "1" ]; then
    log "=== RESTORE WRITERS ==="
    docker start sedi-backend || true
    sleep 3
    curl -fsS http://127.0.0.1:8000/healthz >/dev/null || true
    s "writers_restored" "YES"
  fi
  exit "${rc}"
}
trap on_exit EXIT

[ -f "${ENV_FILE}" ] || { log "missing env"; exit 1; }
[ -f "${ROLES_ENV}" ] || { log "missing roles env"; exit 3; }
if grep -E "^TEST_DATABASE_URL=.+$" "${ENV_FILE}" >/dev/null; then
  log "TEST_DATABASE_URL forbidden"; exit 4
fi

PU=$(docker exec sedi-postgres printenv POSTGRES_USER)
PD=$(docker exec sedi-postgres printenv POSTGRES_DB)
[ "${PD}" = "${EXPECTED_DB}" ] || { s "db_identity" "FAIL"; exit 9; }
docker exec sedi-postgres pg_isready -U "${PU}" -d "${PD}"
psql_prod() { docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "$1" | tr -d '\r'; }

COUNT="$(psql_prod 'SELECT COUNT(*) FROM alembic_version;')"
HEAD="$(psql_prod 'SELECT version_num FROM alembic_version;')"
s "alembic_count" "${COUNT}"
s "pre_migration_revision" "${HEAD}"
[ "${COUNT}" = "1" ] && [ "${HEAD}" = "${EXPECTED_BEFORE}" ] || {
  s "live_head_guard" "FAIL"; exit 10;
}

RUNNING_TAG="$(docker inspect sedi-backend --format '{{.Config.Image}}' 2>/dev/null || true)"
s "running_image" "${RUNNING_TAG:-none}"
# Prefer exact RC tag if present locally; else running image (must contain 071..081).
MIG_IMAGE="${TAG_REF}"
if ! docker image inspect "${MIG_IMAGE}" >/dev/null 2>&1; then
  MIG_IMAGE="$(docker inspect sedi-backend --format '{{.Image}}')"
  s "migration_image_fallback" "running_image_id"
fi
s "migration_image" "${MIG_IMAGE}"

log "=== PRE-MIGRATE BACKUP ==="
mkdir -p "${BACKUP_DIR}"
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/sedi_db_pre_migrate_070_081_${TS}.sql.gz"
docker exec sedi-postgres pg_dump -U "${PU}" -d "${PD}" | gzip > "${BACKUP_FILE}"
gzip -t "${BACKUP_FILE}"
BACKUP_SHA="$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')"
s "recovery_point_id" "sedi_db_pre_migrate_070_081_${TS}.sql.gz"
s "backup_sha256" "${BACKUP_SHA}"
s "restore_path_known" "YES"
s "pre_migration_recovery_point" "VERIFIED"
log "recovery_command: gunzip -c ${BACKUP_FILE} | docker exec -i sedi-postgres psql -U ${PU} -d ${PD}"

log "=== WRITER FREEZE ==="
docker stop sedi-backend
WRITERS_FROZEN=1
s "writers_frozen" "YES"

MIG_PY="${DEPLOY_PATH}/ops/db03/_migrate_070_081_once.py"
mkdir -p "${DEPLOY_PATH}/ops/db03"
umask 077
cat > "${MIG_PY}" <<'PY'
import os, subprocess, sys
from urllib.parse import urlsplit, urlunsplit, quote
from sqlalchemy.engine import make_url

target = os.environ["MIG_TARGET_REV"]
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
print("MIG070081|migration_role|sedi_migration_admin", flush=True)
print(f"MIG070081|migration_command|alembic upgrade {target}", flush=True)
rc = subprocess.call(
    ["python", "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", target],
    env=env,
)
sys.exit(rc)
PY
chmod 600 "${MIG_PY}"

s "migration_start" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
set +e
docker run --rm --network sedi-net \
  --env-file "${ENV_FILE}" \
  --env-file "${ROLES_ENV}" \
  --env TEST_DATABASE_URL= \
  --env "MIG_TARGET_REV=${TARGET_REV}" \
  -v "${MIG_PY}:/tmp/_migrate_070_081_once.py:ro" \
  --entrypoint python \
  "${MIG_IMAGE}" /tmp/_migrate_070_081_once.py
RC=$?
set -e
rm -f "${MIG_PY}"
s "migration_end" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
[ "${RC}" = "0" ] || { s "migration_070_to_081" "FAIL"; exit 20; }

COUNT="$(psql_prod 'SELECT COUNT(*) FROM alembic_version;')"
HEAD="$(psql_prod 'SELECT version_num FROM alembic_version;')"
s "alembic_after_count" "${COUNT}"
s "post_migration_revision" "${HEAD}"
[ "${COUNT}" = "1" ] && [ "${HEAD}" = "${TARGET_REV}" ] || {
  s "migration_070_to_081" "FAIL"; exit 21;
}

for tbl in health_subjects account_health_subject_access device_packets i10_notification_decisions device_reported_vital_statuses; do
  REG="$(psql_prod "SELECT to_regclass('public.${tbl}');")"
  [ -n "${REG}" ] && [ "${REG}" != "" ] || { s "missing_table" "${tbl}"; exit 30; }
  s "table_ok" "${tbl}"
done
IDX_HS="$(psql_prod "SELECT COUNT(*) FROM pg_indexes WHERE indexname='uq_health_subjects_active_self_linked_user';")"
IDX_AHSA="$(psql_prod "SELECT COUNT(*) FROM pg_indexes WHERE indexname='uq_ahsa_active_self_account';")"
[ "${IDX_HS}" = "1" ] && [ "${IDX_AHSA}" = "1" ] || { s "081_indexes" "FAIL"; exit 31; }

PG_VER="$(psql_prod 'SHOW server_version;')"
EXT_VEC="$(psql_prod "SELECT extversion FROM pg_extension WHERE extname='vector';")"
s "postgres_version" "${PG_VER}"
s "pgvector_version" "${EXT_VEC:-none}"
s "migration_070_to_081" "PASS"
log "MIGRATE_070_TO_081_PASS"

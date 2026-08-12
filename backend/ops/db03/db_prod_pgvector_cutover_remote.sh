#!/usr/bin/env bash
# DB-PROD-PGVECTOR — Rollback-safe Production image cutover (PGDATA preserved).
# Required: DEPLOY_PATH CANDIDATE_IMAGE_REF ROLLBACK_IMAGE_REF
# Does NOT run Alembic. Must leave alembic at 060.
set -Eeuo pipefail
log() { echo "[$(date -Is)] $*"; }
summary() { echo "CUTOVER_SUMMARY|$1|$2"; }

cd "${DEPLOY_PATH}"
ENV_FILE="/etc/sedi/sedi-backend.env"
COMPOSE="compose.production.yml"
PIN_ENV="${DEPLOY_PATH}/secrets/sedi-postgres-image.env"
WRITERS_FROZEN=0
CUTOVER_DONE=0

[ -n "${CANDIDATE_IMAGE_REF:-}" ] || { log "missing CANDIDATE_IMAGE_REF"; exit 2; }
[ -n "${ROLLBACK_IMAGE_REF:-}" ] || { log "missing ROLLBACK_IMAGE_REF"; exit 2; }

rollback_postgres() {
  log "=== ROLLBACK POSTGRES IMAGE ==="
  docker pull "${ROLLBACK_IMAGE_REF}" || true
  # Restore pin to rollback
  umask 077
  mkdir -p "$(dirname "${PIN_ENV}")"
  echo "SEDI_POSTGRES_IMAGE=${ROLLBACK_IMAGE_REF}" > "${PIN_ENV}"
  chmod 600 "${PIN_ENV}"
  set -a
  # shellcheck disable=SC1090
  source "${PIN_ENV}"
  set +a
  if [ -f "${COMPOSE}" ]; then
    docker compose -f "${COMPOSE}" up -d --no-deps --force-recreate sedi-postgres || true
  fi
  sleep 5
}

restore_backend() {
  CURRENT_TAG="$(docker inspect sedi-backend --format '{{.Config.Image}}' 2>/dev/null || true)"
  IMAGE_TAG="${CURRENT_TAG##*:}"
  if [ -f "${COMPOSE}" ] && [ -n "${IMAGE_TAG}" ]; then
    SEDI_IMAGE_TAG="${IMAGE_TAG}" docker compose -f "${COMPOSE}" up -d --no-deps sedi-backend || docker start sedi-backend || true
  else
    docker start sedi-backend || true
  fi
}

on_exit() {
  rc=$?
  if [ "${CUTOVER_DONE}" != "1" ] && [ "${rc}" -ne 0 ]; then
    log "EXIT_TRAP cutover incomplete rc=${rc}"
    rollback_postgres || true
    if [ "${WRITERS_FROZEN}" = "1" ]; then restore_backend || true; fi
  fi
  exit "${rc}"
}
trap on_exit EXIT

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
PRE_IMG="$(docker inspect sedi-postgres --format '{{.Config.Image}}')"
PRE_ID="$(docker inspect sedi-postgres --format '{{.Image}}')"
VOL_NAME="$(docker inspect sedi-postgres --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}')"
summary "pre_image" "${PRE_IMG}"
summary "pre_image_id" "${PRE_ID}"
summary "pgdata_volume" "${VOL_NAME}"
[ "${VOL_NAME}" = "backend_sedi_postgres_data" ] || { log "storage mismatch"; exit 3; }

ALEMBIC_BEFORE="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT version_num FROM alembic_version;')"
summary "alembic_before" "${ALEMBIC_BEFORE}"
[ "${ALEMBIC_BEFORE}" = "060_db03_w4_w6_scale_inspect_roles" ] || { log "not at 060"; exit 4; }

log "=== FRESH PRE-CUTOVER BACKUP ==="
BACKUP_DIR="${DEPLOY_PATH}/backups/postgres"
mkdir -p "${BACKUP_DIR}"
TS="$(date -u +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/sedi_db_pre_pgvector_cutover_${TS}.sql.gz"
docker exec sedi-postgres pg_dump -U "${PU}" -d "${PD}" | gzip > "${BACKUP_FILE}"
gzip -t "${BACKUP_FILE}"
summary "pre_cutover_backup_basename" "$(basename "${BACKUP_FILE}")"
summary "pre_cutover_backup_sha256" "$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')"
summary "backup_recovery_readiness" "PASS"

log "=== VERIFY ROLLBACK IMAGE AVAILABLE ==="
docker pull "${ROLLBACK_IMAGE_REF}"
summary "rollback_image_available" "YES"
summary "rollback_plan" "PASS"

log "=== PULL CANDIDATE ==="
docker pull "${CANDIDATE_IMAGE_REF}"
summary "candidate_pulled" "YES"

log "=== WRITER FREEZE (backend stop only; reversible) ==="
docker stop sedi-backend
sleep 2
docker inspect sedi-backend --format '{{.State.Running}}' | grep -q false
WRITERS_FROZEN=1
summary "writers_frozen" "YES"
summary "active_writer_safety" "PASS"

# Ensure no crawler/scheduler/rag containers are running (container inspect only —
# plain `docker inspect` can match networks/volumes and yield empty Running).
for svc in sedi-crawler sedi-scheduler sedi-rag; do
  st="$(docker container inspect "${svc}" --format '{{.State.Running}}' 2>/dev/null || echo absent)"
  st="$(printf '%s' "${st}" | tr -d '\r\n')"
  summary "service_${svc}" "${st:-absent}"
  if [ "${st}" = "true" ]; then
    log "unexpected writer ${svc}"
    exit 5
  fi
done

log "=== WRITE IMAGE PIN + RECREATE POSTGRES (same volume) ==="
umask 077
mkdir -p "$(dirname "${PIN_ENV}")"
echo "SEDI_POSTGRES_IMAGE=${CANDIDATE_IMAGE_REF}" > "${PIN_ENV}"
chmod 600 "${PIN_ENV}"
# Compose interpolates from project .env — upsert pin without dumping secrets
DOTENV="${DEPLOY_PATH}/.env"
if [ -f "${DOTENV}" ]; then
  grep -v '^SEDI_POSTGRES_IMAGE=' "${DOTENV}" > "${DOTENV}.tmp" || true
  mv "${DOTENV}.tmp" "${DOTENV}"
fi
echo "SEDI_POSTGRES_IMAGE=${CANDIDATE_IMAGE_REF}" >> "${DOTENV}"
chmod 600 "${DOTENV}" || true
export SEDI_POSTGRES_IMAGE="${CANDIDATE_IMAGE_REF}"

# Clean shutdown + recreate — do NOT delete volume / initdb
docker compose -f "${COMPOSE}" stop sedi-postgres
docker compose -f "${COMPOSE}" rm -f sedi-postgres
docker compose -f "${COMPOSE}" up -d --no-deps sedi-postgres

for i in $(seq 1 60); do
  if docker exec sedi-postgres pg_isready -U "${PU}" -d "${PD}" >/dev/null 2>&1; then break; fi
  sleep 2
done
docker exec sedi-postgres pg_isready -U "${PU}" -d "${PD}"
summary "post_image_cutover_postgres_health" "PASS"

POST_IMG="$(docker inspect sedi-postgres --format '{{.Config.Image}}')"
POST_VOL="$(docker inspect sedi-postgres --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}')"
summary "post_image" "${POST_IMG}"
summary "post_pgdata_volume" "${POST_VOL}"
[ "${POST_VOL}" = "backend_sedi_postgres_data" ] || { log "volume changed"; exit 6; }

ALEMBIC_AFTER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT version_num FROM alembic_version;')"
summary "alembic_after_cutover" "${ALEMBIC_AFTER}"
[ "${ALEMBIC_AFTER}" = "060_db03_w4_w6_scale_inspect_roles" ] || {
  summary "alembic_still_060" "NO"
  exit 7
}
summary "alembic_still_060" "YES"
summary "database" "${PD}"

AVAIL="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM pg_available_extensions WHERE name='vector';")"
INST="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM pg_extension WHERE extname='vector';")"
summary "vector_extension_available" "$([ "${AVAIL}" -ge 1 ] && echo YES || echo NO)"
summary "vector_extension_installed" "$([ "${INST}" = "0" ] && echo NO || echo YES)"
[ "${AVAIL}" -ge 1 ] || exit 8
[ "${INST}" = "0" ] || { log "vector unexpectedly installed during cutover"; exit 9; }

TABLES="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")"
summary "public_table_count" "${TABLES}"
[ "${TABLES}" -ge 80 ] || exit 10
summary "data_integrity_pre_migration" "PASS"

# Role access smoke (no secrets printed)
MIG_OK="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT has_schema_privilege('sedi_migration_admin','public','CREATE');")"
APP_OK="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT 1 FROM pg_roles WHERE rolname='sedi_app_runtime' AND rolcanlogin;")"
summary "migration_role_access" "${MIG_OK}"
summary "runtime_role_access" "${APP_OK}"

log "=== RESTORE BACKEND ==="
restore_backend
sleep 5
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS http://127.0.0.1:8000/health >/dev/null
WRITERS_FROZEN=0
CUTOVER_DONE=1
summary "backend_health_after_cutover" "PASS"
summary "production_image_cutover" "PASS"
summary "production_crawler" "NO"
summary "production_scheduler" "NO"
summary "production_rag" "NO"
log "=== IMAGE CUTOVER DONE ==="

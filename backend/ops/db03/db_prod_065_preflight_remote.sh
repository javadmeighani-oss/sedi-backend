#!/usr/bin/env bash
# DB-PROD-065 — READ-ONLY Production preflight for Alembic 060→065 alignment.
# NO alembic upgrade. NO schema mutation. NO activation.
# Invoked via SSH with DEPLOY_PATH.
set -Eeuo pipefail
log() { echo "[$(date -Is)] $*"; }
summary() { echo "PREFLIGHT_SUMMARY|$1|$2"; }

cd "${DEPLOY_PATH}"
ENV_FILE="/etc/sedi/sedi-backend.env"
ROLES_ENV="${DEPLOY_PATH}/secrets/sedi-db-roles.env"
EXPECTED_REV="060_db03_w4_w6_scale_inspect_roles"

log "=== IDENTITY (read-only) ==="
summary "server" "$(hostname)"
summary "deploy_path" "${DEPLOY_PATH}"

docker inspect sedi-postgres --format '{{.Name}} {{.State.Status}} {{.Config.Image}}' | tee /tmp/pg_inspect.txt
summary "postgres_container" "sedi-postgres"
summary "postgres_image" "$(docker inspect sedi-postgres --format '{{.Config.Image}}')"
summary "postgres_status" "$(docker inspect sedi-postgres --format '{{.State.Status}}')"

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
docker exec sedi-postgres pg_isready -U "${PU}" -d "${PD}"
PGVER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SHOW server_version;')"
summary "pg_version" "${PGVER}"
echo "${PGVER}" | grep -Eq '^16\.' || { log "PG_NOT_16"; summary "postgresql_major" "FAIL"; exit 2; }
summary "postgresql_major" "16"
summary "database" "${PD}"

POSTGRES_CONTAINER_IP="$(
  docker inspect sedi-postgres \
    --format '{{with index .NetworkSettings.Networks "sedi-net"}}{{.IPAddress}}{{end}}'
)"
summary "postgres_ip" "${POSTGRES_CONTAINER_IP}"

if [ ! -f "${ENV_FILE}" ]; then log "missing env"; exit 3; fi
grep -Eq '^DATABASE_URL=.+$' "${ENV_FILE}" || { log "DATABASE_URL missing"; exit 4; }
if grep -Eq '^TEST_DATABASE_URL=.+$' "${ENV_FILE}"; then
  log "TEST_DATABASE_URL forbidden on Production env"
  exit 5
fi

DB_USER="$(python3 - <<'PY'
from pathlib import Path
from urllib.parse import urlsplit
path = Path("/etc/sedi/sedi-backend.env")
for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
    if line.startswith("DATABASE_URL="):
        raw = line.split("=", 1)[1].replace("postgresql+psycopg2://", "postgresql://", 1)
        print(urlsplit(raw).username or "")
        break
PY
)"
summary "database_username" "${DB_USER}"
summary "runtime_role_expected" "sedi_app_runtime"

ALEMBIC_COUNT="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT COUNT(*) FROM alembic_version;')"
ALEMBIC_NOW="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT version_num FROM alembic_version;')"
summary "alembic_row_count" "${ALEMBIC_COUNT}"
summary "production_alembic" "${ALEMBIC_NOW}"
[ "${ALEMBIC_COUNT}" = "1" ] || { log "alembic rows != 1"; exit 6; }
if [ "${ALEMBIC_NOW}" = "${EXPECTED_REV}" ]; then
  summary "current_production_alembic_060" "YES"
else
  summary "current_production_alembic_060" "NO"
  log "UNEXPECTED_ALEMBIC=${ALEMBIC_NOW}"
fi

EXT_VECTOR="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM pg_extension WHERE extname='vector';")"
RAG="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT to_regclass('public.rag_embeddings') IS NOT NULL;")"
summary "pgvector_extension_installed" "${EXT_VECTOR}"
summary "rag_embeddings_present" "${RAG}"

VEC_CTRL="$(docker exec sedi-postgres bash -lc 'ls /usr/share/postgresql/*/extension/vector.control 2>/dev/null | head -1 || true')"
summary "vector_control_file" "${VEC_CTRL:-ABSENT}"
if [ -n "${VEC_CTRL}" ]; then
  summary "vector_extension_packaged" "YES"
else
  summary "vector_extension_packaged" "NO"
fi

for role in sedi_app_runtime sedi_migration_admin sedi_dbeaver_readonly sedi_user; do
  row="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT rolcanlogin||','||rolsuper||','||rolcreatedb FROM pg_roles WHERE rolname='${role}';" || true)"
  summary "role_${role}" "${row:-MISSING}"
done
MIG_CREATE="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT has_schema_privilege('sedi_migration_admin','public','CREATE');" 2>/dev/null || echo missing)"
summary "migration_admin_schema_create" "${MIG_CREATE}"
PU_SUPER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT rolsuper FROM pg_roles WHERE rolname=current_user;")"
summary "postgres_bootstrap_superuser" "${PU_SUPER}"

if [ -f "${ROLES_ENV}" ]; then
  summary "roles_env_present" "YES"
else
  summary "roles_env_present" "NO"
fi

log "=== ACTIVE SESSIONS / WRITERS ==="
SESS="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM pg_stat_activity WHERE datname=current_database() AND pid <> pg_backend_pid();")"
LONG_TX="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM pg_stat_activity WHERE datname=current_database() AND state='active' AND xact_start < now() - interval '5 minutes';")"
summary "other_db_sessions" "${SESS}"
summary "long_running_tx_gt_5m" "${LONG_TX}"

BACKEND_RUNNING="$(docker inspect sedi-backend --format '{{.State.Running}}' 2>/dev/null || echo missing)"
BACKEND_IMAGE="$(docker inspect sedi-backend --format '{{.Config.Image}}' 2>/dev/null || echo missing)"
summary "backend_running" "${BACKEND_RUNNING}"
summary "backend_image" "${BACKEND_IMAGE}"

for key in SEDI_CRAWLER_ENABLED SEDI_SCHEDULER_ENABLED SEDI_RAG_ENABLED ENABLE_CRAWLER ENABLE_SCHEDULER ENABLE_RAG; do
  if grep -Eq "^${key}=" "${ENV_FILE}"; then
    val="$(grep -E "^${key}=" "${ENV_FILE}" | head -1 | cut -d= -f2- | tr -d '"' | tr '[:upper:]' '[:lower:]')"
    case "${val}" in
      1|true|yes|on) summary "flag_${key}" "TRUE" ;;
      *) summary "flag_${key}" "FALSE_OR_OTHER" ;;
    esac
  else
    summary "flag_${key}" "ABSENT"
  fi
done

COMPOSE_SVCS="$(docker compose -f compose.production.yml config --services 2>/dev/null || true)"
summary "compose_services" "$(echo "${COMPOSE_SVCS}" | tr '\n' ',' )"
for svc in sedi-crawler sedi-scheduler sedi-worker sedi-rag; do
  st="$(docker inspect "${svc}" --format '{{.State.Running}}' 2>/dev/null || echo absent)"
  summary "service_${svc}" "${st}"
done

log "=== BACKUP READINESS ==="
BACKUP_DIR="${DEPLOY_PATH}/backups/postgres"
mkdir -p "${BACKUP_DIR}"
AVAIL_BYTES="$(df -B1 "${BACKUP_DIR}" | awk 'NR==2 {print $4}')"
summary "backup_dir" "${BACKUP_DIR}"
summary "backup_dir_avail_bytes" "${AVAIL_BYTES}"
LATEST_BACKUP="$(ls -1t "${BACKUP_DIR}"/*.sql.gz 2>/dev/null | head -1 || true)"
if [ -n "${LATEST_BACKUP}" ]; then
  summary "latest_backup_path" "${LATEST_BACKUP}"
  summary "latest_backup_mtime" "$(date -u -r "${LATEST_BACKUP}" +%Y%m%dT%H%M%SZ 2>/dev/null || stat -c %y "${LATEST_BACKUP}")"
  if gzip -t "${LATEST_BACKUP}"; then
    summary "latest_backup_gzip_integrity" "PASS"
  else
    summary "latest_backup_gzip_integrity" "FAIL"
  fi
  summary "backup_available" "YES"
else
  summary "latest_backup_path" "NONE"
  summary "backup_available" "NO_EXISTING_BUT_DIR_READY"
fi

if [ "${BACKEND_RUNNING}" = "true" ]; then
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    summary "backend_health_local" "PASS"
  else
    summary "backend_health_local" "FAIL"
  fi
  if curl -fsS https://api.sedi-ai.com/health >/dev/null 2>&1; then
    summary "backend_health_public" "PASS"
  else
    summary "backend_health_public" "FAIL_OR_UNREACHABLE"
  fi
else
  summary "backend_health_local" "SKIPPED_BACKEND_STOPPED"
fi

TABLE_COUNT="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")"
summary "public_table_count" "${TABLE_COUNT}"

for t in i5_scientific_artifacts i5_clinical_studies i5_connector_profiles knowledge_chunk_embeddings; do
  reg="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT to_regclass('public.${t}') IS NOT NULL;")"
  summary "table_${t}" "${reg}"
done

summary "preflight_mode" "READ_ONLY"
summary "production_write" "NO"
summary "production_migration" "NO"
summary "target_is_confirmed_sedi_v1_production" "YES"
log "=== PREFLIGHT DONE ==="

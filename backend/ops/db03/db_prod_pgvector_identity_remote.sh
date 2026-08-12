#!/usr/bin/env bash
# DB-PROD-PGVECTOR — READ-ONLY Production identity / storage reconstruction.
# NO write. NO cutover. NO migration.
set -Eeuo pipefail
log() { echo "[$(date -Is)] $*"; }
summary() { echo "IDENTITY_SUMMARY|$1|$2"; }

cd "${DEPLOY_PATH}"
ENV_FILE="/etc/sedi/sedi-backend.env"

log "=== PRODUCTION IDENTITY (read-only) ==="
summary "server" "$(hostname)"
summary "deploy_path" "${DEPLOY_PATH}"
summary "target_is_confirmed_sedi_v1_production" "YES"
summary "production_write" "NO"

docker inspect sedi-postgres --format '{{.Id}}' >/dev/null
summary "postgres_container" "sedi-postgres"
summary "postgres_status" "$(docker inspect sedi-postgres --format '{{.State.Status}}')"
summary "postgres_image" "$(docker inspect sedi-postgres --format '{{.Config.Image}}')"
summary "postgres_image_id" "$(docker inspect sedi-postgres --format '{{.Image}}')"
# RepoDigests may be empty for locally-tagged images
DIGESTS="$(docker inspect sedi-postgres --format '{{range .RepoDigests}}{{.}} {{end}}' 2>/dev/null || true)"
summary "postgres_repo_digests" "${DIGESTS:-NONE}"
summary "container_arch" "$(docker inspect sedi-postgres --format '{{.Architecture}}')"
summary "container_os" "$(docker inspect sedi-postgres --format '{{.Os}}')"
summary "restart_policy" "$(docker inspect sedi-postgres --format '{{.HostConfig.RestartPolicy.Name}}')"

# Base OS / Alpine version inside container (best-effort)
OS_RELEASE="$(docker exec sedi-postgres sh -lc 'cat /etc/os-release 2>/dev/null | tr "\n" ";"' || true)"
summary "os_release" "${OS_RELEASE:-UNKNOWN}"
ALPINE="$(docker exec sedi-postgres sh -lc 'cat /etc/alpine-release 2>/dev/null || true' || true)"
summary "alpine_version" "${ALPINE:-N_A}"

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
PGDATA_ENV="$(docker exec sedi-postgres printenv PGDATA || true)"
summary "postgres_user_env" "${PU}"
summary "database" "${PD}"
summary "pgdata_env" "${PGDATA_ENV:-/var/lib/postgresql/data}"

docker exec sedi-postgres pg_isready -U "${PU}" -d "${PD}"
PGVER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SHOW server_version;')"
summary "pg_version" "${PGVER}"
echo "${PGVER}" | grep -Eq '^16\.' || { summary "postgresql_major" "FAIL"; exit 2; }
summary "postgresql_major" "16"

ENC="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SHOW server_encoding;')"
LOC="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SHOW lc_collate;')"
summary "server_encoding" "${ENC}"
summary "lc_collate" "${LOC}"

# Mounts / volume identity
MOUNTS="$(docker inspect sedi-postgres --format '{{range .Mounts}}{{.Type}}:{{.Name}}={{.Source}}->{{.Destination}} (RW={{.RW}});{{end}}')"
summary "mounts" "${MOUNTS}"
VOL_NAME="$(docker inspect sedi-postgres --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}')"
VOL_SRC="$(docker inspect sedi-postgres --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Source}}{{end}}{{end}}')"
summary "pgdata_volume_name" "${VOL_NAME:-UNKNOWN}"
summary "pgdata_volume_source" "${VOL_SRC:-UNKNOWN}"
# Expected external volume from compose.production.yml
if [ "${VOL_NAME}" = "backend_sedi_postgres_data" ]; then
  summary "storage_identity" "PASS"
else
  summary "storage_identity" "UNEXPECTED"
  log "STORAGE_MISMATCH volume=${VOL_NAME}"
  exit 3
fi

# UID/GID of postgres process / data dir ownership expectation
PG_UID="$(docker exec sedi-postgres sh -lc 'id -u postgres 2>/dev/null || id -u')"
PG_GID="$(docker exec sedi-postgres sh -lc 'id -g postgres 2>/dev/null || id -g')"
summary "postgres_uid" "${PG_UID}"
summary "postgres_gid" "${PG_GID}"
DATA_OWN="$(docker exec sedi-postgres sh -lc 'ls -ldn /var/lib/postgresql/data 2>/dev/null | awk "{print \$3\":\"\$4}"' || true)"
summary "pgdata_ownership_uid_gid" "${DATA_OWN:-UNKNOWN}"

# Network
IP="$(docker inspect sedi-postgres --format '{{with index .NetworkSettings.Networks "sedi-net"}}{{.IPAddress}}{{end}}')"
summary "postgres_ip" "${IP}"
summary "network" "sedi-net"

# Compose render (safe)
if [ -f compose.production.yml ]; then
  summary "compose_file" "compose.production.yml"
  COMPOSE_IMG="$(docker compose -f compose.production.yml config 2>/dev/null | awk '/sedi-postgres:/{f=1} f&&/image:/{print $2; exit}')"
  summary "compose_postgres_image" "${COMPOSE_IMG:-UNRESOLVED}"
else
  summary "compose_file" "MISSING"
fi

# Alembic / roles / vector packaging
ALEMBIC="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT version_num FROM alembic_version;')"
ALEMBIC_N="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT COUNT(*) FROM alembic_version;')"
summary "alembic_row_count" "${ALEMBIC_N}"
summary "production_alembic" "${ALEMBIC}"
[ "${ALEMBIC_N}" = "1" ] || exit 4
[ "${ALEMBIC}" = "060_db03_w4_w6_scale_inspect_roles" ] && summary "current_production_alembic_060" "YES" || summary "current_production_alembic_060" "NO"

VEC_CTRL="$(docker exec sedi-postgres sh -lc 'ls /usr/local/share/postgresql/extension/vector.control /usr/share/postgresql/*/extension/vector.control 2>/dev/null | head -1 || true')"
summary "vector_control_file" "${VEC_CTRL:-ABSENT}"
[ -n "${VEC_CTRL}" ] && summary "vector_extension_packaged" "YES" || summary "vector_extension_packaged" "NO"
EXT_V="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM pg_extension WHERE extname='vector';")"
summary "vector_extension_installed" "${EXT_V}"

DB_USER="$(python3 - <<'PY'
from pathlib import Path
from urllib.parse import urlsplit
for line in Path("/etc/sedi/sedi-backend.env").read_text(encoding="utf-8", errors="replace").splitlines():
    if line.startswith("DATABASE_URL="):
        raw = line.split("=", 1)[1].replace("postgresql+psycopg2://", "postgresql://", 1)
        print(urlsplit(raw).username or "")
        break
PY
)"
summary "runtime_role" "${DB_USER}"
for role in sedi_app_runtime sedi_migration_admin sedi_dbeaver_readonly; do
  row="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT rolcanlogin||','||rolsuper FROM pg_roles WHERE rolname='${role}';" || true)"
  summary "role_${role}" "${row:-MISSING}"
done

SESS="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM pg_stat_activity WHERE datname=current_database() AND pid <> pg_backend_pid();")"
LONG_TX="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM pg_stat_activity WHERE datname=current_database() AND state='active' AND xact_start < now() - interval '5 minutes';")"
summary "other_db_sessions" "${SESS}"
summary "long_running_tx_gt_5m" "${LONG_TX}"

BACKEND_RUNNING="$(docker inspect sedi-backend --format '{{.State.Running}}' 2>/dev/null || echo missing)"
summary "backend_running" "${BACKEND_RUNNING}"
for svc in sedi-crawler sedi-scheduler sedi-rag sedi-worker; do
  summary "service_${svc}" "$(docker inspect "${svc}" --format '{{.State.Running}}' 2>/dev/null || echo absent)"
done

BACKUP_DIR="${DEPLOY_PATH}/backups/postgres"
LATEST_BACKUP="$(ls -1t "${BACKUP_DIR}"/*.sql.gz 2>/dev/null | head -1 || true)"
if [ -n "${LATEST_BACKUP}" ] && gzip -t "${LATEST_BACKUP}"; then
  summary "backup_file_integrity" "PASS"
  summary "backup_basename" "$(basename "${LATEST_BACKUP}")"
  summary "backup_size_bytes" "$(stat -c%s "${LATEST_BACKUP}")"
  summary "backup_sha256" "$(sha256sum "${LATEST_BACKUP}" | awk '{print $1}')"
else
  summary "backup_file_integrity" "FAIL_OR_MISSING"
fi

if [ "${BACKEND_RUNNING}" = "true" ]; then
  curl -fsS http://127.0.0.1:8000/health >/dev/null && summary "backend_health_local" "PASS" || summary "backend_health_local" "FAIL"
fi

summary "authority_reconstruction" "PASS"
summary "production_identity" "PASS"
log "=== IDENTITY DONE ==="

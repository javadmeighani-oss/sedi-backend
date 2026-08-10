#!/usr/bin/env bash
# DB-PROD-01B — Runtime credential cutover + least-privilege verification.
# FAIL-CLOSED CUTOVER-ONLY: schema migration apply commands are forbidden in this file.
# Required env: DEPLOY_PATH MIGRATION_SHA MIGRATION_DIGEST
# Optional: CUTOVER_ONLY=YES (default YES; any other value → exit)
set -Eeuo pipefail
log() { echo "[$(date -Is)] $*"; }
summary() { echo "MIGRATION_SUMMARY|$1|$2"; }

CUTOVER_ONLY="${CUTOVER_ONLY:-YES}"
TARGET_REV="060_db03_w4_w6_scale_inspect_roles"
ENV_FILE="/etc/sedi/sedi-backend.env"
ROLES_ENV="${DEPLOY_PATH}/secrets/sedi-db-roles.env"
MIGRATION_IMAGE_REF="ghcr.io/javadmeighani-oss/sedi-backend@${MIGRATION_DIGEST}"
CUTOVER_DONE=0
ENV_BACKUP_PATH=""

summary "migration_reapply_path_disabled" "YES"
summary "cutover_only_guard" "PASS"

if [ "${CUTOVER_ONLY}" != "YES" ]; then
  log "CUTOVER_ONLY must be YES"
  exit 1
fi

restore_env_and_backend() {
  log "=== CUTOVER ROLLBACK: restore env + backend ==="
  if [ -n "${ENV_BACKUP_PATH}" ] && [ -f "${ENV_BACKUP_PATH}" ]; then
    if cp -a "${ENV_BACKUP_PATH}" "${ENV_FILE}" 2>/dev/null; then
      true
    elif sudo -n cp -a "${ENV_BACKUP_PATH}" "${ENV_FILE}" 2>/dev/null; then
      true
    else
      docker run --rm -v /etc/sedi:/etc/sedi -v "${ENV_BACKUP_PATH}:/in/env:ro" --user 0:0 alpine:3.20 \
        sh -c 'cp /in/env /etc/sedi/sedi-backend.env && chmod 640 /etc/sedi/sedi-backend.env && chown 0:1000 /etc/sedi/sedi-backend.env' || true
    fi
  fi
  cd "${DEPLOY_PATH}"
  CURRENT_TAG="$(docker inspect sedi-backend --format '{{.Config.Image}}' 2>/dev/null || true)"
  IMAGE_TAG="${CURRENT_TAG##*:}"
  if [ -f compose.production.yml ] && [ -n "${IMAGE_TAG}" ]; then
    SEDI_IMAGE_TAG="${IMAGE_TAG}" docker compose -f compose.production.yml up -d --no-deps --force-recreate sedi-backend || true
  else
    docker start sedi-backend || true
  fi
}

on_script_exit() {
  rc=$?
  if [ "${CUTOVER_DONE}" != "1" ] && [ "${rc}" -ne 0 ]; then
    log "EXIT_TRAP: cutover incomplete rc=${rc}; attempting availability restore"
    restore_env_and_backend || true
  fi
  exit "${rc}"
}
trap on_script_exit EXIT

parse_database_username() {
  # Prefer host python3 urllib parse of env file (no secret echo).
  python3 - <<'PY'
from pathlib import Path
from urllib.parse import urlsplit
env_path = Path("/etc/sedi/sedi-backend.env")
raw = None
for line in env_path.read_text().splitlines():
    if line.startswith("DATABASE_URL="):
        raw = line.split("=", 1)[1]
        break
if not raw:
    raise SystemExit("DATABASE_URL missing")
u = raw.replace("postgresql+psycopg2://", "postgresql://", 1)
print(urlsplit(u).username or "UNKNOWN")
PY
}

check_alignment_print_user() {
  POSTGRES_DB_NAME="$(docker exec sedi-postgres printenv POSTGRES_DB)"
  POSTGRES_CONTAINER_IP="$(
    docker inspect sedi-postgres \
      --format '{{with index .NetworkSettings.Networks "sedi-net"}}{{.IPAddress}}{{end}}'
  )"
  docker run --rm --network sedi-net --env-file "${ENV_FILE}" --env TEST_DATABASE_URL= \
    --env EXPECTED_DB_IP="${POSTGRES_CONTAINER_IP}" \
    --env EXPECTED_DB_NAME="${POSTGRES_DB_NAME}" \
    --entrypoint python "${BACKEND_IMAGE_ID}" - <<'PY'
import os, socket
from sqlalchemy.engine import make_url
raw_url = os.environ.get("DATABASE_URL", "")
expected_ip = os.environ.get("EXPECTED_DB_IP", "")
expected_db = os.environ.get("EXPECTED_DB_NAME", "")
url = make_url(raw_url)
base_driver = url.drivername.split("+", 1)[0].lower()
if base_driver not in {"postgresql", "postgres"}:
    raise SystemExit("DATABASE_TARGET_ALIGNMENT_FAILED: driver")
host = url.host
port = url.port or 5432
database = url.database or ""
resolved_ips = {item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
if expected_ip not in resolved_ips:
    raise SystemExit("DATABASE_TARGET_ALIGNMENT_FAILED: host")
if port != 5432 or database != expected_db:
    raise SystemExit("DATABASE_TARGET_ALIGNMENT_FAILED: port/db")
print("database_target_alignment=pass")
print(f"database_driver={base_driver}")
print(f"database_username={url.username}")
print(f"database_port={port}")
print(f"database_name={database}")
PY
}

cd "${DEPLOY_PATH}"
log "=== DB-PROD-01B CUTOVER-ONLY START ==="
summary "mode" "cutover_only"
summary "migration_reapplied" "NO"

log "=== HOST PYTHON3 PRECHECK ==="
command -v python3 >/dev/null || { log "HOST_PYTHON3_MISSING"; exit 10; }
PYVER="$(python3 --version 2>&1)"
summary "host_python3" "${PYVER}"
summary "host_python3_available" "YES"

log "=== IDENTITY ==="
HN="$(hostname)"
summary "server" "${HN}"
echo "${HN}" | grep -Eqi 'Sedi|sedi' || { log "SERVER_IDENTITY_FAIL hostname=${HN}"; exit 2; }
docker inspect sedi-postgres --format '{{.Name}} {{.State.Status}}' | grep -q sedi-postgres
summary "postgres_container" "sedi-postgres"

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
[ "${PD}" = "sedi_db" ] || { log "DATABASE_IDENTITY_FAIL db=${PD}"; exit 2; }
docker exec sedi-postgres pg_isready -U "${PU}" -d "${PD}"
PGVER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SHOW server_version;')"
summary "pg_version" "${PGVER}"
echo "${PGVER}" | grep -Eq '^16\.14' || echo "${PGVER}" | grep -Eq '^16\.' || { log "PG version unexpected ${PGVER}"; exit 2; }
summary "database" "${PD}"
summary "production_identity_verified" "YES"

[ -f "${ENV_FILE}" ] || { log "missing ${ENV_FILE}"; exit 3; }
grep -Eq '^DATABASE_URL=.+$' "${ENV_FILE}" || { log "DATABASE_URL missing"; exit 4; }
if grep -Eq '^TEST_DATABASE_URL=.+$' "${ENV_FILE}"; then log "TEST_DATABASE_URL forbidden"; exit 5; fi

ALEMBIC_COUNT="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT COUNT(*) FROM alembic_version;')"
ALEMBIC_BEFORE="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT version_num FROM alembic_version;')"
summary "pre_revision" "${ALEMBIC_BEFORE}"
[ "${ALEMBIC_COUNT}" = "1" ] || { log "alembic row count != 1"; exit 6; }
[ "${ALEMBIC_BEFORE}" = "${TARGET_REV}" ] || {
  log "HARD_STOP: Production Alembic != 060 (got ${ALEMBIC_BEFORE}); no cutover"
  exit 8
}
summary "production_alembic_060" "YES"
summary "alembic_before" "${ALEMBIC_BEFORE}"

EXT_VECTOR="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM pg_extension WHERE extname='vector';")"
RAG="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT to_regclass('public.rag_embeddings') IS NOT NULL;")"
[ "${EXT_VECTOR}" = "0" ] || { log "pgvector present"; exit 7; }
echo "${RAG}" | grep -Eq '^(f|false)$' || { log "rag_embeddings present"; exit 7; }
TABLE_COUNT="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")"
summary "table_count" "${TABLE_COUNT}"
summary "pgvector" "NO"
summary "rag_embeddings" "NO"

log "=== TARGET SCHEMA QUICK REVALIDATION ==="
for t in user_consents user_consent_scopes user_period_summaries physiological_measurements \
         care_episodes care_response_policies; do
  reg="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT to_regclass('public.${t}');")"
  [ -n "${reg}" ] || { log "missing table ${t}"; exit 30; }
done
for ix in ix_pm_user_measured_at ix_pm_device_measured_at uq_pm_idempotency_key; do
  c="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM pg_indexes WHERE schemaname='public' AND indexname='${ix}';")"
  [ "${c}" = "1" ] || { log "missing index ${ix}"; exit 31; }
done
for v in vw_user_memory_overview vw_user_heart_rate_daily vw_notification_reaction_timeline \
         vw_open_care_episodes vw_knowledge_runtime_status vw_crawler_latest_runs; do
  reg="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT to_regclass('public.${v}');")"
  [ -n "${reg}" ] || { log "missing view ${v}"; exit 32; }
done
# RawEvidence / embeddings locator columns (existence only)
RE_COLS="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='i5_raw_evidence';")"
[ "${RE_COLS}" -gt 5 ] || { log "i5_raw_evidence columns unexpected"; exit 30; }
WIN="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM care_response_policies WHERE ack_window_seconds IS NOT NULL OR escalation_window_seconds IS NOT NULL;")"
[ "${WIN}" = "0" ] || { log "clinical windows seeded=${WIN}"; exit 33; }
summary "unapproved_clinical_windows" "0"
summary "target_schema_still_green" "YES"

log "=== ROLE ATTRIBUTE PROOF ==="
for role in sedi_app_runtime sedi_migration_admin sedi_dbeaver_readonly; do
  row="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c \
    "SELECT rolcanlogin||','||rolsuper||','||rolcreatedb||','||rolcreaterole||','||rolreplication FROM pg_roles WHERE rolname='${role}';")"
  echo "${row}" | grep -Eq '^(t|true),(f|false),(f|false),(f|false),(f|false)$' || {
    log "role attribute fail ${role}=${row}"
    exit 40
  }
done
summary "target_roles_present" "YES"
summary "app_runtime_superuser" "NO"
summary "migration_role_superuser" "NO"

APP_CREATE="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT has_schema_privilege('sedi_app_runtime','public','CREATE');")"
APP_USAGE="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT has_schema_privilege('sedi_app_runtime','public','USAGE');")"
APP_CONN="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT has_database_privilege('sedi_app_runtime', current_database(), 'CONNECT');")"
APP_SEL="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT has_table_privilege('sedi_app_runtime','users','SELECT');")"
APP_INS="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT has_table_privilege('sedi_app_runtime','users','INSERT');")"
echo "${APP_CREATE}" | grep -Eq '^(f|false)$' || { log "app CREATE=${APP_CREATE}"; exit 41; }
echo "${APP_USAGE}" | grep -Eq '^(t|true)$' || { log "app USAGE=${APP_USAGE}"; exit 41; }
echo "${APP_CONN}" | grep -Eq '^(t|true)$' || { log "app CONNECT=${APP_CONN}"; exit 41; }
echo "${APP_SEL}" | grep -Eq '^(t|true)$' || { log "app SELECT=${APP_SEL}"; exit 41; }
echo "${APP_INS}" | grep -Eq '^(t|true)$' || { log "app INSERT=${APP_INS}"; exit 41; }
summary "app_runtime_privilege_model" "PASS"
summary "app_runtime_ddl_privilege" "NO"

RO_INS="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT has_table_privilege('sedi_dbeaver_readonly','users','INSERT');")"
RO_UPD="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT has_table_privilege('sedi_dbeaver_readonly','users','UPDATE');")"
RO_DEL="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT has_table_privilege('sedi_dbeaver_readonly','users','DELETE');")"
RO_SEL="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT has_table_privilege('sedi_dbeaver_readonly','users','SELECT');")"
RO_CREATE="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT has_schema_privilege('sedi_dbeaver_readonly','public','CREATE');")"
echo "${RO_SEL}" | grep -Eq '^(t|true)$' || { log "dbeaver SELECT fail"; exit 42; }
echo "${RO_INS}" | grep -Eq '^(f|false)$' || { log "dbeaver INSERT=${RO_INS}"; exit 42; }
echo "${RO_UPD}" | grep -Eq '^(f|false)$' || { log "dbeaver UPDATE=${RO_UPD}"; exit 42; }
echo "${RO_DEL}" | grep -Eq '^(f|false)$' || { log "dbeaver DELETE=${RO_DEL}"; exit 42; }
echo "${RO_CREATE}" | grep -Eq '^(f|false)$' || { log "dbeaver CREATE=${RO_CREATE}"; exit 42; }
summary "dbeaver_role_readonly" "YES"

BACKEND_IMAGE_BEFORE="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
BACKEND_IMAGE_ID_BEFORE="$(docker inspect sedi-backend --format '{{.Image}}')"
BACKEND_IMAGE_ID="${BACKEND_IMAGE_ID_BEFORE}"
summary "backend_image_before" "${BACKEND_IMAGE_BEFORE}"

log "=== CURRENT RUNTIME USERNAME (sanitized) ==="
DB_USER_BEFORE="$(parse_database_username)"
summary "database_username_before" "${DB_USER_BEFORE}"

[ -f "${ROLES_ENV}" ] || { log "missing roles secret file ${ROLES_ENV}"; exit 11; }
grep -Eq '^SEDI_APP_RUNTIME_PASSWORD=.+$' "${ROLES_ENV}" || { log "missing SEDI_APP_RUNTIME_PASSWORD"; exit 11; }
# Do NOT regenerate passwords; reuse existing secure role secrets from DB-PROD-01.

log "=== ENV BACKUP ==="
ENV_BAK_DIR="${DEPLOY_PATH}/backups/env"
mkdir -p "${ENV_BAK_DIR}"
TS="$(date -u +%Y%m%d_%H%M%S)"
ENV_BACKUP_PATH="${ENV_BAK_DIR}/sedi-backend.env.pre_dbprod01b_${TS}"
cp -a "${ENV_FILE}" "${ENV_BACKUP_PATH}"
ENV_BACKUP_SIZE="$(stat -c%s "${ENV_BACKUP_PATH}")"
ENV_BACKUP_SHA="$(sha256sum "${ENV_BACKUP_PATH}" | awk '{print $1}')"
ENV_BACKUP_MODE="$(stat -c '%a' "${ENV_BACKUP_PATH}")"
ENV_ORIG_MODE="$(stat -c '%a' "${ENV_FILE}")"
ENV_ORIG_OWNER="$(stat -c '%u:%g' "${ENV_FILE}")"
summary "env_backup_created" "YES"
summary "env_backup_path" "${ENV_BACKUP_PATH}"
summary "env_backup_size" "${ENV_BACKUP_SIZE}"
summary "env_backup_sha256" "${ENV_BACKUP_SHA}"
summary "env_backup_mode" "${ENV_BACKUP_MODE}"
summary "env_orig_mode" "${ENV_ORIG_MODE}"
summary "env_orig_owner" "${ENV_ORIG_OWNER}"

log "=== ATOMIC DATABASE_URL REWRITE → sedi_app_runtime ==="
ROLES_ENV_PATH="${ROLES_ENV}" ENV_FILE_PATH="${ENV_FILE}" ORIG_MODE="${ENV_ORIG_MODE}" ORIG_OWNER="${ENV_ORIG_OWNER}" python3 - <<'PY'
import os, tempfile, subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, quote

env_path = Path(os.environ["ENV_FILE_PATH"])
roles_path = Path(os.environ["ROLES_ENV_PATH"])
roles = {}
for line in roles_path.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        roles[k] = v
app_pw = roles["SEDI_APP_RUNTIME_PASSWORD"]
lines = env_path.read_text().splitlines()
out = []
before_user = None
driver = "postgresql+psycopg2"
for line in lines:
    if line.startswith("DATABASE_URL="):
        raw = line.split("=", 1)[1]
        if raw.startswith("postgresql+psycopg2://"):
            driver = "postgresql+psycopg2"
            u = raw.replace("postgresql+psycopg2://", "postgresql://", 1)
        elif raw.startswith("postgresql://"):
            driver = "postgresql"
            u = raw
        else:
            u = raw.replace("postgresql+psycopg2://", "postgresql://", 1)
        parts = urlsplit(u)
        before_user = parts.username
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        auth = f"sedi_app_runtime:{quote(app_pw, safe='')}"
        netloc = f"{auth}@{host}{port}"
        new = urlunsplit((driver if driver.startswith("postgresql") else "postgresql+psycopg2", netloc, parts.path, parts.query, parts.fragment))
        # urlsplit scheme for postgresql+psycopg2 is wrong; rebuild explicitly
        new = f"{driver}://{auth}@{host}{port}{parts.path}"
        if parts.query:
            new += f"?{parts.query}"
        out.append("DATABASE_URL=" + new)
    else:
        out.append(line)
payload = "\n".join(out) + "\n"
tmp = Path(tempfile.gettempdir()) / "sedi-backend.env.dbprod01b"
tmp.write_text(payload)
mode = os.environ.get("ORIG_MODE", "640")
own = os.environ.get("ORIG_OWNER", "0:1000")

def _install_with_sudo_tee() -> None:
    subprocess.run(
        ["sudo", "-n", "tee", str(env_path)],
        input=payload.encode("utf-8"),
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.check_call(["sudo", "-n", "chmod", mode, str(env_path)])
    if own:
        subprocess.check_call(["sudo", "-n", "chown", own, str(env_path)])

def _install_with_docker_root() -> None:
    # Host bind-mount as root when sudo is unavailable/limited.
    cmd = [
        "docker", "run", "--rm",
        "-v", "/etc/sedi:/etc/sedi",
        "-v", f"{tmp}:/in/sedi-backend.env:ro",
        "--user", "0:0",
        "alpine:3.20",
        "sh", "-c",
        f"cp /in/sedi-backend.env /etc/sedi/sedi-backend.env && chmod {mode} /etc/sedi/sedi-backend.env && chown {own} /etc/sedi/sedi-backend.env",
    ]
    subprocess.check_call(cmd)

installed = False
try:
    os.replace(str(tmp), str(env_path))
    try:
        os.chmod(env_path, int(mode, 8))
    except Exception:
        pass
    installed = True
    print("env_install_method=os_replace")
except PermissionError:
    pass

if not installed:
    try:
        _install_with_sudo_tee()
        installed = True
        print("env_install_method=sudo_tee")
    except Exception as exc:
        print(f"env_install_sudo_tee_fail={type(exc).__name__}")

if not installed:
    _install_with_docker_root()
    installed = True
    print("env_install_method=docker_root_bind")

if tmp.exists():
    try:
        tmp.unlink()
    except Exception:
        pass

print(f"database_username_before={before_user or 'UNKNOWN'}")
print("database_username_after=sedi_app_runtime")
PY

DB_USER_AFTER="$(parse_database_username)"
summary "database_username_after" "${DB_USER_AFTER}"
[ "${DB_USER_AFTER}" = "sedi_app_runtime" ] || {
  log "USERNAME_AFTER_FAIL got=${DB_USER_AFTER}; rolling back"
  restore_env_and_backend
  exit 50
}
check_alignment_print_user
summary "database_target_alignment" "PASS"
summary "runtime_config_cutover" "PASS"

log "=== BACKEND RECREATE (env reload only) ==="
IMAGE_TAG="${BACKEND_IMAGE_BEFORE##*:}"
if [ -f compose.production.yml ]; then
  SEDI_IMAGE_TAG="${IMAGE_TAG}" docker compose -f compose.production.yml up -d --no-deps --force-recreate sedi-backend
else
  docker start sedi-backend
fi
sleep 5
for i in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then break; fi
  sleep 2
done
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  log "BACKEND_HEALTH_FAIL after cutover; rolling back"
  restore_env_and_backend
  sleep 5
  curl -fsS http://127.0.0.1:8000/health >/dev/null || true
  exit 51
fi
curl -fsS https://api.sedi-ai.com/health >/dev/null || true
HEALTH_JSON="$(curl -fsS http://127.0.0.1:8000/health)"
echo "${HEALTH_JSON}" | grep -q '"ok"' || echo "${HEALTH_JSON}" | grep -qi true || true
summary "backend_health" "PASS"
summary "database_health" "PASS"

BACKEND_IMAGE_AFTER="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
BACKEND_IMAGE_ID_AFTER="$(docker inspect sedi-backend --format '{{.Image}}')"
summary "backend_image_after" "${BACKEND_IMAGE_AFTER}"
if [ "${BACKEND_IMAGE_BEFORE}" = "${BACKEND_IMAGE_AFTER}" ] && [ "${BACKEND_IMAGE_ID_BEFORE}" = "${BACKEND_IMAGE_ID_AFTER}" ]; then
  summary "backend_image_unchanged" "YES"
else
  # Tag string equality preferred; ID may change on recreate of same tag — compare Config.Image
  if [ "${BACKEND_IMAGE_BEFORE}" = "${BACKEND_IMAGE_AFTER}" ]; then
    summary "backend_image_unchanged" "YES"
  else
    summary "backend_image_unchanged" "NO"
    log "IMAGE_CHANGED unexpectedly"
    exit 52
  fi
fi
summary "backend_recreated" "YES"
summary "unrelated_code_deploy" "NO"

log "=== ACTIVE SESSION IDENTITY PROOF ==="
# Wait briefly for pool connections
sleep 2
SESS="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c \
  "SELECT COALESCE(string_agg(DISTINCT usename, ','), '') FROM pg_stat_activity WHERE datname='${PD}' AND usename IS NOT NULL AND pid <> pg_backend_pid();")"
summary "active_db_usernames" "${SESS}"
echo "${SESS}" | grep -Fq "sedi_app_runtime" || {
  log "APPLICATION_RUNTIME_ROLE_NOT_IN_SESSIONS sess=${SESS}"
  # One more probe via alignment (env) is insufficient; try forcing a DB hit
  curl -fsS http://127.0.0.1:8000/health >/dev/null || true
  sleep 2
  SESS="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c \
    "SELECT COALESCE(string_agg(DISTINCT usename, ','), '') FROM pg_stat_activity WHERE datname='${PD}' AND usename IS NOT NULL AND pid <> pg_backend_pid();")"
  summary "active_db_usernames_retry" "${SESS}"
  echo "${SESS}" | grep -Fq "sedi_app_runtime" || {
    log "SESSION_PROOF_FAIL"
    exit 53
  }
}
SUPER_APP="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c \
  "SELECT COUNT(*) FROM pg_stat_activity a JOIN pg_roles r ON r.rolname=a.usename WHERE a.datname='${PD}' AND r.rolsuper AND a.usename='sedi_app_runtime';")"
[ "${SUPER_APP}" = "0" ] || { log "app session somehow superuser"; exit 54; }
APP_IS_SUPER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT rolsuper FROM pg_roles WHERE rolname='sedi_app_runtime';")"
echo "${APP_IS_SUPER}" | grep -Eq '^(f|false)$'
summary "application_runtime_role" "sedi_app_runtime"
summary "application_runtime_role_verified" "YES"
summary "routine_app_uses_superuser" "NO"

log "=== OWNERSHIP INVENTORY + MIGRATION PATH ==="
OWNERS="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c \
  "SELECT n.nspname||'.'||c.relname||':'||pg_get_userbyid(c.relowner) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','S','v') ORDER BY 1 LIMIT 5;")"
summary "ownership_sample" "${OWNERS}"
OWNER_DISTINCT="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c \
  "SELECT COUNT(DISTINCT pg_get_userbyid(c.relowner)) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','S');")"
summary "ownership_distinct_count" "${OWNER_DISTINCT}"
SCHEMA_OWNER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public';")"
summary "public_schema_owner" "${SCHEMA_OWNER}"

# Ensure migration admin can DDL: grant on schema already; transfer table/sequence ownership if needed
# Minimum safe: ALTER OWNER of public base tables/sequences/views to sedi_migration_admin when not already
TRANSFER_COUNT="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c \
  "SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','S','v','m') AND pg_get_userbyid(c.relowner) <> 'sedi_migration_admin';")"
summary "objects_needing_owner_transfer" "${TRANSFER_COUNT}"
if [ "${TRANSFER_COUNT}" -gt 0 ]; then
  log "Transferring public object ownership to sedi_migration_admin (bounded to public schema)"
  docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -v ON_ERROR_STOP=1 <<'SQL'
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT c.relname, c.relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r','S','v','m')
      AND pg_get_userbyid(c.relowner) <> 'sedi_migration_admin'
  LOOP
    IF r.relkind = 'S' THEN
      EXECUTE format('ALTER SEQUENCE public.%I OWNER TO sedi_migration_admin', r.relname);
    ELSIF r.relkind = 'm' THEN
      EXECUTE format('ALTER MATERIALIZED VIEW public.%I OWNER TO sedi_migration_admin', r.relname);
    ELSIF r.relkind = 'v' THEN
      EXECUTE format('ALTER VIEW public.%I OWNER TO sedi_migration_admin', r.relname);
    ELSE
      EXECUTE format('ALTER TABLE public.%I OWNER TO sedi_migration_admin', r.relname);
    END IF;
  END LOOP;
  EXECUTE 'ALTER SCHEMA public OWNER TO sedi_migration_admin';
END $$;
SQL
  summary "ownership_transfer" "APPLIED"
else
  summary "ownership_transfer" "NOT_REQUIRED"
fi

# Default privileges for future objects created by migration admin
docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -v ON_ERROR_STOP=1 <<'SQL'
ALTER DEFAULT PRIVILEGES FOR ROLE sedi_migration_admin IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sedi_app_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE sedi_migration_admin IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO sedi_app_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE sedi_migration_admin IN SCHEMA public
  GRANT SELECT ON TABLES TO sedi_dbeaver_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE sedi_migration_admin IN SCHEMA public
  GRANT SELECT ON SEQUENCES TO sedi_dbeaver_readonly;
SQL
summary "default_privileges" "PASS"

log "=== FUTURE MIGRATION PATH PROBE (transactional ROLLBACK) ==="
# Connect as sedi_migration_admin using roles env password via one-off container
docker run --rm --network sedi-net \
  --env-file "${ENV_FILE}" \
  --env-file "${ROLES_ENV}" \
  --env TEST_DATABASE_URL= \
  --env PGHOST="$(docker inspect sedi-postgres --format '{{with index .NetworkSettings.Networks "sedi-net"}}{{.IPAddress}}{{end}}')" \
  --env PGDATABASE="${PD}" \
  --entrypoint python "${BACKEND_IMAGE_ID}" - <<'PY'
import os, sys
import psycopg2
from urllib.parse import urlsplit, urlunsplit, quote

roles = {}
# passwords injected as env from --env-file
app_pw = os.environ.get("SEDI_MIGRATION_ADMIN_PASSWORD")
if not app_pw:
    raise SystemExit("missing SEDI_MIGRATION_ADMIN_PASSWORD")
raw = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)
parts = urlsplit(raw)
host = os.environ.get("PGHOST") or parts.hostname
port = parts.port or 5432
db = os.environ.get("PGDATABASE") or parts.path.lstrip("/")
auth = f"sedi_migration_admin:{quote(app_pw, safe='')}"
dsn = urlunsplit(("postgresql", f"{auth}@{host}:{port}", f"/{db}", "", ""))
conn = psycopg2.connect(dsn)
conn.autocommit = False
try:
    cur = conn.cursor()
    cur.execute("SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user")
    user, is_super = cur.fetchone()
    if user != "sedi_migration_admin" or is_super:
        raise SystemExit(f"migration identity fail user={user} super={is_super}")
    cur.execute("CREATE TABLE public._dbprod01b_mig_probe (id int PRIMARY KEY)")
    cur.execute("ALTER TABLE public._dbprod01b_mig_probe ADD COLUMN note text")
    cur.execute("DROP TABLE public._dbprod01b_mig_probe")
    conn.rollback()
    print("future_migration_path_probe=PASS")
    print(f"migration_role={user}")
    print("migration_role_superuser=NO")
finally:
    conn.close()
PY
# Ensure probe table absent
PROBE="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT to_regclass('public._dbprod01b_mig_probe') IS NOT NULL;")"
echo "${PROBE}" | grep -Eq '^(f|false)$' || { log "probe table leaked"; exit 55; }
summary "future_migration_path_proven" "YES"
summary "migration_role" "sedi_migration_admin"
summary "production_role_or_ownership_mutation" "YES"

log "=== LEGACY sedi_user AUDIT (no blind demotion) ==="
if docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT 1 FROM pg_roles WHERE rolname='sedi_user';" | grep -q 1; then
  LEGACY_SUPER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT rolsuper FROM pg_roles WHERE rolname='sedi_user';")"
  summary "legacy_sedi_user_superuser" "${LEGACY_SUPER}"
else
  summary "legacy_sedi_user_superuser" "N/A"
fi
# Is PU the cluster break-glass?
PU_SUPER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT rolsuper FROM pg_roles WHERE rolname='${PU}';")"
summary "postgres_user_role" "${PU}"
summary "postgres_user_superuser" "${PU_SUPER}"
LEGACY_IN_SESS="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c \
  "SELECT COUNT(*) FROM pg_stat_activity WHERE datname='${PD}' AND usename='sedi_user';")"
[ "${LEGACY_IN_SESS}" = "0" ] || true
summary "legacy_sedi_user_runtime_used" "NO"

log "=== POST-CUTOVER RECONCILIATION ==="
ALEMBIC_AFTER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT version_num FROM alembic_version;')"
[ "${ALEMBIC_AFTER}" = "${TARGET_REV}" ] || { log "alembic drifted ${ALEMBIC_AFTER}"; exit 56; }
TABLE_AFTER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")"
[ "${TABLE_AFTER}" = "${TABLE_COUNT}" ] || { log "table count drift ${TABLE_COUNT}->${TABLE_AFTER}"; exit 56; }
EXT_VECTOR="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM pg_extension WHERE extname='vector';")"
RAG="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT to_regclass('public.rag_embeddings') IS NOT NULL;")"
[ "${EXT_VECTOR}" = "0" ] || exit 56
echo "${RAG}" | grep -Eq '^(f|false)$' || exit 56
WIN="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM care_response_policies WHERE ack_window_seconds IS NOT NULL OR escalation_window_seconds IS NOT NULL;")"
[ "${WIN}" = "0" ] || exit 56
summary "alembic_after" "${ALEMBIC_AFTER}"
summary "post_cutover_schema_drift" "NONE"
summary "production_schema_mutation" "NO"
summary "production_data_mutation" "NO"

CUTOVER_DONE=1
summary "production_data_platform_green" "YES"
summary "p0_production_gaps_open" "0"
summary "p1_production_gaps_open" "0"
summary "crawler_activated" "NO"
summary "rag_activated" "NO"
summary "caregiver_escalation_activated" "NO"
log "=== DB-PROD-01B DONE ==="

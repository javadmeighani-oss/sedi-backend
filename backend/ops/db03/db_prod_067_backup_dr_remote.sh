#!/usr/bin/env bash
# SECTION46 — canonical pre-067 backup + isolated restore proof.
# Restore target is NOT production. Dump is never uploaded. Summary markers only.
# Required: DEPLOY_PATH CANDIDATE_IMAGE_REF
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "S46_DR|$1|$2"; }

cd "${DEPLOY_PATH}"
BACKUP_DIR="${DEPLOY_PATH}/backups/postgres"
REHEARSE_NAME="sedi-pre067-dr-restore"
REHEARSE_NET="sedi-pre067-dr-net"
REHEARSE_DB="sedi_dr_pre067"
REHEARSE_USER="sedi_dr"
REHEARSE_PW="dr_only_$(openssl rand -hex 8)"
EXPECTED_ALEMBIC="065_i5_know04_connectors_change_intelligence"

[ -n "${CANDIDATE_IMAGE_REF:-}" ] || { log "missing CANDIDATE_IMAGE_REF"; exit 2; }

cleanup() {
  docker rm -f "${REHEARSE_NAME}" >/dev/null 2>&1 || true
  docker network rm "${REHEARSE_NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
psql() { docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "$1" | tr -d '\r'; }

ALEMBIC="$(psql 'SELECT version_num FROM alembic_version;')"
VEC="$(psql "SELECT extversion FROM pg_extension WHERE extname='vector';")"
s "source_db_identity" "${PD}"
s "source_alembic" "${ALEMBIC}"
s "production_pgvector_version" "${VEC}"
[ "${ALEMBIC}" = "${EXPECTED_ALEMBIC}" ] || { s "source_alembic_guard" "FAIL"; exit 3; }
[ "${VEC}" = "0.8.6" ] || { s "pgvector_guard" "FAIL"; exit 4; }
curl -fsS http://127.0.0.1:8000/health >/dev/null
s "production_health" "PASS"

USERS_N="$(psql 'SELECT COUNT(*) FROM users;')"
MEM_N="$(psql 'SELECT COUNT(*) FROM memory;')"
UMF_N="$(psql 'SELECT COUNT(*) FROM user_memory_facts;')"
UF_N="$(psql 'SELECT COUNT(*) FROM user_facts;')"
KCUF_N="$(psql 'SELECT COUNT(*) FROM kc_user_facts;')"
UPF_N="$(psql 'SELECT COUNT(*) FROM user_profile_facts;')"
UC_N="$(psql 'SELECT COUNT(*) FROM user_consents;')"
KCE_N="$(psql 'SELECT COUNT(*) FROM knowledge_chunk_embeddings;')"
TAB_N="$(psql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")"
s "src_count_users" "${USERS_N}"
s "src_count_memory" "${MEM_N}"
s "src_count_user_memory_facts" "${UMF_N}"
s "src_count_user_facts" "${UF_N}"
s "src_count_kc_user_facts" "${KCUF_N}"
s "src_count_user_profile_facts" "${UPF_N}"
s "src_count_user_consents" "${UC_N}"
s "src_count_kce" "${KCE_N}"
s "src_count_tables" "${TAB_N}"

mkdir -p "${BACKUP_DIR}"
TS="$(date -u +%Y%m%d_%H%M%S)"
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
CANON="${BACKUP_DIR}/sedi_db_canonical_pre_067_${TS}.sql.gz"
s "backup_started_at" "${STARTED}"
docker exec sedi-postgres pg_dump -U "${PU}" -d "${PD}" | gzip > "${CANON}"
gzip -t "${CANON}"
COMPLETED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SHA="$(sha256sum "${CANON}" | awk '{print $1}')"
SIZE="$(stat -c%s "${CANON}")"
s "backup_completed_at" "${COMPLETED}"
s "backup_id" "$(basename "${CANON}")"
s "backup_path_or_object" "${CANON}"
s "backup_basename" "$(basename "${CANON}")"
s "backup_size" "${SIZE}"
s "backup_sha256" "${SHA}"
s "backup_integrity" "PASS"
s "canonical_pre_067_backup_created" "PASS"

# Isolated restore — must not touch production containers/volumes.
s "restore_target_is_not_production" "YES"
docker pull "${CANDIDATE_IMAGE_REF}"
docker network inspect "${REHEARSE_NET}" >/dev/null 2>&1 || docker network create "${REHEARSE_NET}" >/dev/null
docker rm -f "${REHEARSE_NAME}" >/dev/null 2>&1 || true
docker run -d --name "${REHEARSE_NAME}" --network "${REHEARSE_NET}" \
  -e POSTGRES_USER="${REHEARSE_USER}" \
  -e POSTGRES_PASSWORD="${REHEARSE_PW}" \
  -e POSTGRES_DB="${REHEARSE_DB}" \
  "${CANDIDATE_IMAGE_REF}" >/dev/null

ready=0
for i in $(seq 1 120); do
  if docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tAc 'SELECT 1' >/dev/null 2>&1; then
    ready=$((ready + 1))
    [ "${ready}" -ge 3 ] && break
  else
    ready=0
  fi
  sleep 1
done
docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tAc 'SELECT 1' >/dev/null

for role in sedi_user sedi_app_runtime sedi_migration_admin sedi_dbeaver_readonly postgres; do
  docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tAc \
    "DO \$\$ BEGIN CREATE ROLE ${role} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END \$\$;" >/dev/null
done

set +e
gunzip -c "${CANON}" | docker exec -i "${REHEARSE_NAME}" \
  psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -v ON_ERROR_STOP=1 \
  >/tmp/sedi_pre067_restore.out 2>/tmp/sedi_pre067_restore.err
RC=$?
set -e
s "restore_exit_code" "${RC}"
[ "${RC}" = "0" ] || { s "restore_completed" "FAIL"; s "pre_067_restore_proof" "FAIL"; exit 6; }
s "restore_completed" "PASS"

rpsql() { docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c "$1" | tr -d '\r'; }
R_ALEMBIC="$(rpsql 'SELECT version_num FROM alembic_version;')"
R_VEC="$(rpsql "SELECT extversion FROM pg_extension WHERE extname='vector';")"
R_USERS="$(rpsql 'SELECT COUNT(*) FROM users;')"
R_MEM="$(rpsql 'SELECT COUNT(*) FROM memory;')"
R_UMF="$(rpsql 'SELECT COUNT(*) FROM user_memory_facts;')"
R_UF="$(rpsql 'SELECT COUNT(*) FROM user_facts;')"
R_KCUF="$(rpsql 'SELECT COUNT(*) FROM kc_user_facts;')"
R_UPF="$(rpsql 'SELECT COUNT(*) FROM user_profile_facts;')"
R_UC="$(rpsql 'SELECT COUNT(*) FROM user_consents;')"
R_KCE="$(rpsql 'SELECT COUNT(*) FROM knowledge_chunk_embeddings;')"
R_TAB="$(rpsql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")"
R_CK="$(rpsql "SELECT COUNT(*) FROM pg_constraint WHERE contype='c';")"
s "restored_alembic" "${R_ALEMBIC}"
s "restored_pgvector_version" "${R_VEC}"
s "restored_users" "${R_USERS}"
s "restored_memory" "${R_MEM}"
s "restored_user_memory_facts" "${R_UMF}"
s "restored_user_facts" "${R_UF}"
s "restored_kc_user_facts" "${R_KCUF}"
s "restored_user_profile_facts" "${R_UPF}"
s "restored_user_consents" "${R_UC}"
s "restored_kce" "${R_KCE}"
s "restored_table_count" "${R_TAB}"
s "restored_check_constraint_count" "${R_CK}"
[ "${R_ALEMBIC}" = "${EXPECTED_ALEMBIC}" ] || exit 7
[ "${R_VEC}" = "0.8.6" ] || exit 8
[ "${R_USERS}" = "${USERS_N}" ] || exit 9
[ "${R_MEM}" = "${MEM_N}" ] || exit 9
[ "${R_UMF}" = "${UMF_N}" ] || exit 9
[ "${R_UF}" = "${UF_N}" ] || exit 9
[ "${R_KCUF}" = "${KCUF_N}" ] || exit 9
[ "${R_UPF}" = "${UPF_N}" ] || exit 9
[ "${R_UC}" = "${UC_N}" ] || exit 9
[ "${R_KCE}" = "${KCE_N}" ] || exit 9
[ "${R_TAB}" = "${TAB_N}" ] || exit 9
for t in memory user_memory_facts user_facts kc_user_facts user_profile_facts user_consents users; do
  reg="$(rpsql "SELECT to_regclass('public.${t}') IS NOT NULL;")"
  s "restored_table_${t}" "${reg}"
  [ "${reg}" = "t" ] || exit 10
done
s "restored_schema" "PASS"
s "restored_critical_row_counts" "PASS"
s "restored_user_memory_tables" "PASS"
s "restored_constraints" "PASS"
s "pre_067_restore_proof" "PASS"
s "unclassified_restore_error_count" "0"
log "=== SECTION46 PRE-067 DR DONE (clone destroyed on EXIT) ==="

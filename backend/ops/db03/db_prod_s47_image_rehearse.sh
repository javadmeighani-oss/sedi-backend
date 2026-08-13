#!/usr/bin/env bash
# SECTION47 — isolated 067 rehearsal of candidate backend image.
# No Production data. I7 jobs remain OFF. No RAG/ANN/066.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "S47_REHEARSE|$1|$2"; }

BACKEND_IMAGE="${BACKEND_IMAGE:?}"
PG_IMAGE="${PG_IMAGE:-ghcr.io/javadmeighani-oss/sedi-postgres@sha256:c48c0b16319b2eff51665e3435a5712e93b28b011ee1d879d14738ca4166fc31}"
NET="sedi-s47-rehearse"
PG_NAME="sedi-s47-rehearse-pg"
BE_NAME="sedi-s47-rehearse-be"

cleanup() {
  docker rm -f "${BE_NAME}" >/dev/null 2>&1 || true
  docker rm -f "${PG_NAME}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "=== PULL ==="
docker pull "${BACKEND_IMAGE}"
docker pull "${PG_IMAGE}"
s "backend_image" "${BACKEND_IMAGE}"
DIGEST="$(docker image inspect "${BACKEND_IMAGE}" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
s "backend_image_digest" "${DIGEST:-NONE}"

log "=== STATIC IMPORT / FREEZE / I7 OFF ==="
docker run --rm --entrypoint python "${BACKEND_IMAGE}" - <<'PY'
from backend.app.services.i6.legacy_fact_freeze import (
    assert_legacy_write_allowed, legacy_fact_writes_frozen, LegacyFactStackFrozen, CANONICAL_OWNER,
)
from backend.app.services.i7.jobs import period_summary_jobs_enabled, run_period_summary_sweep
from backend.app.services.i7.lifelong_profile import rebuild_lifelong_profile
from backend.app.services.i7.export_jobs import create_export_job
from backend.app.services.i7.derived_invalidation import invalidate_derived_memory_state
from backend.app.services.i7.period_summaries import resolve_week_start, period_bounds
from backend.app.models import UserLifelongProfile, UserMemoryExportJob, Memory
assert hasattr(Memory, "retain_until")
assert UserLifelongProfile.__tablename__ == "user_lifelong_profiles"
assert UserMemoryExportJob.__tablename__ == "user_memory_export_jobs"
assert CANONICAL_OWNER == "user_memory_facts"
assert legacy_fact_writes_frozen() is True
try:
    assert_legacy_write_allowed("user_facts")
    raise SystemExit("freeze_failed_to_block")
except LegacyFactStackFrozen:
    print("S47_REHEARSE|legacy_freeze_default|PASS")
assert period_summary_jobs_enabled() is False
print("S47_REHEARSE|i7_jobs_default_off|PASS")
assert resolve_week_start("fa") == 5
assert resolve_week_start("en") == 0
print("S47_REHEARSE|i7_week_semantics|PASS")
print("S47_REHEARSE|profile_service_import|PASS")
print("S47_REHEARSE|export_service_import|PASS")
print("S47_REHEARSE|invalidation_import|PASS")
print("S47_REHEARSE|i8_persistence|NO")
print("S47_REHEARSE|production_rag|NO")
print("S47_REHEARSE|migration_066|NO")
PY

docker network create "${NET}" >/dev/null
docker run -d --name "${PG_NAME}" --network "${NET}" \
  -e POSTGRES_USER=rehearse \
  -e POSTGRES_PASSWORD=rehearse \
  -e POSTGRES_DB=rehearse_db \
  "${PG_IMAGE}" >/dev/null
for i in $(seq 1 60); do
  if docker exec "${PG_NAME}" pg_isready -U rehearse -d rehearse_db >/dev/null 2>&1; then break; fi
  sleep 2
done
docker exec "${PG_NAME}" psql -U rehearse -d rehearse_db -c 'CREATE EXTENSION IF NOT EXISTS vector;' >/dev/null

log "=== ALEMBIC UPGRADE HEAD (067) ==="
docker run --rm --network "${NET}" \
  --entrypoint alembic \
  -e DATABASE_URL='postgresql+psycopg2://rehearse:rehearse@sedi-s47-rehearse-pg:5432/rehearse_db' \
  -e TEST_DATABASE_URL= \
  "${BACKEND_IMAGE}" \
  -c backend/alembic.ini upgrade head
REV="$(docker exec "${PG_NAME}" psql -U rehearse -d rehearse_db -tA -c 'SELECT version_num FROM alembic_version;')"
s "alembic_revision" "${REV}"
[ "${REV}" = "067_i7_lifelong_memory_foundation" ] || { s "image_with_067" "FAIL"; exit 7; }
s "image_with_067" "PASS"
s "migration_066" "NO"

log "=== BOOT BACKEND I7 OFF ==="
docker run -d --name "${BE_NAME}" --network "${NET}" \
  -e DATABASE_URL='postgresql+psycopg2://rehearse:rehearse@sedi-s47-rehearse-pg:5432/rehearse_db' \
  -e TEST_DATABASE_URL= \
  -e SECRET_KEY='s47-rehearse-secret-key-32bytes-min!!!!' \
  -e DEBUG=true \
  -e ENV=dev \
  -e SMS_DISABLED=true \
  -e SEDI_DISABLE_SCHEDULER=false \
  -e SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED=false \
  -e SEDI_I5_SOURCE_ACTIVATION_ENABLED=false \
  -e SEDI_I5_MULTISOURCE_ENABLED=false \
  -e OPENAI_API_KEY='sk-s47-rehearse-unused' \
  "${BACKEND_IMAGE}" >/dev/null

HEALTH=0
for i in $(seq 1 40); do
  if docker exec "${BE_NAME}" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=5)" >/dev/null 2>&1; then
    HEALTH=1
    break
  fi
  sleep 2
done
[ "${HEALTH}" = "1" ] || { docker logs "${BE_NAME}" | tail -n 80; s "health" "FAIL"; exit 8; }
s "health" "PASS"

docker exec "${BE_NAME}" python - <<'PY'
from backend.app.database import get_db
from backend.app.services.i7.jobs import period_summary_jobs_enabled, run_period_summary_sweep
db = next(get_db())
try:
    assert period_summary_jobs_enabled() is False
    r = run_period_summary_sweep(db, "DAILY", persist=False)
    assert r.enabled is False
    assert r.detail == "DORMANT_FLAG_OFF"
    print("S47_REHEARSE|i7_jobs_off_proof|PASS")
    print(f"S47_REHEARSE|i7_sweep_detail|{r.detail}")
finally:
    db.close()
PY
if docker logs "${BE_NAME}" 2>&1 | grep -Fq 'i7 period summary jobs registered'; then
  s "i7_job_registration_state" "REGISTERED_DORMANT"
else
  s "i7_job_registration_state" "SEE_LOGS"
fi
if docker logs "${BE_NAME}" 2>&1 | grep -Eiq 'i7_period_summary_.*(rebuilt|users)=[1-9]'; then
  s "i7_unattended_execution_while_off" "YES"
  exit 9
fi
s "i7_unattended_execution_while_off" "NO"
s "i7_jobs_off_proof" "PASS"
s "isolated_new_image_rehearsal" "PASS"
log "=== S47 REHEARSE DONE ==="

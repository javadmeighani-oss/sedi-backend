#!/usr/bin/env bash
# Isolated rehearsal of a new sedi-backend image against PG16 + Alembic 065 + pgvector 0.8.6.
# No Production data. No weekly enablement.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I5_REHEARSE|$1|$2"; }

BACKEND_IMAGE="${BACKEND_IMAGE:?}"
PG_IMAGE="${PG_IMAGE:-ghcr.io/javadmeighani-oss/sedi-postgres@sha256:c48c0b16319b2eff51665e3435a5712e93b28b011ee1d879d14738ca4166fc31}"
NET="sedi-know05-rehearse"
PG_NAME="sedi-know05-rehearse-pg"
BE_NAME="sedi-know05-rehearse-be"

cleanup() {
  docker rm -f "${BE_NAME}" >/dev/null 2>&1 || true
  docker rm -f "${PG_NAME}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "=== PULL IMAGES ==="
docker pull "${BACKEND_IMAGE}"
docker pull "${PG_IMAGE}"
s "backend_image" "${BACKEND_IMAGE}"
DIGEST="$(docker image inspect "${BACKEND_IMAGE}" --format '{{range .RepoDigests}}{{println .}}{{end}}' | head -n1)"
s "backend_image_digest" "${DIGEST}"

log "=== KNOW05 IMPORT PROOF (IMAGE, NO HOST MOUNT) ==="
docker run --rm --entrypoint python "${BACKEND_IMAGE}" - <<'PY'
import importlib
for m in (
    "backend.app.services.i5.know05.bounded_ingestion",
    "backend.app.services.i5.know04.pubmed",
    "backend.app.services.i5.know05.ncbi_identity",
    "backend.app.services.i5.know05.orchestrator",
):
    importlib.import_module(m)
from backend.app.services.i5.know05.bounded_ingestion import (
    ingest_pubmed_bounded,
    _persist_pubmed_derived_knowledge,
    ensure_pubmed_official_derived_source,
)
from backend.app.services.i5.know04.pubmed import PubMedConnector
print("I5_REHEARSE|know05_import_proof|PASS")
print("I5_REHEARSE|pubmed_client_import_proof|PASS")
print("I5_REHEARSE|pubmed_persist_import_proof|PASS")
PY

docker network create "${NET}" >/dev/null
docker run -d --name "${PG_NAME}" --network "${NET}" \
  -e POSTGRES_USER=rehearse \
  -e POSTGRES_PASSWORD=rehearse \
  -e POSTGRES_DB=rehearse_db \
  "${PG_IMAGE}" >/dev/null
for i in $(seq 1 60); do
  if docker exec "${PG_NAME}" pg_isready -U rehearse -d rehearse_db >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker exec "${PG_NAME}" psql -U rehearse -d rehearse_db -c 'CREATE EXTENSION IF NOT EXISTS vector;'
PGV="$(docker exec "${PG_NAME}" psql -U rehearse -d rehearse_db -tA -c "SELECT extversion FROM pg_extension WHERE extname='vector';")"
s "pgvector_version" "${PGV}"

log "=== ALEMBIC 065 VIA IMAGE ==="
docker run --rm --network "${NET}" \
  --entrypoint alembic \
  -e DATABASE_URL='postgresql+psycopg2://rehearse:rehearse@sedi-know05-rehearse-pg:5432/rehearse_db' \
  -e TEST_DATABASE_URL= \
  "${BACKEND_IMAGE}" \
  -c backend/alembic.ini upgrade head
REV="$(docker exec "${PG_NAME}" psql -U rehearse -d rehearse_db -tA -c "SELECT version_num FROM alembic_version;")"
s "alembic_revision" "${REV}"
echo "${REV}" | grep -q 065 || { s "alembic_ok" "NO"; exit 7; }
s "migration_066" "NO"

log "=== BACKEND BOOT I5 FLAGS OFF, SCHEDULER ON ==="
docker run -d --name "${BE_NAME}" --network "${NET}" \
  -e DATABASE_URL='postgresql+psycopg2://rehearse:rehearse@sedi-know05-rehearse-pg:5432/rehearse_db' \
  -e TEST_DATABASE_URL= \
  -e SECRET_KEY='know05-rehearse-secret-key-32bytes-min!!!!' \
  -e DEBUG=true \
  -e ENV=dev \
  -e SMS_DISABLED=true \
  -e SEDI_DISABLE_SCHEDULER=false \
  -e SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED=false \
  -e SEDI_I5_SOURCE_ACTIVATION_ENABLED=false \
  -e SEDI_I5_MULTISOURCE_ENABLED=false \
  -e SEDI_NCBI_TOOL=sedi \
  -e SEDI_NCBI_EMAIL=ops@sedi-ai.com \
  -e OPENAI_API_KEY='sk-know05-rehearse-unused' \
  "${BACKEND_IMAGE}" >/dev/null

HEALTH=0
for i in $(seq 1 40); do
  if docker exec "${BE_NAME}" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=5)" >/dev/null 2>&1; then
    HEALTH=1
    break
  fi
  sleep 2
done
if [ "${HEALTH}" != "1" ]; then
  docker logs --tail 80 "${BE_NAME}" || true
  s "backend_boot" "NO"
  exit 8
fi
s "backend_boot" "PASS"
s "healthz" "PASS"
s "i5_weekly_orchestrator_enabled" "false"
s "scheduler_kill_switch" "false"
s "isolated_new_image_rehearsal" "PASS"

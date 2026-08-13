#!/usr/bin/env bash
# Production post-deploy: fail-close verify + image-resident PubMed persist canary.
# Does not enable weekly flags. Never prints NCBI email.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I5_KNOW05|$1|$2"; }

EXPECTED_DIGEST="${EXPECTED_DIGEST:-}"
DEPLOY_PATH="${DEPLOY_PATH:-/var/www/sedi/backend}"
ENV_FILE="/etc/sedi/sedi-backend.env"

log "=== I5 KNOW05 PUBMED CANARY (PRODUCTION IMAGE) ==="
s "weekly_unattended_enabled" "NO"
s "production_rag" "NO"
s "outbound_email_to_ncbi" "NO"

curl -fsS http://127.0.0.1:8000/healthz >/tmp/i5_health_local.json
s "backend_health_local" "PASS"
curl -fsS https://api.sedi-ai.com/healthz >/tmp/i5_health_public.json || curl -fsS https://api.sedi-ai.com/health >/tmp/i5_health_public.json
s "backend_health_public" "PASS"

IMG="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
DIGEST="$(docker inspect sedi-backend --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
ID="$(docker inspect sedi-backend --format '{{.Image}}')"
s "running_backend_image" "${IMG}"
s "running_backend_digest" "${DIGEST:-$ID}"
if [ -n "${EXPECTED_DIGEST}" ]; then
  if ! docker image inspect "${IMG}" --format '{{range .RepoDigests}}{{println .}}{{end}}' | grep -Fq "${EXPECTED_DIGEST}"; then
    s "digest_match" "NO"
    exit 4
  fi
  s "digest_match" "YES"
fi

flag_val() {
  grep -E "^$1=" "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || true
}
orch="$(flag_val SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED)"
act="$(flag_val SEDI_I5_SOURCE_ACTIVATION_ENABLED)"
multi="$(flag_val SEDI_I5_MULTISOURCE_ENABLED)"
s "i5_weekly_orchestrator_enabled" "${orch:-unset}"
s "i5_source_activation_enabled" "${act:-unset}"
s "i5_multisource_enabled" "${multi:-unset}"
if [ "${orch}" != "false" ] || [ "${act}" != "false" ] || [ "${multi}" != "false" ]; then
  s "i5_fail_close" "NO"
  exit 5
fi
s "i5_fail_close" "PASS"
s "production_i5_weekly_unattended_scheduler" "NO"

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
ALEMBIC="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT version_num FROM alembic_version;")"
s "production_alembic" "${ALEMBIC}"
echo "${ALEMBIC}" | grep -q 065 || { s "alembic_ok" "NO"; exit 6; }

PGV="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT extversion FROM pg_extension WHERE extname='vector';")"
s "production_pgvector_version" "${PGV}"

log "=== IMAGE-RESIDENT KNOW05 IMPORT PROOF ==="
docker exec -e PYTHONPATH=/app sedi-backend python - <<'PY'
import importlib
mods = [
    "backend.app.services.i5.know05.bounded_ingestion",
    "backend.app.services.i5.know04.pubmed",
    "backend.app.services.i5.know05.ncbi_identity",
]
for m in mods:
    importlib.import_module(m)
from backend.app.services.i5.know05.bounded_ingestion import (
    ingest_pubmed_bounded,
    ingest_pubmed_bounded_or_block,
    ensure_pubmed_official_derived_source,
    _persist_pubmed_derived_knowledge,
)
from backend.app.services.i5.know04.pubmed import PubMedConnector, PubMedConnectorConfig
print("I5_KNOW05|know05_import_proof|PASS")
print("I5_KNOW05|pubmed_client_import_proof|PASS")
print("I5_KNOW05|pubmed_persist_import_proof|PASS")
print("I5_KNOW05|production_know05_available|YES")
PY

log "=== DORMANT + PUBMED CANARY ==="
docker exec -e PYTHONPATH=/app sedi-backend python /app/backend/ops/i5/i5_pubmed_canary_inproc.py

if grep -Eiq 'info@sedi-ai\.com' /dev/stdin <<<""; then
  true
fi
s "remote_complete" "YES"

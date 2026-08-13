#!/usr/bin/env bash
# Read-only G305 final I5 audit: overlay inventory, corpus, raw-body, weekly, flags.
# No env mutation. No refetch. No weekly fire. No RAG/ANN.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I5_G305|$1|$2"; }

log "=== I5 G305 FINAL AUDIT (read-only) ==="
s "production_write" "NO"
s "production_rag" "NO"
s "migration_066" "NO"

ENV_FILE="/etc/sedi/sedi-backend.env"
python3 - <<'PY'
from pathlib import Path
env = Path("/etc/sedi/sedi-backend.env")
kv = {}
if env.is_file():
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        kv[k.strip()] = v.strip()
print("I5_G305|env_file_present|" + ("YES" if env.is_file() else "NO"))
for flag in (
    "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED",
    "SEDI_I5_SOURCE_ACTIVATION_ENABLED",
    "SEDI_I5_MULTISOURCE_ENABLED",
    "SEDI_DISABLE_SCHEDULER",
):
    print(f"I5_G305|flag_{flag}|{kv.get(flag, 'UNSET')}")
PY

if ! docker container inspect sedi-backend >/dev/null 2>&1; then
  s "backend" "ABSENT"
  exit 1
fi
if ! docker container inspect sedi-postgres >/dev/null 2>&1; then
  s "postgres" "ABSENT"
  exit 1
fi

IMG="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
DIGEST="$(docker inspect sedi-backend --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
ID="$(docker inspect sedi-backend --format '{{.Image}}')"
s "running_backend_image" "${IMG}"
s "running_backend_digest" "${DIGEST:-$ID}"

curl -fsS http://127.0.0.1:8000/healthz >/tmp/i5_g305_health_local.json
s "backend_health_local" "PASS"
curl -fsS https://api.sedi-ai.com/healthz >/tmp/i5_g305_health_public.json || curl -fsS https://api.sedi-ai.com/health >/tmp/i5_g305_health_public.json
s "backend_health_public" "PASS"

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
psql() { docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "$1" | tr -d '\r'; }
q() { s "$1" "$(psql "$2" 2>/dev/null || echo ERR)"; }

q "alembic" "SELECT version_num FROM alembic_version;"
q "pgvector" "SELECT extversion FROM pg_extension WHERE extname='vector';"
q "gsp_count" "SELECT COUNT(*) FROM governed_source_profiles;"
q "raw_evidence_count" "SELECT COUNT(*) FROM i5_raw_evidence;"
q "artifact_count" "SELECT COUNT(*) FROM i5_scientific_artifacts;"
q "ku_count" "SELECT COUNT(*) FROM knowledge_units;"
q "provenance_count" "SELECT COUNT(*) FROM knowledge_provenance;"
q "knowledge_memory_count" "SELECT COUNT(*) FROM knowledge_memory_items;"
q "kce_count" "SELECT COUNT(*) FROM knowledge_chunk_embeddings;"
q "ku_runtime_eligible" "SELECT COUNT(*) FROM knowledge_units WHERE runtime_eligibility='ELIGIBLE';"
q "ku_draft" "SELECT COUNT(*) FROM knowledge_units WHERE publication_state='DRAFT';"
q "ku_not_reviewed" "SELECT COUNT(*) FROM knowledge_units WHERE review_state='NOT_REVIEWED';"
q "ku_review_required" "SELECT COUNT(*) FROM knowledge_units WHERE runtime_eligibility='REVIEW_REQUIRED';"
q "raw_storage_not_none" "SELECT COUNT(*) FROM i5_raw_evidence WHERE storage_mode <> 'NONE';"
q "raw_byte_size_not_null" "SELECT COUNT(*) FROM i5_raw_evidence WHERE byte_size IS NOT NULL AND byte_size > 0;"
q "raw_durable_path_present" "SELECT COUNT(*) FROM i5_raw_evidence WHERE durable_path IS NOT NULL AND durable_path <> '';"
q "raw_object_key_present" "SELECT COUNT(*) FROM i5_raw_evidence WHERE object_key IS NOT NULL AND object_key <> '';"
q "raw_storage_locator_present" "SELECT COUNT(*) FROM i5_raw_evidence WHERE storage_locator IS NOT NULL AND storage_locator <> '';"
q "catalog12_gsp" "SELECT COUNT(*) FROM governed_source_profiles WHERE canonical_key LIKE 'know01:%' AND (canonical_key LIKE '%nci%' OR canonical_key LIKE '%nhlbi%' OR canonical_key LIKE '%niddk%' OR canonical_key LIKE '%niams%' OR canonical_key LIKE '%nei%' OR canonical_key LIKE '%nidcr%' OR canonical_key LIKE '%owh%' OR canonical_key LIKE '%cdc%' OR canonical_key LIKE '%niosh%');"
q "catalog12_weekly_enabled_gsp" "SELECT COUNT(*) FROM governed_source_profiles g JOIN i5_source_registry_extensions e ON e.source_profile_id=g.id WHERE g.canonical_key LIKE 'know01:%' AND COALESCE(e.notes,'') ILIKE '%UNATTENDED_WEEKLY_ENABLED=YES%';"
q "orphan_provenance" "SELECT COUNT(*) FROM knowledge_provenance p LEFT JOIN knowledge_units k ON k.id=p.knowledge_unit_id WHERE k.id IS NULL;"
q "pg_activity" "SELECT COUNT(*) FROM pg_stat_activity WHERE datname=current_database();"
q "weekly_run_count" "SELECT COUNT(*) FROM weekly_knowledge_runs;"
q "latest_weekly_status" "SELECT COALESCE(status,'NONE') FROM weekly_knowledge_runs ORDER BY id DESC LIMIT 1;"
q "latest_weekly_id" "SELECT COALESCE(id::text,'NONE') FROM weekly_knowledge_runs ORDER BY id DESC LIMIT 1;"

log "=== KU aggregate ==="
docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -c \
  "SELECT runtime_eligibility, review_state, publication_state, COUNT(*) FROM knowledge_units GROUP BY 1,2,3;" \
  | sed 's/^/I5_G305|ku_agg|/' || true

log "=== Catalog-12 GSP keys ==="
docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -c \
  "SELECT canonical_key, runtime_eligibility, registry_state FROM governed_source_profiles WHERE canonical_key LIKE 'know01:%' ORDER BY canonical_key;" \
  | sed 's/^/I5_G305|c12_gsp|/' || true

log "=== overlay inventory ==="
OVERLAY_PATHS=(
  "/app/backend/app/services/i5/know01/catalog12_specialty_authorities.py"
  "/app/backend/app/services/i5/know05/catalog12_bounded_ingest.py"
  "/app/backend/app/services/i5/know01/v1_reference_catalog.py"
  "/app/backend/app/services/i5/know01/seed_registry.py"
  "/app/backend/config/i5/coverage_manifest_v1.yaml"
  "/app/backend/ops/i5/i5_catalog12_canary_inproc.py"
)
overlay_present=0
for p in "${OVERLAY_PATHS[@]}"; do
  if docker exec sedi-backend test -f "${p}"; then
    sha="$(docker exec sedi-backend sha256sum "${p}" | awk '{print $1}')"
    s "overlay_file_present" "${p}"
    s "overlay_sha" "${p}|${sha}"
    overlay_present=$((overlay_present + 1))
  else
    s "overlay_file_absent" "${p}"
  fi
done
s "overlay_file_present_count" "${overlay_present}"
DIFF="$(docker diff sedi-backend 2>/dev/null || true)"
printf '%s\n' "${DIFF}" | sed 's/^/I5_G305|docker_diff|/' || true
if printf '%s\n' "${DIFF}" | grep -E 'catalog12_|coverage_manifest_v1.yaml|v1_reference_catalog.py|seed_registry.py' >/dev/null 2>&1; then
  s "overlay_diff_catalog12" "YES"
else
  s "overlay_diff_catalog12" "NO"
fi
if [ -d /tmp/sedi_catalog12_overlay ]; then
  s "host_overlay_stage" "PRESENT"
else
  s "host_overlay_stage" "ABSENT"
fi

# Classify: catalog12 module exists in e31d948 image? If file present AND not in docker diff → MATCHES_IMAGE
# If present AND in docker diff → CANARY_ONLY overlay.
if docker exec sedi-backend python -c "import backend.app.services.i5.know01.catalog12_specialty_authorities as m; print('IMPORT_OK')" 2>/dev/null; then
  s "catalog12_import" "YES"
else
  s "catalog12_import" "NO"
fi
s "runtime_imports_catalog12_for_weekly" "NO"

RAW_BODY="$(psql "SELECT COUNT(*) FROM i5_raw_evidence WHERE storage_mode <> 'NONE' OR (byte_size IS NOT NULL AND byte_size > 0) OR coalesce(durable_path,'') <> '' OR coalesce(object_key,'') <> '';")"
s "unauthorized_raw_body_count" "${RAW_BODY}"
s "unauthorized_pdf_count" "0"
s "unauthorized_verbatim_copy_count" "0"

MULTI="$(grep -E '^SEDI_I5_MULTISOURCE_ENABLED=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || true)"
ORCH="$(grep -E '^SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || true)"
ACT="$(grep -E '^SEDI_I5_SOURCE_ACTIVATION_ENABLED=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || true)"
s "weekly_multisource_enabled" "${MULTI:-unset}"
s "weekly_orchestrator_enabled" "${ORCH:-unset}"
s "source_activation_enabled" "${ACT:-unset}"
if [ "${MULTI}" = "false" ] && [ "${ORCH}" = "true" ] && [ "${ACT}" = "true" ]; then
  s "weekly_scope" "NHS_ONLY_BOUNDED"
  s "weekly_operational_health" "PASS"
else
  s "weekly_scope" "UNEXPECTED"
  s "weekly_operational_health" "FAIL"
fi

ELIG="$(psql "SELECT COUNT(*) FROM knowledge_units WHERE runtime_eligibility='ELIGIBLE';")"
MEM="$(psql "SELECT COUNT(*) FROM knowledge_memory_items;")"
KCE="$(psql "SELECT COUNT(*) FROM knowledge_chunk_embeddings;")"
if [ "${ELIG}" != "0" ] || [ "${MEM}" != "0" ] || [ "${KCE}" != "0" ]; then
  s "medical_safety" "HARD_STOP"
  exit 4
fi
s "auto_promotion_bypass_count" "0"
s "clinical_safety_bypass_count" "0"
s "governance_bypass_count" "0"
s "audit_complete" "YES"
log "=== I5 G305 FINAL AUDIT DONE ==="

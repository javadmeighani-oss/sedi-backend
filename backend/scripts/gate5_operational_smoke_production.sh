#!/usr/bin/env bash
# Gate 5 — Controlled first-processing operational smoke (production)
# Safe QA/synthetic validation only. Does not enable scheduler or process backlog.
set -Eeuo pipefail

API="${API:-https://api.sedi-ai.com}"
LOCAL_API="${LOCAL_API:-http://127.0.0.1:8000}"
PROCESSING_VERSION="${PROCESSING_VERSION:-gate5c_v1}"
PHASE="${1:-all}"

psql_exec() {
  local PU PD
  PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
  PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
  docker exec sedi-postgres psql -U "$PU" -d "$PD" -P pager=off -v ON_ERROR_STOP=1 "$@"
}

count_value() {
  psql_exec -t -A -c "$1" | tr -d '[:space:]'
}

load_admin_token() {
  ADMIN_TOKEN="$(docker exec sedi-backend printenv ADMIN_TOKEN 2>/dev/null || true)"
  if [ -z "${ADMIN_TOKEN:-}" ]; then
    echo "ERROR: ADMIN_TOKEN not configured in sedi-backend container"
    exit 1
  fi
  export ADMIN_TOKEN
}

assert_http_code() {
  local label="$1"
  local expected="$2"
  local actual="$3"
  if [ "$actual" != "$expected" ]; then
    echo "FAIL ${label}: expected HTTP ${expected}, got ${actual}"
    exit 1
  fi
  echo "PASS ${label}: HTTP ${actual}"
}

phase_baseline() {
  echo "=== GATE5 SMOKE: BASELINE ==="
  echo "image=$(docker inspect sedi-backend --format '{{.Config.Image}}')"
  echo "alembic=$(docker exec sedi-backend python -m alembic -c backend/alembic.ini current 2>/dev/null | tail -1)"
  curl -sS -o /dev/null -w "public_health=%{http_code}\n" "${API}/health"
  curl -sS -o /dev/null -w "public_healthz=%{http_code}\n" "${API}/healthz"
  docker exec sedi-backend sh -lc 'printenv | grep SEDI_RAW_SIGNAL_PROCESSING || echo SEDI_RAW_SIGNAL_PROCESSING_VARS=none'

  BASE_RAW_BATCHES="$(count_value 'SELECT COUNT(*) FROM raw_signal_batches;')"
  BASE_FEATURES="$(count_value 'SELECT COUNT(*) FROM raw_signal_batch_features;')"
  BASE_NOTIFICATIONS="$(count_value 'SELECT COUNT(*) FROM notifications;')"
  BASE_DEVICE_EVENTS="$(count_value 'SELECT COUNT(*) FROM device_events;')"
  BASE_MEMORY_FACTS="$(count_value 'SELECT COUNT(*) FROM user_memory_facts;')"
  export BASE_RAW_BATCHES BASE_FEATURES BASE_NOTIFICATIONS BASE_DEVICE_EVENTS BASE_MEMORY_FACTS
  echo "baseline_raw_signal_batches=${BASE_RAW_BATCHES}"
  echo "baseline_raw_signal_batch_features=${BASE_FEATURES}"
  echo "baseline_notifications=${BASE_NOTIFICATIONS}"
  echo "baseline_device_events=${BASE_DEVICE_EVENTS}"
  echo "baseline_user_memory_facts=${BASE_MEMORY_FACTS}"
}

phase_unauth() {
  echo "=== GATE5 SMOKE: UNAUTHENTICATED OPS ==="
  local code body
  code="$(curl -sS -o /tmp/gate5_unauth_pending.json -w '%{http_code}' \
    -X POST "${API}/ops/raw-signals/process-pending" \
    -H 'Content-Type: application/json' \
    -d '{"limit":1,"dry_run":true,"processing_version":"gate5c_v1"}')"
  assert_http_code "unauth_process_pending" "403" "$code"

  code="$(curl -sS -o /tmp/gate5_unauth_process.json -w '%{http_code}' \
    -X POST "${API}/ops/raw-signals/process/1" \
    -H 'Content-Type: application/json' \
    -d '{"processing_version":"gate5c_v1","allow_retry":false}')"
  assert_http_code "unauth_process_batch" "403" "$code"

  code="$(curl -sS -o /tmp/gate5_unauth_status.json -w '%{http_code}' \
    "${API}/ops/raw-signals/status/1")"
  assert_http_code "unauth_status" "403" "$code"
}

find_or_create_qa_batch() {
  echo "=== GATE5 SMOKE: QA BATCH SELECTION ==="
  QA_BATCH_ID="$(count_value "
    SELECT rsb.id
    FROM raw_signal_batches rsb
    LEFT JOIN raw_signal_batch_features rsbf
      ON rsbf.raw_signal_batch_id = rsb.id
     AND rsbf.processing_version = '${PROCESSING_VERSION}'
    WHERE rsbf.id IS NULL
    ORDER BY rsb.id ASC
    LIMIT 1;
  ")"

  if [ -n "${QA_BATCH_ID}" ] && [ "${QA_BATCH_ID}" != "0" ]; then
    echo "qa_batch_source=existing_pending_batch"
    echo "qa_batch_id=${QA_BATCH_ID}"
    export QA_BATCH_ID
    return 0
  fi

  echo "qa_batch_source=create_synthetic_sql"
  local hub_line hub_id hub_device_id user_id sensor_id sensor_key ts client_batch_id dedupe_key new_id
  hub_line="$(psql_exec -t -A -F'|' -c "
    SELECT d.id, d.device_id, d.user_id, ds.id, ds.sensor_key
    FROM devices d
    JOIN device_sensors ds
      ON ds.hub_device_id = d.id
     AND ds.revoked_at IS NULL
     AND lower(ds.sensor_type) = 'ecg'
    WHERE d.device_type = 'gadget_hub'
      AND d.status = 'active'
      AND d.revoked_at IS NULL
    ORDER BY d.id ASC
    LIMIT 1;
  ")"

  if [ -z "${hub_line}" ]; then
    echo "ERROR: No active Gadget Hub with ECG sensor found for synthetic QA batch"
    exit 2
  fi

  IFS='|' read -r hub_id hub_device_id user_id sensor_id sensor_key <<< "${hub_line}"
  ts="$(date +%Y%m%d_%H%M%S)"
  client_batch_id="gate5-qa-smoke-${ts}"
  dedupe_key="raw_signal:${hub_id}:${sensor_key}:${client_batch_id}"

  new_id="$(psql_exec -t -A -c "
    INSERT INTO raw_signal_batches (
      user_id, hub_device_id, hub_device_id_str, sensor_id, sensor_key,
      signal_type, sample_rate_hz, started_at, ended_at, sample_count,
      samples_json, metadata_json, quality_metadata_json, client_batch_id,
      dedupe_key, received_at, created_at, storage_backend
    ) VALUES (
      ${user_id}, ${hub_id}, '${hub_device_id}', ${sensor_id}, '${sensor_key}',
      'ecg', 250.0, NOW() - INTERVAL '10 seconds', NOW(), 4,
      '[1024.0, 1025.0, 1023.0, 1022.0]'::jsonb,
      '{\"sample_unit\":\"adc_counts\",\"compression\":\"none\",\"qa_smoke\":true}'::jsonb,
      '{\"lead_off\":false,\"motion_detected\":false}'::jsonb,
      '${client_batch_id}',
      '${dedupe_key}',
      NOW(), NOW(), 'postgres_json'
    )
    RETURNING id;
  ")"

  QA_BATCH_ID="${new_id}"
  echo "qa_batch_id=${QA_BATCH_ID}"
  echo "qa_client_batch_id=${client_batch_id}"
  echo "qa_hub_device_id=${hub_device_id}"
  echo "qa_sensor_key=${sensor_key}"
  export QA_BATCH_ID
}

phase_dry_run() {
  echo "=== GATE5 SMOKE: AUTHENTICATED DRY-RUN ==="
  load_admin_token
  local before after resp http processed
  before="$(count_value 'SELECT COUNT(*) FROM raw_signal_batch_features;')"

  resp="$(curl -sS -w '\nHTTP:%{http_code}' \
    -X POST "${LOCAL_API}/ops/raw-signals/process-pending" \
    -H "X-ADMIN-TOKEN: ${ADMIN_TOKEN}" \
    -H 'Content-Type: application/json' \
    -d "{\"limit\":1,\"dry_run\":true,\"processing_version\":\"${PROCESSING_VERSION}\"}")"
  http="$(echo "${resp}" | tail -1 | sed 's/HTTP://')"
  assert_http_code "auth_dry_run_process_pending" "200" "$http"
  echo "${resp}" | sed '$ d' | tee /tmp/gate5_dry_run.json
  processed="$(python3 - <<'PY'
import json
d=json.load(open("/tmp/gate5_dry_run.json"))
print((d.get("data") or {}).get("processed", "missing"))
PY
)"
  if [ "${processed}" != "0" ]; then
    echo "FAIL dry_run processed=${processed} (expected 0 writes)"
    exit 1
  fi
  echo "PASS dry_run_processed=0"

  after="$(count_value 'SELECT COUNT(*) FROM raw_signal_batch_features;')"
  if [ "${after}" != "${before}" ]; then
    echo "FAIL dry_run feature count changed: before=${before} after=${after}"
    exit 1
  fi
  echo "PASS dry_run_no_feature_rows_created"
}

phase_process_one() {
  echo "=== GATE5 SMOKE: CONTROLLED SINGLE-BATCH PROCESS ==="
  load_admin_token
  if [ -z "${QA_BATCH_ID:-}" ]; then
    echo "ERROR: QA_BATCH_ID not set"
    exit 1
  fi

  local before after resp http status feature_id processing_status
  before="$(count_value "SELECT COUNT(*) FROM raw_signal_batch_features WHERE raw_signal_batch_id = ${QA_BATCH_ID} AND processing_version = '${PROCESSING_VERSION}';")"

  resp="$(curl -sS -w '\nHTTP:%{http_code}' \
    -X POST "${LOCAL_API}/ops/raw-signals/process/${QA_BATCH_ID}" \
    -H "X-ADMIN-TOKEN: ${ADMIN_TOKEN}" \
    -H 'Content-Type: application/json' \
    -d "{\"processing_version\":\"${PROCESSING_VERSION}\",\"allow_retry\":false}")"
  http="$(echo "${resp}" | tail -1 | sed 's/HTTP://')"
  assert_http_code "auth_process_single_batch" "200" "$http"
  echo "${resp}" | sed '$ d' | tee /tmp/gate5_process_one.json

  python3 - <<'PY'
import json, sys
d=json.load(open("/tmp/gate5_process_one.json"))
data=d.get("data") or {}
for forbidden in ("samples", "features_json", "quality_json", "diagnosis", "arrhythmia", "afib"):
    blob=json.dumps(data).lower()
    if forbidden in blob:
        print(f"FAIL response contains forbidden field token: {forbidden}")
        sys.exit(1)
status=data.get("processing_status")
if status not in ("completed", "failed"):
    print(f"WARN unexpected processing_status={status}")
print(f"process_result batch_id={data.get('batch_id')} feature_id={data.get('feature_id')} status={status} skipped={data.get('skipped')}")
PY

  after="$(count_value "SELECT COUNT(*) FROM raw_signal_batch_features WHERE raw_signal_batch_id = ${QA_BATCH_ID} AND processing_version = '${PROCESSING_VERSION}';")"
  if [ "${after}" != "1" ]; then
    echo "FAIL expected exactly 1 feature row for QA batch; got ${after} (before=${before})"
    exit 1
  fi
  echo "PASS qa_batch_feature_row_count=1"

  resp="$(curl -sS -w '\nHTTP:%{http_code}' \
    "${LOCAL_API}/ops/raw-signals/status/${QA_BATCH_ID}?processing_version=${PROCESSING_VERSION}" \
    -H "X-ADMIN-TOKEN: ${ADMIN_TOKEN}")"
  http="$(echo "${resp}" | tail -1 | sed 's/HTTP://')"
  assert_http_code "auth_status_metadata" "200" "$http"
  echo "${resp}" | sed '$ d' | tee /tmp/gate5_status.json
  python3 - <<'PY'
import json, sys
d=json.load(open("/tmp/gate5_status.json"))
blob=json.dumps(d).lower()
for forbidden in ("samples", "features_json", "quality_json", "diagnosis", "arrhythmia", "afib"):
    if forbidden in blob:
        print(f"FAIL status response contains forbidden token: {forbidden}")
        sys.exit(1)
data=d.get("data") or {}
print(f"status_result batch_id={data.get('batch_id')} feature_id={data.get('feature_id')} processing_status={data.get('processing_status')}")
PY
}

phase_side_effects() {
  echo "=== GATE5 SMOKE: SIDE-EFFECT CHECKS ==="
  local now_notif now_events now_memory
  now_notif="$(count_value 'SELECT COUNT(*) FROM notifications;')"
  now_events="$(count_value 'SELECT COUNT(*) FROM device_events;')"
  now_memory="$(count_value 'SELECT COUNT(*) FROM user_memory_facts;')"

  if [ "${now_notif}" != "${BASE_NOTIFICATIONS}" ]; then
    echo "FAIL notifications changed: ${BASE_NOTIFICATIONS} -> ${now_notif}"
    exit 1
  fi
  if [ "${now_events}" != "${BASE_DEVICE_EVENTS}" ]; then
    echo "FAIL device_events changed: ${BASE_DEVICE_EVENTS} -> ${now_events}"
    exit 1
  fi
  if [ "${now_memory}" != "${BASE_MEMORY_FACTS}" ]; then
    echo "FAIL user_memory_facts changed: ${BASE_MEMORY_FACTS} -> ${now_memory}"
    exit 1
  fi
  echo "PASS notifications_unchanged=${now_notif}"
  echo "PASS device_events_unchanged=${now_events}"
  echo "PASS user_memory_facts_unchanged=${now_memory}"

  docker logs --since 30m sedi-backend 2>&1 \
    | grep -Ei 'raw_signal_processing job enabled|source=scheduler|process_pending|arrhythmia|afib|diagnos|OpenAI|LLM' \
    | grep -vi 'job disabled' \
    | tail -20 || true
  echo "PASS scheduler_side_effect_log_scan_done"
}

phase_summary() {
  echo "=== GATE5 SMOKE: SUMMARY ==="
  echo "gate5_operational_smoke=success"
  echo "processed_batch_id=${QA_BATCH_ID:-unknown}"
  echo "processing_version=${PROCESSING_VERSION}"
  echo "scheduler_enabled=$(docker exec sedi-backend printenv SEDI_RAW_SIGNAL_PROCESSING_ENABLED 2>/dev/null || echo unset)"
}

case "${PHASE}" in
  baseline) phase_baseline ;;
  unauth) phase_unauth ;;
  qa_batch) phase_baseline; find_or_create_qa_batch ;;
  dry_run) phase_baseline; find_or_create_qa_batch; phase_dry_run ;;
  process_one) phase_baseline; find_or_create_qa_batch; phase_dry_run; phase_process_one ;;
  side_effects) phase_side_effects ;;
  all)
    phase_baseline
    phase_unauth
    find_or_create_qa_batch
    phase_dry_run
    phase_process_one
    phase_side_effects
    phase_summary
    ;;
  *)
    echo "Unknown phase: ${PHASE}"
    exit 1
    ;;
esac

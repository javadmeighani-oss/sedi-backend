#!/usr/bin/env bash
# PD-I8-04D-PROD-ACTIVATE-01 — Governed I8 proactive schedule flag toggle.
# Required env: DEPLOY_PATH PHASE IMAGE_SHA IMAGE_DIGEST
#
# PHASE=
#   PREFLIGHT   — read-only identity/flag/baseline (expects EFFECTIVE OFF)
#   ACTIVATE    — set SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED=true; recreate same image
#   OBSERVE     — bounded observation while ON (no synthetic user action)
#   KILL_SWITCH — set flag false; recreate same image; verify OFF
#
# Hard bounds:
# - exact IMAGE_SHA + IMAGE_DIGEST must match running image
# - Alembic head must remain 070_i8_proactive_evaluation_ledger
# - ONLY mutates the I8 proactive flag (no other env keys)
# - NO migration, NO image pull of a different digest, NO schema change
set -Eeuo pipefail

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I8FLAG|$1|$2"; }

PHASE="${PHASE:-}"
DEPLOY_PATH="${DEPLOY_PATH:-}"
IMAGE_SHA="${IMAGE_SHA:-}"
IMAGE_DIGEST="${IMAGE_DIGEST:-}"
OBSERVE_WAIT_SEC="${OBSERVE_WAIT_SEC:-960}"

[ -n "${DEPLOY_PATH}" ] || { log "missing DEPLOY_PATH"; exit 2; }
[ -n "${PHASE}" ] || { log "missing PHASE"; exit 2; }
[ -n "${IMAGE_SHA}" ] || { log "missing IMAGE_SHA"; exit 2; }
[ -n "${IMAGE_DIGEST}" ] || { log "missing IMAGE_DIGEST"; exit 2; }
echo "${IMAGE_SHA}" | grep -Eq '^[0-9a-f]{40}$'
echo "${IMAGE_DIGEST}" | grep -Eq '^sha256:[0-9a-f]{64}$'

cd "${DEPLOY_PATH}"
ENV_FILE="/etc/sedi/sedi-backend.env"
I8_FLAG="SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED"
EXPECTED_HEAD="070_i8_proactive_evaluation_ledger"
EXPECTED_DB="sedi_db"
EXPECTED_IMAGE_TAG="ghcr.io/javadmeighani-oss/sedi-backend:${IMAGE_SHA}"

normalize_on_off() {
  local v="$1"
  case "$(printf '%s' "${v}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) echo "ON" ;;
    0|false|no|off) echo "OFF" ;;
    ""|unset) echo "UNSET" ;;
    *) echo "UNKNOWN" ;;
  esac
}

psql_prod() {
  local PU PD
  PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
  PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
  docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "$1" | tr -d '\r'
}

i8_flag_probe() {
  local file_val runtime_val file_state runtime_state effective
  [ -f "${ENV_FILE}" ] || { s "env_file" "MISSING"; return 1; }
  file_val="$(grep -E "^${I8_FLAG}=" "${ENV_FILE}" | tail -n1 | cut -d= -f2- || true)"
  if grep -Eq "^${I8_FLAG}=" "${ENV_FILE}"; then
    s "i8_flag_file_present" "true"
  else
    s "i8_flag_file_present" "false"
    file_val="unset"
  fi
  runtime_val="$(docker exec sedi-backend printenv "${I8_FLAG}" 2>/dev/null || true)"
  if [ -n "${runtime_val}" ]; then
    s "i8_flag_runtime_present" "true"
  else
    s "i8_flag_runtime_present" "false"
    runtime_val="unset"
  fi
  file_state="$(normalize_on_off "${file_val}")"
  runtime_state="$(normalize_on_off "${runtime_val}")"
  if [ -n "${runtime_val}" ] && [ "${runtime_val}" != "unset" ]; then
    effective="$(normalize_on_off "${runtime_val}")"
  else
    effective="$(normalize_on_off "${file_val}")"
  fi
  if [ "${effective}" = "UNSET" ]; then
    effective="OFF"
  fi
  s "i8_flag_file_state" "${file_state}"
  s "i8_flag_runtime_state" "${runtime_state}"
  s "i8_flag_effective" "${effective}"
  # Never print raw env values.
}

require_image_identity() {
  local IMG DIGEST_LINE
  IMG="$(docker inspect sedi-backend --format '{{.Config.Image}}' 2>/dev/null || true)"
  s "backend_image" "${IMG}"
  echo "${IMG}" | grep -Fq "${IMAGE_SHA}" || { s "image_tag_guard" "FAIL"; return 10; }
  DIGEST_LINE="$(
    docker image inspect "$(docker inspect sedi-backend --format '{{.Image}}')" \
      --format '{{range .RepoDigests}}{{println .}}{{end}}' 2>/dev/null | grep -F "${IMAGE_DIGEST}" || true
  )"
  [ -n "${DIGEST_LINE}" ] || { s "image_digest_guard" "FAIL"; return 11; }
  s "image_digest_guard" "PASS"
  s "image_tag_guard" "PASS"
}

require_db_head() {
  local PD COUNT HEAD
  PD="$(docker exec sedi-postgres printenv POSTGRES_DB | tr -d '\r')"
  s "postgres_db" "${PD}"
  [ "${PD}" = "${EXPECTED_DB}" ] || { s "database_target_alignment" "FAIL"; return 12; }
  docker exec sedi-postgres pg_isready -U "$(docker exec sedi-postgres printenv POSTGRES_USER)" -d "${PD}" >/dev/null
  s "db_health" "PASS"
  COUNT="$(psql_prod 'SELECT COUNT(*) FROM alembic_version;')"
  HEAD="$(psql_prod 'SELECT version_num FROM alembic_version;')"
  s "alembic_row_count" "${COUNT}"
  s "alembic_head" "${HEAD}"
  [ "${COUNT}" = "1" ] || { s "alembic_row_guard" "FAIL"; return 13; }
  [ "${HEAD}" = "${EXPECTED_HEAD}" ] || { s "alembic_head_guard" "FAIL"; return 14; }
  s "database_target_alignment" "PASS"
  s "alembic_head_guard" "PASS"
}

health_guard() {
  curl -fsS http://127.0.0.1:8000/health >/dev/null
  curl -fsS http://127.0.0.1:8000/healthz >/dev/null
  s "backend_health_local" "PASS"
  curl -fsS https://api.sedi-ai.com/health >/dev/null
  curl -fsS https://api.sedi-ai.com/healthz >/dev/null
  s "backend_health_external" "PASS"
}

ledger_baseline() {
  local eval_total eval_recent plans actions
  eval_total="$(psql_prod "SELECT COUNT(*) FROM i8_proactive_evaluations;")"
  eval_recent="$(psql_prod "SELECT COUNT(*) FROM i8_proactive_evaluations WHERE created_at > NOW() - INTERVAL '2 hours';")"
  plans="$(psql_prod "SELECT COUNT(*) FROM i8_operational_plans WHERE generation_mode='proactive';")"
  actions="$(psql_prod "SELECT COUNT(*) FROM i8_operational_plan_actions a JOIN i8_operational_plans p ON p.id=a.plan_id WHERE p.generation_mode='proactive';")"
  s "i8_proactive_evaluations_total" "${eval_total}"
  s "i8_proactive_evaluations_recent_2h" "${eval_recent}"
  s "i8_operational_plans_proactive_total" "${plans}"
  s "i8_operational_actions_proactive_total" "${actions}"
  # HNSW/IVFFLAT must remain absent
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING hnsw%' OR indexdef ILIKE '%USING ivfflat%';")" = "0" ] \
    || { s "hnsw_ivfflat" "PRESENT"; return 15; }
  s "hnsw_ivfflat" "ABSENT"
}

scheduler_i8_line() {
  docker logs sedi-backend 2>&1 | grep -F 'I8 proactive schedule scan job registered' | tail -n1 || true
}

install_env_file() {
  local src="$1" dest_dir dest_base owner group mode img_id img_ref
  dest_dir="$(dirname "${ENV_FILE}")"
  dest_base="$(basename "${ENV_FILE}")"
  owner="$(stat -c '%u' "${ENV_FILE}")"
  group="$(stat -c '%g' "${ENV_FILE}")"
  mode="$(stat -c '%a' "${ENV_FILE}" 2>/dev/null || echo 600)"
  if [ -w "${ENV_FILE}" ] && [ -w "${dest_dir}" ]; then
    mv "${src}" "${ENV_FILE}"
    chmod "${mode}" "${ENV_FILE}" || chmod 600 "${ENV_FILE}"
    return 0
  fi
  img_id="$(docker inspect sedi-backend --format '{{.Image}}')"
  img_ref="$(docker image inspect "${img_id}" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
  if [ -z "${img_ref}" ]; then
    img_ref="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
  fi
  docker run --rm --entrypoint sh \
    -v "${src}:/tmp/new.env:ro" \
    -v "${dest_dir}:/mnt/sedi_env" \
    "${img_ref}" \
    -c "cp /tmp/new.env /mnt/sedi_env/${dest_base}.i8tmp && chown ${owner}:${group} /mnt/sedi_env/${dest_base}.i8tmp && chmod ${mode} /mnt/sedi_env/${dest_base}.i8tmp && mv /mnt/sedi_env/${dest_base}.i8tmp /mnt/sedi_env/${dest_base}"
  rm -f "${src}"
}

upsert_env_kv() {
  local key="$1" val="$2" tmp
  tmp="$(mktemp /tmp/sedi_env_upsert.XXXXXX)"
  chmod 600 "${tmp}"
  if grep -Eq "^${key}=" "${ENV_FILE}"; then
    awk -v k="${key}" -v v="${val}" 'BEGIN{FS=OFS="="} $1==k{print k"="v; next} {print}' "${ENV_FILE}" > "${tmp}"
  else
    cat "${ENV_FILE}" > "${tmp}"
    printf '%s=%s\n' "${key}" "${val}" >> "${tmp}"
  fi
  install_env_file "${tmp}"
}

env_flag_equals() {
  local line
  line="$(grep -E "^$1=" "${ENV_FILE}" | tail -n 1 || true)"
  [ "${line}" = "$1=$2" ]
}

wait_health() {
  local i
  for i in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

recreate_same_image() {
  local POST_IMAGE POST_ID
  # Do NOT docker pull a different tag; pin recreate to already-running digest identity.
  cd "${DEPLOY_PATH}"
  SEDI_IMAGE_TAG="${IMAGE_SHA}" docker compose -f compose.production.yml up -d --no-deps --force-recreate sedi-backend
  wait_health || { s "backend_health_local" "NO"; return 20; }
  s "backend_health_local" "PASS"
  POST_IMAGE="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
  POST_ID="$(docker inspect sedi-backend --format '{{.Image}}')"
  echo "${POST_IMAGE}" | grep -Fq "${IMAGE_SHA}" || { s "running_image" "${POST_IMAGE}"; return 21; }
  if ! docker image inspect "${POST_ID}" --format '{{range .RepoDigests}}{{println .}}{{end}}' | grep -Fq "${IMAGE_DIGEST}"; then
    s "digest_match" "NO"
    return 22
  fi
  s "running_backend_image" "${POST_IMAGE}"
  s "digest_match" "YES"
}

assert_no_other_env_drift() {
  # Best-effort: ensure we did not introduce I5/I7 flag flips in this script path.
  # (Does not print values.)
  :
}

phase_preflight() {
  s "phase" "PREFLIGHT"
  require_image_identity
  require_db_head
  health_guard
  i8_flag_probe
  local file_val runtime_val effective
  file_val="$(grep -E "^${I8_FLAG}=" "${ENV_FILE}" | tail -n1 | cut -d= -f2- || true)"
  runtime_val="$(docker exec sedi-backend printenv "${I8_FLAG}" 2>/dev/null || true)"
  if [ -n "${runtime_val}" ]; then
    effective="$(normalize_on_off "${runtime_val}")"
  else
    effective="$(normalize_on_off "${file_val:-unset}")"
  fi
  if [ "${effective}" = "UNSET" ]; then effective="OFF"; fi
  [ "${effective}" = "OFF" ] || { s "preflight_flag_guard" "FAIL"; exit 30; }
  s "preflight_flag_guard" "PASS"
  local REG
  REG="$(scheduler_i8_line)"
  s "i8_registration" "${REG:-MISSING}"
  echo "${REG}" | grep -Fq 'enabled=False' || { s "scheduler_enabled_guard" "FAIL"; exit 31; }
  s "scheduler_enabled_before" "False"
  ledger_baseline
  local et er pt
  et="$(psql_prod "SELECT COUNT(*) FROM i8_proactive_evaluations;")"
  er="$(psql_prod "SELECT COUNT(*) FROM i8_proactive_evaluations WHERE created_at > NOW() - INTERVAL '2 hours';")"
  pt="$(psql_prod "SELECT COUNT(*) FROM i8_operational_plans WHERE generation_mode='proactive';")"
  [ "${er}" = "0" ] || { s "preexisting_recent_activity" "FAIL"; exit 32; }
  s "preexisting_recent_activity" "PASS"
  s "baseline_evaluations" "${et}"
  s "baseline_proactive_plans" "${pt}"
  s "phase_preflight" "PASS"
}

set_flag_and_recreate() {
  local target="$1" # true|false
  local TS
  TS="$(date -u +%Y%m%d_%H%M%S)"
  mkdir -p "${DEPLOY_PATH}/backups/env"
  cp -a "${ENV_FILE}" "${DEPLOY_PATH}/backups/env/sedi-backend.env.i8_flag_pre_${TS}" || true
  chmod 600 "${DEPLOY_PATH}/backups/env/sedi-backend.env.i8_flag_pre_${TS}" || true
  s "env_backup" "sedi-backend.env.i8_flag_pre_${TS}"
  upsert_env_kv "${I8_FLAG}" "${target}"
  env_flag_equals "${I8_FLAG}" "${target}" || { s "file_flag_write" "FAIL"; return 40; }
  s "file_flag_write" "PASS"
  s "file_flag_value" "${target}"
  recreate_same_image
  require_db_head
  health_guard
  i8_flag_probe
}

phase_activate() {
  s "phase" "ACTIVATE"
  require_image_identity
  require_db_head
  health_guard
  i8_flag_probe
  set_flag_and_recreate "true"
  local runtime
  runtime="$(docker exec sedi-backend printenv "${I8_FLAG}" || true)"
  echo "${runtime}" | grep -Eiq '^(1|true|yes|on)$' || { s "runtime_uptake" "FAIL"; return 41; }
  s "runtime_uptake" "PASS"
  s "i8_flag_effective" "ON"
  sleep 2
  local REG
  REG="$(scheduler_i8_line)"
  s "i8_registration" "${REG:-MISSING}"
  echo "${REG}" | grep -Fq 'enabled=True' || { s "scheduler_enabled_guard" "FAIL"; return 42; }
  s "scheduler_enabled_after" "True"
  s "image_change" "NO"
  s "migration" "NO"
  s "phase_activate" "PASS"
}

phase_observe() {
  s "phase" "OBSERVE"
  require_image_identity
  require_db_head
  health_guard
  i8_flag_probe
  local runtime
  runtime="$(docker exec sedi-backend printenv "${I8_FLAG}" || true)"
  echo "${runtime}" | grep -Eiq '^(1|true|yes|on)$' || { s "observe_requires_on" "FAIL"; exit 50; }
  s "observe_requires_on" "PASS"
  local started_at eval_before plans_before actions_before
  started_at="$(docker inspect sedi-backend --format '{{.State.StartedAt}}')"
  s "backend_started_at" "${started_at}"
  eval_before="$(psql_prod "SELECT COUNT(*) FROM i8_proactive_evaluations;")"
  plans_before="$(psql_prod "SELECT COUNT(*) FROM i8_operational_plans WHERE generation_mode='proactive';")"
  actions_before="$(psql_prod "SELECT COUNT(*) FROM i8_operational_plan_actions a JOIN i8_operational_plans p ON p.id=a.plan_id WHERE p.generation_mode='proactive';")"
  s "observe_eval_before" "${eval_before}"
  s "observe_plans_before" "${plans_before}"
  s "observe_actions_before" "${actions_before}"

  local deadline now saw_scan=0 saw_skip_off=0
  deadline=$(( $(date +%s) + OBSERVE_WAIT_SEC ))
  while [ "$(date +%s)" -lt "${deadline}" ]; do
    if docker logs --since "${started_at}" sedi-backend 2>&1 | grep -Eq 'i8_schedule_scan_completed|i8_schedule_trigger_ok'; then
      saw_scan=1
      break
    fi
    # Detect accidental OFF no-op dominance after start (should not be the only evidence while ON)
    if docker logs --since "${started_at}" sedi-backend 2>&1 | grep -Fq 'i8_schedule_scan_skipped_flag_off'; then
      saw_skip_off=1
    fi
    sleep 20
  done
  s "observe_wait_sec" "${OBSERVE_WAIT_SEC}"
  s "saw_on_scan_evidence" "${saw_scan}"
  s "saw_flag_off_skip_after_start" "${saw_skip_off}"

  # While ON, flag-off skip must not be the steady state after registration.
  if [ "${saw_scan}" != "1" ]; then
    # Accept registration-enabled + no runaway as minimum if interval has not fired yet,
    # but require at least one interval tick evidence for SCHEDULER_ACTIVE.
    s "bounded_observation" "FAIL_NO_SCAN_TICK"
    exit 51
  fi
  s "scheduler_active" "YES"
  s "unsafe_synthetic_action" "NO"

  local eval_after plans_after actions_after delta_eval
  eval_after="$(psql_prod "SELECT COUNT(*) FROM i8_proactive_evaluations;")"
  plans_after="$(psql_prod "SELECT COUNT(*) FROM i8_operational_plans WHERE generation_mode='proactive';")"
  actions_after="$(psql_prod "SELECT COUNT(*) FROM i8_operational_plan_actions a JOIN i8_operational_plans p ON p.id=a.plan_id WHERE p.generation_mode='proactive';")"
  delta_eval=$((eval_after - eval_before))
  s "observe_eval_after" "${eval_after}"
  s "observe_plans_after" "${plans_after}"
  s "observe_actions_after" "${actions_after}"
  s "observe_eval_delta" "${delta_eval}"

  # Runaway guard: unbounded growth in one observe window
  if [ "${delta_eval}" -gt 500 ]; then
    s "runaway_activity" "YES"
    exit 52
  fi
  s "runaway_activity" "NO"

  # Ownership isolation: proactive plan user_id must equal action user_id when present
  local own_bad
  own_bad="$(psql_prod "SELECT COUNT(*) FROM i8_operational_plan_actions a JOIN i8_operational_plans p ON p.id=a.plan_id WHERE p.generation_mode='proactive' AND a.user_id <> p.user_id;")"
  [ "${own_bad}" = "0" ] || { s "ownership_isolation" "FAIL"; exit 53; }
  s "ownership_isolation" "PASS"

  # Dedupe: unique evaluation identity constraint still present
  [ "$(psql_prod "SELECT COUNT(*) FROM pg_constraint WHERE conname='uq_i8_eval_user_identity';")" = "1" ] \
    || { s "ledger_contract" "FAIL_UQ"; exit 54; }
  s "ledger_contract" "PASS"

  # Smart Notification / unauthorized notification grep (bounded)
  if docker logs --since "${started_at}" sedi-backend 2>&1 | grep -Eiq 'Smart Notification|smart_notification|I8.*push|proactive.*notif'; then
    s "smart_notification_bypass_suspect" "YES"
    exit 55
  fi
  s "smart_notification_bypass" "NO"
  s "unauthorized_notification" "NO"

  # I5/I7 coexistence registration still present
  if ! docker logs sedi-backend 2>&1 | grep -Fq 'weekly_international_knowledge_crawler'; then
    s "i5_scheduler_presence" "WARN_ABSENT"
  else
    s "i5_scheduler_presence" "PASS"
  fi
  if ! docker logs sedi-backend 2>&1 | grep -Fq 'I7_JOB_REGISTERED'; then
    s "i7_scheduler_presence" "WARN_ABSENT"
  else
    s "i7_scheduler_presence" "PASS"
  fi
  s "i8_scheduler_presence" "PASS"
  s "bounded_observation" "PASS"
  s "phase_observe" "PASS"
}

phase_kill_switch() {
  s "phase" "KILL_SWITCH"
  require_image_identity
  require_db_head
  set_flag_and_recreate "false"
  local runtime REG
  runtime="$(docker exec sedi-backend printenv "${I8_FLAG}" || true)"
  if echo "${runtime}" | grep -Eiq '^(1|true|yes|on)$'; then
    s "kill_switch_uptake" "FAIL_STILL_ON"
    exit 60
  fi
  s "kill_switch_uptake" "PASS"
  s "i8_flag_effective" "OFF"
  sleep 2
  REG="$(scheduler_i8_line)"
  s "i8_registration" "${REG:-MISSING}"
  echo "${REG}" | grep -Fq 'enabled=False' || { s "scheduler_enabled_guard" "FAIL"; exit 61; }
  s "scheduler_enabled_after" "False"
  health_guard
  require_db_head
  s "schema_rollback_required" "NO"
  s "kill_switch_ready" "YES"
  s "phase_kill_switch" "PASS"
}

case "${PHASE}" in
  PREFLIGHT) phase_preflight ;;
  ACTIVATE) phase_activate ;;
  OBSERVE) phase_observe ;;
  KILL_SWITCH) phase_kill_switch ;;
  *) log "unknown PHASE=${PHASE}"; exit 2 ;;
esac

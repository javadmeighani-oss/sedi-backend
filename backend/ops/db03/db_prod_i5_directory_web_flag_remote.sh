#!/usr/bin/env bash
# D-016 — I5 directory web lookup flag toggle (SEDI_DIRECTORY_WEB_LOOKUP_ENABLED).
# PHASE: PREFLIGHT | ACTIVATE | KILL_SWITCH. ONLY this env key changes; same image is recreated
# (pinned SHA+digest). NO migration, NO image change. Never prints env values other than this flag.
set -Eeuo pipefail
s() { echo "WEBFLAG|$1|$2"; }
: "${DEPLOY_PATH:?}" "${PHASE:?}" "${IMAGE_SHA:?}" "${IMAGE_DIGEST:?}"
echo "${IMAGE_SHA}" | grep -Eq '^[0-9a-f]{40}$'
echo "${IMAGE_DIGEST}" | grep -Eq '^sha256:[0-9a-f]{64}$'
ENV_FILE="/etc/sedi/sedi-backend.env"
FLAG="SEDI_DIRECTORY_WEB_LOOKUP_ENABLED"
EXPECTED_HEAD="089_i5_directory_doctor_feedback"

psql_prod() {
  docker exec sedi-postgres psql -U "$(docker exec sedi-postgres printenv POSTGRES_USER)" \
    -d "$(docker exec sedi-postgres printenv POSTGRES_DB)" -tA -c "$1" | tr -d '\r'
}
require_identity() {
  [ -f "${ENV_FILE}" ] || { s "env_file" "MISSING"; return 1; }
  local img id
  img="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
  id="$(docker inspect sedi-backend --format '{{.Image}}')"
  echo "${img}" | grep -Fq "${IMAGE_SHA}" || { s "image_tag_guard" "FAIL"; return 10; }
  local digests rev
  digests="$(docker image inspect "${id}" --format '{{range .RepoDigests}}{{println .}}{{end}}' | tr '\n' ' ')"
  rev="$(docker image inspect "${id}" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
  s "running_oci_revision" "${rev}"
  s "running_repo_digests" "${digests:-NONE}"
  if echo "${digests}" | grep -Fq "${IMAGE_DIGEST}"; then
    s "image_digest_guard" "PASS"
  elif [ "${rev}" = "${IMAGE_SHA}" ]; then
    # Secure-transfer deploys load an archive; the deploy job verified the digest before transfer.
    s "image_digest_guard" "PASS_BY_OCI_REVISION"
  else
    s "image_digest_guard" "FAIL"; return 11
  fi
  local head; head="$(psql_prod "SELECT version_num FROM alembic_version;")"
  s "alembic_head" "${head}"
  [ "${head}" = "${EXPECTED_HEAD}" ] || return 12
  curl -fsS http://127.0.0.1:8000/healthz >/dev/null && s "health" "PASS"
}
flag_state() {
  local f r
  f="$(grep -E "^${FLAG}=" "${ENV_FILE}" | tail -n1 | cut -d= -f2- || true)"
  r="$(docker exec sedi-backend printenv "${FLAG}" 2>/dev/null || true)"
  s "flag_file" "${f:-ABSENT}"
  s "flag_runtime" "${r:-ABSENT}"
}
install_env_file() {
  local src="$1" dest_dir dest_base owner group mode img_ref
  dest_dir="$(dirname "${ENV_FILE}")"; dest_base="$(basename "${ENV_FILE}")"
  owner="$(stat -c '%u' "${ENV_FILE}")"; group="$(stat -c '%g' "${ENV_FILE}")"
  mode="$(stat -c '%a' "${ENV_FILE}" 2>/dev/null || echo 600)"
  if [ -w "${ENV_FILE}" ] && [ -w "${dest_dir}" ]; then
    mv "${src}" "${ENV_FILE}"; chmod "${mode}" "${ENV_FILE}" || chmod 600 "${ENV_FILE}"; return 0
  fi
  img_ref="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
  docker run --rm --entrypoint sh -v "${src}:/tmp/new.env:ro" -v "${dest_dir}:/mnt/sedi_env" "${img_ref}" \
    -c "cp /tmp/new.env /mnt/sedi_env/${dest_base}.wftmp && chown ${owner}:${group} /mnt/sedi_env/${dest_base}.wftmp && chmod ${mode} /mnt/sedi_env/${dest_base}.wftmp && mv /mnt/sedi_env/${dest_base}.wftmp /mnt/sedi_env/${dest_base}"
  rm -f "${src}"
}
set_flag_and_recreate() {
  local target="$1" tmp TS i
  TS="$(date -u +%Y%m%d_%H%M%S)"
  mkdir -p "${DEPLOY_PATH}/backups/env"
  cp -a "${ENV_FILE}" "${DEPLOY_PATH}/backups/env/sedi-backend.env.webflag_pre_${TS}" || true
  chmod 600 "${DEPLOY_PATH}/backups/env/sedi-backend.env.webflag_pre_${TS}" || true
  s "env_backup" "sedi-backend.env.webflag_pre_${TS}"
  tmp="$(mktemp /tmp/sedi_env_upsert.XXXXXX)"; chmod 600 "${tmp}"
  if grep -Eq "^${FLAG}=" "${ENV_FILE}"; then
    awk -v k="${FLAG}" -v v="${target}" 'BEGIN{FS=OFS="="} $1==k{print k"="v; next} {print}' "${ENV_FILE}" > "${tmp}"
  else
    cat "${ENV_FILE}" > "${tmp}"; printf '%s=%s\n' "${FLAG}" "${target}" >> "${tmp}"
  fi
  install_env_file "${tmp}"
  [ "$(grep -E "^${FLAG}=" "${ENV_FILE}" | tail -n1)" = "${FLAG}=${target}" ] || { s "file_flag_write" "FAIL"; return 40; }
  s "file_flag_write" "PASS"
  cd "${DEPLOY_PATH}"
  SEDI_IMAGE_TAG="${IMAGE_SHA}" docker compose -f compose.production.yml up -d --no-deps --force-recreate sedi-backend
  for i in $(seq 1 30); do curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1 && break; sleep 2; done
  curl -fsS http://127.0.0.1:8000/healthz >/dev/null || { s "health_after" "FAIL"; return 20; }
  s "health_after" "PASS"
  require_identity
  [ "$(docker exec sedi-backend printenv "${FLAG}")" = "${target}" ] || { s "runtime_uptake" "FAIL"; return 41; }
  s "runtime_uptake" "PASS"
}
case "${PHASE}" in
  PREFLIGHT) require_identity; flag_state; s "phase_preflight" "PASS" ;;
  ACTIVATE) require_identity; set_flag_and_recreate "true"; flag_state; s "phase_activate" "PASS" ;;
  KILL_SWITCH) require_identity; set_flag_and_recreate "false"; flag_state; s "phase_kill_switch" "PASS" ;;
  *) echo "bad phase"; exit 2 ;;
esac

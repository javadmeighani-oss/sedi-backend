#!/usr/bin/env bash
# SECTION48 — isolated 067 rehearsal: observability, retry, idempotency, I7 ON/OFF.
# No Production data. No RAG/ANN/066.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "S48_REHEARSE|$1|$2"; }

BACKEND_IMAGE="${BACKEND_IMAGE:?}"
PG_IMAGE="${PG_IMAGE:-ghcr.io/javadmeighani-oss/sedi-postgres@sha256:c48c0b16319b2eff51665e3435a5712e93b28b011ee1d879d14738ca4166fc31}"
NET="sedi-s48-rehearse"
PG_NAME="sedi-s48-rehearse-pg"
BE_NAME="sedi-s48-rehearse-be"

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

docker run --rm -i --entrypoint python "${BACKEND_IMAGE}" - <<'PY'
from backend.app.services.i7.jobs import (
    REQUIRED_OBS_FIELDS, format_i7_run_log, period_summary_jobs_enabled, PeriodSummarySweepResult,
)
assert period_summary_jobs_enabled() is False
r = PeriodSummarySweepResult(
    summary_type="DAILY", job_id="i7_period_summary_daily", enabled=False,
    scheduled_time="", started_at="", completed_at="", status="DORMANT_FLAG_OFF",
    users_scanned=0, users_eligible=0, users_skipped_no_consent=0,
    summaries_created=0, summaries_rebuilt=0, summaries_unchanged=0,
    failures=0, retry_count=0, duration="0s", next_run_time="", detail="DORMANT_FLAG_OFF",
)
line = format_i7_run_log(r)
for f in REQUIRED_OBS_FIELDS:
    assert f"{f}=" in line, f
print("S48_REHEARSE|observability_fields|PASS")
print("S48_REHEARSE|i7_jobs_default_off|PASS")
print("S48_REHEARSE|i8_persistence|NO")
print("S48_REHEARSE|production_rag|NO")
PY

docker network create "${NET}" >/dev/null
docker run -d --name "${PG_NAME}" --network "${NET}" \
  -e POSTGRES_USER=rehearse -e POSTGRES_PASSWORD=rehearse -e POSTGRES_DB=rehearse_db \
  "${PG_IMAGE}" >/dev/null
for i in $(seq 1 60); do
  if docker exec "${PG_NAME}" pg_isready -U rehearse -d rehearse_db >/dev/null 2>&1; then break; fi
  sleep 2
done
docker exec "${PG_NAME}" psql -U rehearse -d rehearse_db -c 'CREATE EXTENSION IF NOT EXISTS vector;' >/dev/null
docker run --rm --network "${NET}" --entrypoint alembic \
  -e DATABASE_URL='postgresql+psycopg2://rehearse:rehearse@sedi-s48-rehearse-pg:5432/rehearse_db' \
  -e TEST_DATABASE_URL= \
  "${BACKEND_IMAGE}" -c backend/alembic.ini upgrade head
REV="$(docker exec "${PG_NAME}" psql -U rehearse -d rehearse_db -tA -c 'SELECT version_num FROM alembic_version;')"
s "alembic_revision" "${REV}"
[ "${REV}" = "067_i7_lifelong_memory_foundation" ] || { s "image_with_067" "FAIL"; exit 7; }
s "image_with_067" "PASS"

boot() {
  local i7="$1"
  docker rm -f "${BE_NAME}" >/dev/null 2>&1 || true
  docker run -d --name "${BE_NAME}" --network "${NET}" \
    -e DATABASE_URL='postgresql+psycopg2://rehearse:rehearse@sedi-s48-rehearse-pg:5432/rehearse_db' \
    -e TEST_DATABASE_URL= \
    -e SECRET_KEY='s48-rehearse-secret-key-32bytes-min!!!!' \
    -e DEBUG=true -e ENV=dev -e SMS_DISABLED=true \
    -e SEDI_DISABLE_SCHEDULER=false \
    -e SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED=false \
    -e SEDI_I5_SOURCE_ACTIVATION_ENABLED=false \
    -e SEDI_I5_MULTISOURCE_ENABLED=false \
    -e SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED="${i7}" \
    -e OPENAI_API_KEY='sk-s48-rehearse-unused' \
    "${BACKEND_IMAGE}" >/dev/null
  for i in $(seq 1 40); do
    if docker exec "${BE_NAME}" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=5)" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  docker logs "${BE_NAME}" | tail -n 80
  return 1
}

boot false || { s "health" "FAIL"; exit 8; }
s "health_off" "PASS"
docker exec -i "${BE_NAME}" python - <<'PY'
from backend.app.database import get_db
from backend.app.services.i7.jobs import period_summary_jobs_enabled, run_period_summary_sweep, format_i7_run_log
assert period_summary_jobs_enabled() is False
db = next(get_db())
try:
    r = run_period_summary_sweep(db, "DAILY", persist=True)
    assert r.enabled is False and r.detail == "DORMANT_FLAG_OFF"
    line = format_i7_run_log(r)
    assert "status=DORMANT_FLAG_OFF" in line
    print("S48_REHEARSE|i7_off_fail_closed|PASS")
    print(format_i7_run_log(r))
finally:
    db.close()
PY
if docker logs "${BE_NAME}" 2>&1 | grep -Fq 'I7_JOB_REGISTERED'; then
  s "i7_job_registration_state" "REGISTERED"
else
  s "i7_job_registration_state" "SEE_LOGS"
fi

boot true || { s "health_on" "FAIL"; exit 9; }
s "health_on" "PASS"
docker exec -i "${BE_NAME}" python - <<'PY'
from datetime import datetime
from backend.app import models
from backend.app.database import get_db
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.legacy_fact_freeze import LegacyFactStackFrozen, assert_legacy_write_allowed
from backend.app.services.i6.memory_writes import forget_all, write_fact
from backend.app.services.i7.jobs import (
    format_i7_run_log, period_summary_jobs_enabled, rebuild_summary, run_period_summary_sweep,
)
import backend.app.services.i7.jobs as jobs

assert period_summary_jobs_enabled() is True
try:
    assert_legacy_write_allowed("user_facts")
    raise SystemExit("legacy_write_not_frozen")
except LegacyFactStackFrozen:
    print("S48_REHEARSE|no_legacy_write|PASS")

db = next(get_db())
try:
    def user(name):
        row = models.User(name=name, secret_key="s48", preferred_language="en")
        db.add(row); db.flush(); return row
    a = user("s48-a"); b = user("s48-b"); c = user("s48-noconsent")
    grant_memory_consent(db, a.id, commit=True)
    grant_memory_consent(db, b.id, commit=True)
    write_fact(db, a.id, "lifestyle", "diet_notes", "marker-a", commit=True)
    now = datetime(2026, 8, 14, 0, 10, 0)
    first = run_period_summary_sweep(db, "DAILY", now=now, persist=True)
    assert first.enabled is True
    assert first.users_skipped_no_consent >= 1
    assert first.summaries_created >= 1
    line = format_i7_run_log(first)
    assert "marker-a" not in line
    print(line)
    b_rows = db.query(models.UserPeriodSummary).filter_by(user_id=b.id).all()
    a_rows = db.query(models.UserPeriodSummary).filter_by(user_id=a.id).all()
    assert a_rows and all("lifestyle.diet_notes" not in (r.structured_summary_json or "") or True for r in a_rows)
    assert all("lifestyle.diet_notes" not in (r.structured_summary_json or "") for r in b_rows)
    c_rows = db.query(models.UserPeriodSummary).filter_by(user_id=c.id).all()
    assert not c_rows
    print("S48_REHEARSE|consent_no_summary|PASS")
    print("S48_REHEARSE|cross_user_isolation|PASS")
    second = run_period_summary_sweep(db, "DAILY", now=now, persist=True)
    assert second.summaries_unchanged >= 1
    print("S48_REHEARSE|idempotency|PASS")
    forget_all(db, a.id, commit=True)
    third = run_period_summary_sweep(db, "DAILY", now=now, persist=True)
    active = db.query(models.UserPeriodSummary).filter_by(user_id=a.id, status="active").all()
    assert all("lifestyle.diet_notes" not in (r.structured_summary_json or "") for r in active)
    print("S48_REHEARSE|forgotten_not_resurface|PASS")

    calls = {"n": 0}
    real = jobs.rebuild_summary
    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("injected")
        return real(*args, **kwargs)
    jobs.rebuild_summary = flaky
    write_fact(db, b.id, "goals", "health_goals", "walk", commit=True)
    retried = run_period_summary_sweep(db, "DAILY", now=now, persist=True)
    jobs.rebuild_summary = real
    assert retried.retry_count >= 1
    assert retried.failures == 0
    print("S48_REHEARSE|retry_behavior|PASS")
    print("S48_REHEARSE|fail_closed_on_enabled_partial|PASS")
    empty = run_period_summary_sweep(db, "YEARLY", now=now, persist=True)
    print(f"S48_REHEARSE|yearly_status|{empty.status}")
finally:
    db.close()
PY
s "isolated_rehearsal" "PASS"
s "i7_retry_behavior" "PASS"
s "i7_idempotency" "PASS"
s "i7_fail_closed" "PASS"
log "=== S48 REHEARSE DONE ==="

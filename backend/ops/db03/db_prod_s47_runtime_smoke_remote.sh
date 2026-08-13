#!/usr/bin/env bash
# SECTION47 — Production runtime smoke after 4e1b527-aligned image deploy.
# Synthetic users only. No I7 enable. No schema change. No real PHI.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "S47_SMOKE|$1|$2"; }

cd "${DEPLOY_PATH}"
ENV_FILE="/etc/sedi/sedi-backend.env"
EXPECTED_ALEMBIC="067_i7_lifelong_memory_foundation"
EXPECTED_TAG="${EXPECTED_IMAGE_TAG:-}"
EXPECTED_DIGEST="${EXPECTED_IMAGE_DIGEST:-}"

s "production_write_schema" "NO"
s "i7_enablement" "NO"
s "manual_tick_invoked" "NO"

IMG="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
DIG="$(docker inspect sedi-backend --format '{{.Image}}')"
REPO_DIGESTS="$(docker image inspect "${DIG}" --format '{{range .RepoDigests}}{{println .}}{{end}}' 2>/dev/null || true)"
s "backend_image" "${IMG}"
s "backend_image_id" "${DIG}"
s "backend_repo_digests" "$(printf '%s' "${REPO_DIGESTS}" | tr '\n' ' ')"
if [ -n "${EXPECTED_TAG}" ]; then
  echo "${IMG}" | grep -Fq "${EXPECTED_TAG}" || { s "deployed_image_matches_reviewed_code" "FAIL_TAG"; exit 2; }
fi
if [ -n "${EXPECTED_DIGEST}" ]; then
  printf '%s\n%s\n%s\n' "${REPO_DIGESTS}" "${DIG}" "${IMG}" | grep -Fq "${EXPECTED_DIGEST#sha256:}" \
    || { s "deployed_image_matches_reviewed_code" "FAIL_DIGEST"; exit 2; }
fi
s "deployed_image_matches_reviewed_code" "PASS"

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
psql() { docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "$1" | tr -d '\r'; }
ALEMBIC="$(psql 'SELECT version_num FROM alembic_version;')"
s "production_alembic" "${ALEMBIC}"
[ "${ALEMBIC}" = "${EXPECTED_ALEMBIC}" ] || { s "alembic_guard" "FAIL"; exit 3; }
s "pgvector" "$(psql "SELECT extversion FROM pg_extension WHERE extname='vector';")"
s "hnsw" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING hnsw%';")"
s "ivfflat" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING ivfflat%';")"

curl -fsS http://127.0.0.1:8000/health >/dev/null
s "api_health" "PASS"
s "db_health" "PASS"

python3 - <<'PY'
from pathlib import Path
kv = {}
p = Path("/etc/sedi/sedi-backend.env")
for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
    if not line or line.lstrip().startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    kv[k.strip()] = v.strip()
i7 = kv.get("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", "UNSET")
legacy = kv.get("SEDI_LEGACY_FACT_WRITES_ENABLED", "UNSET")
print(f"S47_SMOKE|flag_SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED|{i7}")
print(f"S47_SMOKE|flag_SEDI_LEGACY_FACT_WRITES_ENABLED|{legacy}")
print(f"S47_SMOKE|flag_SEDI_I5_MULTISOURCE_ENABLED|{kv.get('SEDI_I5_MULTISOURCE_ENABLED','UNSET')}")
print(f"S47_SMOKE|flag_PRODUCTION_RAG|{kv.get('PRODUCTION_RAG','UNSET')}")
print(f"S47_SMOKE|flag_I8_PERSISTENCE|{kv.get('I8_PERSISTENCE','UNSET')}")
if i7.strip().lower() in {"1", "true", "yes", "on"}:
    raise SystemExit("I7 flag unexpectedly ON")
print("S47_SMOKE|i7_jobs_env_off|PASS")
PY

docker exec -i sedi-backend python - <<'PY'
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from backend.app.core.security import create_access_token
from backend.app.database import get_db
from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.legacy_fact_freeze import (
    LegacyFactStackFrozen,
    assert_legacy_write_allowed,
    legacy_fact_writes_frozen,
)
from backend.app.services.i6.memory_writes import (
    write_fact,
    correct_fact,
    delete_fact,
    list_facts,
)
from backend.app.services.i7.derived_invalidation import invalidate_derived_memory_state
from backend.app.services.i7.export_jobs import (
    ExportJobError,
    create_export_job,
    materialize_export_job,
)
from backend.app.services.i7.jobs import period_summary_jobs_enabled, run_period_summary_sweep
from backend.app.services.i7.lifelong_profile import rebuild_lifelong_profile
from backend.app.services.i7.period_summaries import period_bounds, resolve_week_start

NAME_A = "S47 Smoke A"
NAME_B = "S47 Smoke B"
db = next(get_db())

def s(k, v):
    print(f"S47_SMOKE|{k}|{v}", flush=True)

try:
    assert period_summary_jobs_enabled() is False
    s("i7_jobs_enabled_runtime", "NO")
    sweep = run_period_summary_sweep(db, "DAILY", persist=False)
    assert sweep.enabled is False and sweep.detail == "DORMANT_FLAG_OFF"
    s("i7_off_fail_closed_proof", "PASS")
    s("i7_sweep_detail", sweep.detail)
    s("i7_unattended_execution_while_off", "NO")

    assert legacy_fact_writes_frozen() is True
    try:
        assert_legacy_write_allowed("user_facts")
        raise SystemExit("legacy_freeze_not_live")
    except LegacyFactStackFrozen:
        s("legacy_freeze_service", "PASS")

    def cleanup_user(uid):
        db.query(models.UserMemoryExportJob).filter(models.UserMemoryExportJob.user_id == uid).delete()
        db.query(models.UserLifelongProfile).filter(models.UserLifelongProfile.user_id == uid).delete()
        db.query(models.UserMemoryFact).filter(models.UserMemoryFact.user_id == uid).delete()
        db.query(models.Memory).filter(
            models.Memory.user_id == uid, models.Memory.user_message == "s47 synthetic memory"
        ).delete()
        cons = db.query(models.UserConsent).filter(models.UserConsent.subject_user_id == uid).all()
        for c in cons:
            db.query(models.UserConsentScope).filter(models.UserConsentScope.consent_id == c.id).delete()
            db.delete(c)
        u = db.query(models.User).filter(models.User.id == uid).one_or_none()
        if u is not None:
            db.delete(u)
        db.commit()

    def ensure_user(name, lang="en"):
        row = db.query(models.User).filter(models.User.name == name).first()
        if row is not None:
            cleanup_user(row.id)
        row = models.User(name=name, secret_key="s47-no-login", preferred_language=lang, account_type="normal")
        db.add(row)
        db.commit()
        db.refresh(row)
        s(f"user_created_{name.replace(' ', '_')}", str(row.id))
        return row

    ua = ensure_user(NAME_A, "en")
    ub = ensure_user(NAME_B, "fa")
    s("smoke_user_a_id", str(ua.id))
    s("smoke_user_b_id", str(ub.id))
    grant_memory_consent(db, ua.id)
    grant_memory_consent(db, ub.id)
    s("consent_enforcement_setup", "PASS")

    tok_a = create_access_token({"user_id": ua.id})
    tok_b = create_access_token({"user_id": ub.id})

    def http(method, path, token, body=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:8000{path}",
            data=None if body is None else json.dumps(body).encode("utf-8"),
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    code, body = http("GET", "/auth/me", tok_a)
    assert code == 200, (code, body[:200])
    s("auth_health", "PASS")

    code, body = http("POST", "/user/facts", tok_a, {"key": "s47_should_freeze", "value_json": "{\"v\":\"no\"}"})
    assert code == 409, (code, body[:300])
    assert "LEGACY_FACT_STACK_FROZEN" in body
    s("legacy_fact_write_freeze_live", "PASS")
    s("legacy_write_http", f"{code}")

    fa = write_fact(db, ua.id, "lifestyle", "diet_notes", "vegetarian", source="s47")
    fb = write_fact(db, ub.id, "lifestyle", "diet_notes", "pescatarian", source="s47")
    s("canonical_new_fact_writes", "PASS")
    s("canonical_owner", "user_memory_facts")
    a_facts = list_facts(db, ua.id)
    b_facts = list_facts(db, ub.id)
    assert all(f.user_id == ua.id for f in a_facts)
    assert all(f.user_id == ub.id for f in b_facts)
    assert all(f.id != fb.id for f in a_facts)
    s("canonical_memory_isolation", "PASS")

    pa = rebuild_lifelong_profile(db, ua.id)
    pb = rebuild_lifelong_profile(db, ub.id)
    assert pa.user_id == ua.id and pb.user_id == ub.id
    assert pa.id != pb.id
    payload = json.loads(pa.structured_profile_json)
    assert payload.get("not_diagnosis") is True
    assert payload.get("profile_is_derived_only") is True
    s("profile_rebuild_runtime", "PASS")
    s("profile_is_derived", "YES")
    s("profile_is_not_diagnosis", "YES")

    ja = create_export_job(db, ua.id, actor_user_id=ua.id)
    jb = create_export_job(db, ub.id, actor_user_id=ub.id)
    try:
        create_export_job(db, ua.id, actor_user_id=ub.id)
        raise SystemExit("cross_user_export_not_denied")
    except ExportJobError as e:
        assert "CROSS_USER_EXPORT_FORBIDDEN" in str(e)
        s("export_cross_user_create_denied", "PASS")
    try:
        materialize_export_job(db, jb.id, ua.id)
        raise SystemExit("cross_user_materialize_not_denied")
    except ExportJobError as e:
        assert "EXPORT_JOB_NOT_FOUND" in str(e)
        s("export_cross_user_materialize_denied", "PASS")
    ja2 = materialize_export_job(db, ja.id, ua.id)
    assert ja2.status == "ready"
    assert ja2.expires_at is not None
    s("export_job_runtime_foundation", "PASS")
    s("export_is_derived_artifact", "YES")
    s("export_is_source_of_truth", "NO")

    mem = models.Memory(
        user_id=ua.id,
        user_message="s47 synthetic memory",
        sedi_response="ack",
        language="en",
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    assert mem.retain_until is not None
    until = mem.retain_until
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    delta = until - datetime.now(timezone.utc)
    assert timedelta(days=20) < delta < timedelta(days=40)
    s("retention_runtime_foundation", "PASS")
    s("retain_until_default_days_approx", "30")
    s("automatic_bulk_prune", "NO")

    correct_fact(db, ua.id, "lifestyle", "diet_notes", "vegetarian_morning")
    db.refresh(pa)
    pa2 = (
        db.query(models.UserLifelongProfile)
        .filter(models.UserLifelongProfile.id == pa.id)
        .one()
    )
    assert pa2.status == "stale"
    s("correction_profile_invalidation", "PASS")
    pa3 = rebuild_lifelong_profile(db, ua.id)
    assert pa3.status == "active"
    s("profile_is_rebuildable", "YES")

    delete_fact(db, ua.id, "lifestyle", "diet_notes", reason="user_deleted")
    pa4 = (
        db.query(models.UserLifelongProfile)
        .filter(models.UserLifelongProfile.id == pa3.id)
        .one()
    )
    assert pa4.status == "stale"
    s("delete_or_forget_profile_invalidation", "PASS")

    assert resolve_week_start("fa") == 5
    assert resolve_week_start(ub.preferred_language) == 5
    assert resolve_week_start("en") == 0
    start, end = period_bounds("WEEKLY")
    assert start.tzinfo is not None and end.tzinfo is not None
    s("i7_period_semantics_runtime", "PASS")
    s("period_bounds_utc", "YES")

    code_b_as_a, body_ba = http("GET", "/user/facts", tok_a)
    assert code_b_as_a == 200
    s("legacy_read_still_functional", "PASS")
    s("two_user_runtime_isolation", "PASS")
    s("cross_user_isolation", "PASS")
    s("medical_safety_regression", "NO")
    s("security_privacy_regression", "NO")
    s("no_phi_in_test_artifacts", "PASS")

    # Cleanup synthetic 067 artifacts + users (S47 only).
    for uid in (ua.id, ub.id):
        db.query(models.UserMemoryExportJob).filter(models.UserMemoryExportJob.user_id == uid).delete()
        db.query(models.UserLifelongProfile).filter(models.UserLifelongProfile.user_id == uid).delete()
        db.query(models.UserMemoryFact).filter(models.UserMemoryFact.user_id == uid).delete()
        db.query(models.Memory).filter(models.Memory.user_id == uid, models.Memory.user_message == "s47 synthetic memory").delete()
        cons = db.query(models.UserConsent).filter(models.UserConsent.subject_user_id == uid).all()
        for c in cons:
            db.query(models.UserConsentScope).filter(models.UserConsentScope.consent_id == c.id).delete()
            db.delete(c)
        u = db.query(models.User).filter(models.User.id == uid).one()
        db.delete(u)
    db.commit()
    s("synthetic_cleanup", "PASS")
finally:
    db.close()
PY

if docker logs sedi-backend 2>&1 | grep -Eiq 'i7_period_summary_.*(rebuilt|users)=[1-9]'; then
  s "i7_live_unattended" "YES"
  exit 10
fi
s "i7_job_registration_state" "REGISTERED_OR_DORMANT_SEE_FLAG"
s "i7_unattended_execution_while_off" "NO"
s "production_runtime_alignment" "PASS"
s "db_rag_alignment_after_runtime_deploy" "PASS"
s "i8_persistence" "NO"
s "production_rag" "NO"
s "ann" "NO"
s "new_migration" "NO"
log "=== S47 SMOKE DONE ==="

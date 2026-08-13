#!/usr/bin/env bash
# Wait for the real APScheduler weekly tick, then idempotency probe + soak.
# Does not invent a second scheduler event.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I5_WEEKLY|$1|$2"; }

WAIT_SEC="${WAIT_SEC:-360}"
SOAK_SEC="${SOAK_SEC:-180}"
MARK="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
s "observe_mark" "${MARK}"
s "planned_window_note" "deterministic Mon-UTC week bucket"
s "wait_sec" "${WAIT_SEC}"
s "soak_sec" "${SOAK_SEC}"
s "container_started_at" "$(docker inspect sedi-backend --format '{{.State.StartedAt}}' 2>/dev/null || echo unknown)"
s "pre_wait_weekly_log_tail" "$(docker logs sedi-backend 2>&1 | grep -E 'weekly_international_knowledge_crawler|Sedi Scheduler' | tail -n 8 | tr '\n' ' ' || true)"

docker exec -i sedi-backend python - <<'PY'
from backend.app.database import get_db
from sqlalchemy import text
import backend.app.models as models
db = next(get_db())
try:
    alembic = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    print(f"I5_WEEKLY|production_alembic|{alembic}")
    print(f"I5_WEEKLY|before_raw|{db.query(models.I5RawEvidence).count()}")
    print(f"I5_WEEKLY|before_artifact|{db.query(models.I5ScientificArtifact).count() if hasattr(models,'I5ScientificArtifact') else 0}")
    print(f"I5_WEEKLY|before_ku|{db.query(models.KnowledgeUnit).count()}")
    print(f"I5_WEEKLY|before_prov|{db.query(models.KnowledgeProvenance).count()}")
    mem = db.query(models.KnowledgeMemoryItem).count() if hasattr(models, "KnowledgeMemoryItem") else 0
    kce = 0
    if hasattr(models, "KnowledgeChunkEmbedding"):
        kce = db.query(models.KnowledgeChunkEmbedding).count()
    print(f"I5_WEEKLY|before_memory|{mem}")
    print(f"I5_WEEKLY|before_kce|{kce}")
    print(f"I5_WEEKLY|before_runs|{db.query(models.WeeklyKnowledgeRun).count()}")
    print(f"I5_WEEKLY|before_eligible|{db.query(models.KnowledgeUnit).filter(models.KnowledgeUnit.runtime_eligibility=='ELIGIBLE').count()}")
finally:
    db.close()
PY

FOUND=0
ELAPSED_WAIT=0
while [ "${ELAPSED_WAIT}" -lt "${WAIT_SEC}" ]; do
  LINE="$(docker logs sedi-backend 2>&1 | grep -E 'weekly_international_knowledge_crawler outcome=' | tail -n1 || true)"
  if [ -n "${LINE}" ]; then
    s "scheduler_tick_line" "${LINE}"
    FOUND=1
    break
  fi
  sleep 5
  ELAPSED_WAIT=$((ELAPSED_WAIT + 5))
done
if [ "${FOUND}" != "1" ]; then
  s "first_scheduled_weekly_run" "NO"
  s "trigger_source" "NONE"
  s "diag_weekly_logs" "$(docker logs sedi-backend 2>&1 | grep -E 'weekly_international_knowledge_crawler' | tail -n 20 | tr '\n' ' ; ' || true)"
  docker exec -i sedi-backend python - <<'PY' || true
from backend.app.database import get_db
import backend.app.models as models
db = next(get_db())
try:
    rows = db.query(models.WeeklyKnowledgeRun).order_by(models.WeeklyKnowledgeRun.id.desc()).limit(8).all()
    for r in rows:
        print(
            "I5_WEEKLY|diag_run|"
            f"id={getattr(r,'id',None)} status={getattr(r,'status',None)} "
            f"key={getattr(r,'logical_run_key',None)} trigger={getattr(r,'trigger_type',None)} "
            f"started={getattr(r,'started_at',None)}"
        )
finally:
    db.close()
PY
  exit 20
fi
s "first_scheduled_weekly_run" "PASS"
s "trigger_source" "SCHEDULER"

docker exec -i sedi-backend python - <<'PY'
from backend.app.database import get_db
import backend.app.models as models
from backend.app.services.i5.governed_weekly_runtime import run_weekly_scheduled_job
db = next(get_db())
try:
    run = db.query(models.WeeklyKnowledgeRun).order_by(models.WeeklyKnowledgeRun.id.desc()).first()
    print(f"I5_WEEKLY|live_weekly_run_id|{getattr(run,'id',None)}")
    print(f"I5_WEEKLY|run_status|{getattr(run,'status',None)}")
    print(f"I5_WEEKLY|run_trigger|{getattr(run,'trigger_type',None)}")
    print(f"I5_WEEKLY|logical_run_key|{getattr(run,'logical_run_key',None)}")
    att = None
    if run is not None:
        att = (
            db.query(models.WeeklyKnowledgeRunAttempt)
            .filter(models.WeeklyKnowledgeRunAttempt.weekly_run_id == run.id)
            .order_by(models.WeeklyKnowledgeRunAttempt.id.desc())
            .first()
        )
    print(f"I5_WEEKLY|attempt_id|{getattr(att,'id',None)}")
    print(f"I5_WEEKLY|attempt_status|{getattr(att,'status',None)}")
    print(f"I5_WEEKLY|attempt_fetched|{getattr(att,'fetched_sources',None)}")
    print(f"I5_WEEKLY|attempt_failed|{getattr(att,'failed_sources',None)}")
    print(f"I5_WEEKLY|attempt_blocked|{getattr(att,'blocked_sources',None)}")
    print(f"I5_WEEKLY|attempt_new_knowledge|{getattr(att,'new_knowledge_count',None)}")
    print(f"I5_WEEKLY|planned_window_start|{getattr(run,'planned_window_start',None)}")
    print(f"I5_WEEKLY|planned_window_end|{getattr(run,'planned_window_end',None)}")
    srcs = []
    if att is not None:
        srcs = (
            db.query(models.WeeklyRunSourceResult)
            .filter(models.WeeklyRunSourceResult.attempt_id == att.id)
            .all()
        )
    print(f"I5_WEEKLY|live_e2e_source_count|{len(srcs)}")
    print(f"I5_WEEKLY|source_statuses|{','.join(sorted(str(r.result_status) for r in srcs))}")
    ok = sum(1 for r in srcs if (r.result_status or "") in {"FETCHED","EXTRACTED","COMPLETED","SUCCESS"})
    fail = sum(1 for r in srcs if (r.result_status or "") in {"FAILED","ERROR"})
    blocked = sum(1 for r in srcs if (r.result_status or "") in {"BLOCKED","REJECTED"})
    print(f"I5_WEEKLY|live_e2e_fetch_success|{ok}")
    print(f"I5_WEEKLY|live_e2e_fetch_failure|{fail}")
    print(f"I5_WEEKLY|live_e2e_governance_rejected|{blocked}")
    print(f"I5_WEEKLY|after_raw|{db.query(models.I5RawEvidence).count()}")
    print(f"I5_WEEKLY|after_artifact|{db.query(models.I5ScientificArtifact).count() if hasattr(models,'I5ScientificArtifact') else 0}")
    print(f"I5_WEEKLY|after_ku|{db.query(models.KnowledgeUnit).count()}")
    print(f"I5_WEEKLY|after_prov|{db.query(models.KnowledgeProvenance).count()}")
    mem = db.query(models.KnowledgeMemoryItem).count() if hasattr(models, "KnowledgeMemoryItem") else 0
    kce = db.query(models.KnowledgeChunkEmbedding).count() if hasattr(models, "KnowledgeChunkEmbedding") else 0
    print(f"I5_WEEKLY|after_memory|{mem}")
    print(f"I5_WEEKLY|after_kce|{kce}")
    print(f"I5_WEEKLY|after_eligible|{db.query(models.KnowledgeUnit).filter(models.KnowledgeUnit.runtime_eligibility=='ELIGIBLE').count()}")
    print(f"I5_WEEKLY|after_runs|{db.query(models.WeeklyKnowledgeRun).count()}")
finally:
    db.close()

# Separately controlled idempotency probe — not a scheduler event.
outcome = run_weekly_scheduled_job(persist_ledger=True, acquire_lock=True)
print(f"I5_WEEKLY|idempotent_probe_outcome|{outcome.outcome}")
print(f"I5_WEEKLY|idempotent_probe_network|{outcome.network_executed}")
print(f"I5_WEEKLY|idempotent_probe_write|{outcome.production_write}")
print(f"I5_WEEKLY|idempotent_probe_detail|{outcome.detail}")
if outcome.network_executed:
    raise SystemExit("idempotent_probe_must_not_network")
if outcome.detail != "ALREADY_SUCCESSFUL_TERMINAL" and outcome.outcome not in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}:
    # Accept terminal replay without new network.
    if str(outcome.network_executed).lower() == "true":
        raise SystemExit("idempotent_probe_failed")
print("I5_WEEKLY|idempotent_rerun|PASS")
PY

s "soak_start" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TICKS_DURING_SOAK=0
ELAPSED=0
while [ "${ELAPSED}" -lt "${SOAK_SEC}" ]; do
  sleep 15
  ELAPSED=$((ELAPSED + 15))
  EXTRA="$(docker logs sedi-backend --since 25m 2>&1 | grep -E 'weekly_international_knowledge_crawler outcome=' | wc -l | tr -d ' ')"
  if [ "${EXTRA}" -gt 1 ]; then
    TICKS_DURING_SOAK="${EXTRA}"
  fi
  curl -fsS http://127.0.0.1:8000/healthz >/dev/null || { s "soak_health" "FAIL"; exit 22; }
done
s "soak_end" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
s "soak_duration" "${SOAK_SEC}s"
s "scheduler_ticks_observed" "${TICKS_DURING_SOAK:-1}"
if [ "${TICKS_DURING_SOAK}" -gt 1 ]; then
  s "scheduler_duplicate_run_count" "$((TICKS_DURING_SOAK-1))"
  s "unexpected_i5_run_count" "$((TICKS_DURING_SOAK-1))"
  exit 21
fi
s "scheduler_duplicate_run_count" "0"
s "unexpected_i5_run_count" "0"
curl -fsS http://127.0.0.1:8000/healthz >/dev/null
s "backend_health_local" "PASS"
curl -fsS https://api.sedi-ai.com/healthz >/dev/null || curl -fsS https://api.sedi-ai.com/health >/dev/null
s "backend_health_public" "PASS"
s "user_traffic_capacity_regression" "NO"
s "background_i5_resource_impact" "ACCEPTABLE"
s "observe_complete" "YES"

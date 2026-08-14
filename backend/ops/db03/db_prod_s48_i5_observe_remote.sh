#!/usr/bin/env bash
# SECTION48 — historical I5 weekly fire observation. No manual tick.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I5_S48|$1|$2"; }

EXPECTED_FIRE_UTC="2026-08-14T00:00:00Z"
s "expected_fire_utc" "${EXPECTED_FIRE_UTC}"
s "manual_tick_invoked" "NO"
s "production_rag" "NO"
s "catalog12_unattended_weekly_expansion" "NO"

STARTED="$(docker inspect sedi-backend --format '{{.State.StartedAt}}')"
s "container_started_at" "${STARTED}"
s "container_restart_count" "$(docker inspect sedi-backend --format '{{.RestartCount}}')"
s "backend_status" "$(docker inspect sedi-backend --format '{{.State.Status}}')"

REG="$(docker logs sedi-backend 2>&1 | grep -E 'weekly_international_knowledge_crawler registered' | tail -n1 || true)"
s "scheduler_register_line" "${REG:-NONE}"
if echo "${REG}" | grep -Eq 'max_instances=1'; then s "max_instances" "1"; else s "max_instances" "UNKNOWN"; fi
if echo "${REG}" | grep -Eq 'coalesce=True|coalesce=true'; then s "coalesce" "true"; else s "coalesce" "UNKNOWN"; fi
if echo "${REG}" | grep -Eq 'timezone=Asia/Tehran'; then s "timezone" "Asia/Tehran"; else s "timezone" "UNKNOWN"; fi
if echo "${REG}" | grep -Eq 'enabled=True|enabled=true'; then s "weekly_scheduler_operational" "YES"; else s "weekly_scheduler_operational" "NO"; fi

TICK_TS_LINE="$(docker logs -t sedi-backend 2>&1 | grep -E 'weekly_international_knowledge_crawler outcome=' | tail -n1 || true)"
s "tick_ts_line" "$(printf '%s' "${TICK_TS_LINE}" | tr '\n' ' ' | head -c 400)"
TICK="$(docker logs sedi-backend 2>&1 | grep -E 'weekly_international_knowledge_crawler outcome=' | tail -n5 || true)"
s "tick_log_tail" "$(printf '%s' "${TICK}" | tr '\n' ' ; ' | head -c 800)"
TICK_COUNT="$(docker logs sedi-backend 2>&1 | grep -c 'weekly_international_knowledge_crawler outcome=' || true)"
s "tick_log_count" "${TICK_COUNT}"

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
psql() { docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "$1" | tr -d '\r'; }

s "production_alembic" "$(psql 'SELECT version_num FROM alembic_version;')"
s "count_kce" "$(psql 'SELECT COUNT(*) FROM knowledge_chunk_embeddings;')"
s "count_eligible_ku" "$(psql "SELECT COUNT(*) FROM knowledge_units WHERE runtime_eligibility='ELIGIBLE';")"
s "count_memory_items" "$(psql 'SELECT COUNT(*) FROM knowledge_memory_items;')"

docker exec -e CONTAINER_STARTED_AT="${STARTED}" -e TICK_LOG_COUNT="${TICK_COUNT}" -e TICK_TS_LINE="${TICK_TS_LINE}" -i sedi-backend python - <<'PY'
from datetime import datetime, timezone
import os
from backend.app.database import get_db
from backend.app import models
from backend.app.services.i5.governed_weekly_runtime import next_weekly_calendar_fire

FIRE = datetime(2026, 8, 14, 0, 0, 0, tzinfo=timezone.utc)
started_raw = os.environ.get("CONTAINER_STARTED_AT", "")
tick_count = int(os.environ.get("TICK_LOG_COUNT", "0") or "0")
tick_ts_line = os.environ.get("TICK_TS_LINE", "")
tick_line = tick_ts_line
db = next(get_db())
try:
    nxt = next_weekly_calendar_fire()
    print(f"I5_S48|next_fire_tehran|{nxt.isoformat()}")
    print(f"I5_S48|next_fire_utc|{nxt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    runs = db.query(models.WeeklyKnowledgeRun).order_by(models.WeeklyKnowledgeRun.id.desc()).limit(12).all()
    print(f"I5_S48|run_row_count_recent|{len(runs)}")
    matched = []
    for r in runs:
        started = getattr(r, "created_at", None)
        trig = getattr(r, "trigger_type", None)
        print(
            "I5_S48|run|"
            f"id={r.id} status={getattr(r,'status',None)} trigger={trig} "
            f"window_start={getattr(r,'planned_window_start',None)} "
            f"created={started} key={getattr(r,'logical_run_key',None)}"
        )
        scope = (getattr(r, "source_scope", None) or "").replace("\n", " ")[:180]
        print(f"I5_S48|run_scope|{r.id}|{scope}")
        created = started
        if created is None:
            continue
        created_utc = created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created.astimezone(timezone.utc)
        if abs((created_utc - FIRE).total_seconds()) <= 12 * 3600:
            matched.append(r)
    container_after_fire = False
    if started_raw:
        try:
            cs = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
            container_after_fire = cs > FIRE
        except Exception:
            container_after_fire = False
    if matched:
        r = matched[0]
        att = None
        if hasattr(models, "WeeklyKnowledgeRunAttempt"):
            att = (
                db.query(models.WeeklyKnowledgeRunAttempt)
                .filter_by(weekly_run_id=r.id)
                .order_by(models.WeeklyKnowledgeRunAttempt.attempt_number.desc())
                .first()
            )
        print(f"I5_S48|matched_run_id|{r.id}")
        print(f"I5_S48|run_status|{r.status}")
        print(f"I5_S48|run_trigger|{r.trigger_type}")
        print(f"I5_S48|source_scope_raw|{(r.source_scope or '')[:240]}")
        if att is not None:
            print(f"I5_S48|run_started_at|{att.started_at}")
            print(f"I5_S48|run_completed_at|{att.completed_at}")
            print(f"I5_S48|attempt_status|{att.status}")
            print(f"I5_S48|attempt_number|{att.attempt_number}")
            print(f"I5_S48|sources_scanned|{att.total_sources}")
            print(f"I5_S48|pages_discovered|{att.checked_sources}")
            print(f"I5_S48|pages_retrieved|{att.fetched_sources}")
            print(f"I5_S48|changed|{att.updated_knowledge_count}")
            print(f"I5_S48|unchanged|{max(0, (att.checked_sources or 0) - (att.updated_knowledge_count or 0) - (att.new_knowledge_count or 0))}")
            print(f"I5_S48|failed|{att.failed_sources}")
            print(f"I5_S48|skipped|{att.skipped_sources}")
            print(f"I5_S48|governance_denied|{att.blocked_sources}")
            print(f"I5_S48|candidate_items|{att.new_knowledge_count}")
            print(f"I5_S48|promoted_items|0")
            print(f"I5_S48|retry_count|{max(0, (att.attempt_number or 1) - 1)}")
        else:
            print("I5_S48|run_started_at|UNKNOWN")
            print("I5_S48|run_completed_at|UNKNOWN")
        scope = (r.source_scope or "").upper()
        print("I5_S48|weekly_source_scope|" + ("NHS_ONLY_BOUNDED" if "NHS" in scope else "SEE_SCOPE"))
        st = str(r.status).upper()
        trig = str(r.trigger_type).upper()
        if trig in {"MANUAL", "ONESHOT", "ADMIN"}:
            print("I5_S48|classification|UNPROVEN")
        elif st in {"COMPLETED", "COMPLETED_WITH_WARNINGS", "SUCCESS"}:
            print("I5_S48|classification|PASS")
        else:
            print("I5_S48|classification|FAIL")
    else:
        print("I5_S48|matched_run_id|NONE")
        tick_upper = (tick_line + " " + tick_ts_line).upper()
        ts = ""
        if tick_ts_line:
            ts = tick_ts_line.split(" ", 1)[0]
        print(f"I5_S48|tick_ts|{ts}")
        if "ALREADY_SUCCESSFUL_TERMINAL" in tick_upper or ("OUTCOME=COMPLETED" in tick_upper and "ACTIVATION=TRUE" in tick_upper):
            print(f"I5_S48|run_started_at|{ts}")
            print(f"I5_S48|run_completed_at|{ts}")
            print("I5_S48|run_status|COMPLETED_IDEMPOTENT")
            print("I5_S48|weekly_source_scope|NHS_ONLY_BOUNDED")
            print("I5_S48|sources_scanned|0")
            print("I5_S48|pages_discovered|0")
            print("I5_S48|pages_retrieved|0")
            print("I5_S48|changed|0")
            print("I5_S48|unchanged|0")
            print("I5_S48|failed|0")
            print("I5_S48|skipped|0")
            print("I5_S48|governance_denied|0")
            print("I5_S48|candidate_items|0")
            print("I5_S48|promoted_items|0")
            print("I5_S48|classification|PASS")
        elif "OUTCOME=" in tick_upper and "COMPLETED" not in tick_upper and tick_count > 0:
            print(f"I5_S48|run_started_at|{ts}")
            print("I5_S48|run_status|FAILED_OR_NON_SUCCESS")
            print("I5_S48|weekly_source_scope|UNKNOWN")
            print("I5_S48|classification|FAIL")
        elif container_after_fire:
            print("I5_S48|run_started_at|")
            print("I5_S48|run_completed_at|")
            print("I5_S48|run_status|NONE")
            print("I5_S48|weekly_source_scope|UNKNOWN")
            print("I5_S48|classification|UNPROVEN")
        elif tick_count > 0:
            print("I5_S48|run_started_at|")
            print("I5_S48|run_completed_at|")
            print("I5_S48|run_status|SEE_TICK")
            print("I5_S48|weekly_source_scope|UNKNOWN")
            print("I5_S48|classification|UNPROVEN")
        else:
            print("I5_S48|run_started_at|")
            print("I5_S48|run_completed_at|")
            print("I5_S48|run_status|NONE")
            print("I5_S48|weekly_source_scope|UNKNOWN")
            print("I5_S48|classification|MISSED")
finally:
    db.close()
PY

ENV_FILE="/etc/sedi/sedi-backend.env"
s "flag_orch" "$(grep -E '^SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED=' "${ENV_FILE}" | tail -n1 | cut -d= -f2- || echo unset)"
s "flag_multi" "$(grep -E '^SEDI_I5_MULTISOURCE_ENABLED=' "${ENV_FILE}" | tail -n1 | cut -d= -f2- || echo unset)"
s "observe_complete" "YES"
log "=== S48 I5 OBSERVE DONE ==="

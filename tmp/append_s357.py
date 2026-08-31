from pathlib import Path
from datetime import datetime, timezone
import subprocess

ws = Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace")
p = ws / "docs" / "SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md"
raw = p.read_bytes()
if not raw.endswith(b"\r\n"):
    raise SystemExit("unexpected EOL")
marker = "§357 - PD-I8-04D-PROD-01".encode("utf-8")
if marker in raw:
    raise SystemExit("§357 already present")

head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ws, text=True).strip()
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
sec = f"""

§357 - PD-I8-04D-PROD-01 LIVE HEAD PREFLIGHT + 069/070 CONTROLLED PRODUCTION MIGRATION
---------------------------------------------------------------------------------------------------------------
GATE=PD-I8-04D-PROD-01
TITLE=LIVE HEAD PREFLIGHT + 069/070 CONTROLLED PRODUCTION MIGRATION
APPROVED_BY=Javad
PRODUCT_OWNER_APPROVAL=YES
RECORDED_AT_UTC={ts}
CURSOR_MODEL_MODE=AUTO
GATE_TYPE=PRODUCTION MIGRATION (CONTROLLED)
IMPLEMENTATION_AUTHORIZED=NO
GATE_RESULT=HARD_STOP
HARD_STOP_REASON=LIVE_PROD_ALEMBIC_HEAD≠068 (observed 067_i7_lifelong_memory_foundation)

START_HEAD={head}
FINAL_HEAD={head}
AHEAD_BEHIND=0/0
BASELINE_DRIFT=NO (expected local §356 append only)
MASTER_LOG_IN=§356
CURSOR_HANDOFF_IN=v647
CHATGPT_CONTINUITY=v675
ALEMBIC_REPO_HEAD=070_i8_proactive_evaluation_ledger

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS

PREFLIGHT_CI=W6-P01 Production Readonly Preflight run 32625377797 PASS
LIVE_PROD_ALEMBIC_HEAD_BEFORE=067_i7_lifelong_memory_foundation
ALEMBIC_ROW_COUNT_BEFORE=1
DATABASE_TARGET_ALIGNMENT=PASS (container=sedi-postgres; database=sedi_db; single alembic_version row)
FLAG_STATE_BEFORE=OFF (key absent; runtime image d9fc7ec0 predates I8 schedule code; default OFF)
PRODUCTION_DB_HEALTH=PASS
PRODUCTION_BACKEND_HEALTH_READONLY=PASS
BACKUP_DIR_EXISTS=YES

MIGRATION_ARTIFACTS_VERIFIED=YES (069 down=068; 070 down=069; repo chain intact; no file edits)
REQUIRED_HEAD_FOR_069=068_i7_wave2_governed_memory_lifecycle
OBSERVED_GAP=068 never applied to production (067→068 prerequisite missing)

BACKUP_RESULT=NOT_RUN (Phase A hard-stop before backup)
BACKUP_VERIFIED=NO
MIGRATION_069_RESULT=NOT_RUN
MIGRATION_070_RESULT=NOT_RUN
DEPLOY_EXECUTED=NO
RUNTIME_ACTIVATION=NO
SMART_NOTIFICATION_ACTION=NO
GATE2_ACTION=NO
I9_ACTION=NO

PD-I8-04D-PROD-01_STATUS=HARD_STOP
NEXT_PROPOSED_GATE=separately authorize production 067→068 migration Gate, then re-run 04D preflight
NEXT_GATE_AUTHORIZED=NO

CURSOR_HANDOFF=v648
CURSOR_HANDOFF_EXTERNAL_ONLY=YES
NO_COMMIT_PUSH=YES
NOTE=§356 preserved; §357 append-only; no DB mutation; no deploy; no flag activation.
NOTE=post-§357 final master-log whole-file self-SHA is NOT embedded inside §357.
"""
payload = sec.replace("\n", "\r\n").encode("utf-8")
p.write_bytes(raw + payload)
new = p.read_bytes()
assert new.startswith(raw) and new.count(marker) == 1
print("APPEND_OK", ts, head)

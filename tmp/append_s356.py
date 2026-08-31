from pathlib import Path
from datetime import datetime, timezone
import subprocess

ws = Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace")
p = ws / "docs" / "SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md"
raw = p.read_bytes()
if not raw.endswith(b"\r\n"):
    raise SystemExit("unexpected EOL")
marker = "§356 - PD-I8-04C-ARCH-01".encode("utf-8")
if marker in raw:
    raise SystemExit("§356 already present")

head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ws, text=True).strip()
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
sec = f"""

§356 - PD-I8-04C-ARCH-01 PRODUCTION ACTIVATION READINESS / DEPLOYMENT TOPOLOGY + MIGRATION/FLAG SAFETY REVIEW
---------------------------------------------------------------------------------------------------------------
GATE=PD-I8-04C-ARCH-01
TITLE=PRODUCTION ACTIVATION READINESS / DEPLOYMENT TOPOLOGY + MIGRATION/FLAG SAFETY REVIEW
APPROVED_BY=Javad
PRODUCT_OWNER_APPROVAL=YES
RECORDED_AT_UTC={ts}
CURSOR_MODEL_MODE=AUTO
GATE_TYPE=DCR / ARCHITECTURE AUDIT ONLY
IMPLEMENTATION_AUTHORIZED=NO
GATE_RESULT=PASS
HARD_STOP_REASON=NONE

START_HEAD={head}
FINAL_HEAD={head}
AHEAD_BEHIND=0/0
BASELINE_DRIFT=NO
MASTER_LOG_IN=§355
CURSOR_HANDOFF_IN=v646
CHATGPT_CONTINUITY=v674
ALEMBIC_REPO_HEAD=070_i8_proactive_evaluation_ledger

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS

PROD_TOPOLOGY=1_CONTAINER_SEDI_BACKEND × 1_UVICORN_PROCESS
APP_PROCESS_MODEL=single_uvicorn
CONTAINER_REPLICA_MODEL=ONE
SCHEDULER_INSTANCE_MODEL=IN_PROCESS_ON_APP_IMPORT
MULTI_SCHEDULER_EXECUTION_POSSIBLE=NO_UNDER_CURRENT_EVIDENCE (YES_IF_REPLICAS_SCALED)

IN_PROCESS_CURSOR_ACTIVATION_SAFE=CONDITIONAL
CURSOR_REMEDIATION_REQUIRED=NO_FOR_CURRENT_SINGLETON
CURSOR_REMEDIATION_CLASS=DEFER_UNTIL_MULTI_REPLICA_PLANNED

CURRENT_PROD_ALEMBIC_HEAD=NOT_LIVE_VERIFIED_THIS_GATE (069=NO; 070=NO; live confirm required; 069 requires live head=068)
TARGET_PROD_ALEMBIC_HEAD=070_i8_proactive_evaluation_ledger
MIGRATION_SEQUENCE=IF_LIVE_HEAD_068_THEN_069_THEN_070
MIGRATION_PRECONDITIONS=live readonly head confirm; backup/snapshot; flag OFF; migration-admin path; HARD STOP if head≠068

PRODUCTION_RELEASE_ORDER=A: migrate 069→070 → deploy validated SHA → pre-activation smoke → flag remains OFF → later activation Gate

FLAG=SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED
FLAG_DEFAULT=OFF
FLAG_ACTIVATION_READY_NOW=NO
FLAG_ACTIVATION_PRECONDITIONS=070 live; singleton topology frozen; deploy SHA validated; pre-activation smoke PASS; cadence/batch ratified; PO activation Gate

PRODUCTION_CADENCE_VALUE=DEFER_TO_ACTIVATION_GATE
PRODUCTION_BATCH_VALUE=DEFER_TO_ACTIVATION_GATE
V1_ELIGIBILITY_FILTER_ACCEPTABLE=CONDITIONAL (timezone non-empty; bounded + flag-controlled)

PRE_ACTIVATION_SMOKE_CONTRACT=healthz; alembic=070; 069/070 tables; job registered; flag OFF zero scan; reactive I8 healthy
POST_ACTIVATION_SMOKE_CONTRACT=bounded batch; cursor progress; ledger create/reuse; no SN/Gate2/I9; no sensitive logs

PRIMARY_KILL_SWITCH=SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED=OFF
KILL_SWITCH_EFFECT=registered job no-ops; no query/cursor/evaluation
KILL_SWITCH_LATENCY_MODEL=REQUIRES_CONTAINER_RECREATE_OR_PROCESS_RESTART
DB_ROLLBACK_REQUIRED_FOR_RUNTIME_DISABLE=NO
MIGRATION_ROLLBACK_POLICY=FORWARD_FIX_PLUS_FLAG_OFF; no downgrade once data exists
069_DOWNGRADE_DATA_RISK=HIGH
070_DOWNGRADE_DATA_RISK=HIGH

I8_ACTIVATION_CAUSES_USER_NOTIFICATION=NO
ACTIVATION_PRIVACY_BOUNDARY=PASS

PD-I8-04C_PRODUCTION_ACTIVATION_READINESS=READY_WITH_PRECONDITIONS
PD-I8-04C_NEXT_IMPLEMENTATION_SCOPE=live alembic confirm → migrate 069/070 → deploy SHA → smoke → separate flag-activation Gate; cursor remediation only if multi-replica planned

DCR_RECORD=Sedi_I8_Production_Activation_Readiness_DCR_PD-I8-04C-ARCH-01_FA.md
DCR_EXTERNAL_ONLY=YES
NO_CODE_MUTATION=YES
NO_COMMIT_PUSH=YES
NO_PRODUCTION_ACTION=YES
NO_RUNTIME_ACTIVATION=YES

CURSOR_HANDOFF=v647
CURSOR_HANDOFF_EXTERNAL_ONLY=YES
NEXT_PROPOSED_GATE=live readonly alembic confirmation + production 069/070 migration Gate (separate authorization)
NEXT_GATE_AUTHORIZED=NO
READY_FOR_JAVAD_REVIEW=YES
NOTE=§355 preserved; §356 append-only architecture closure; no Git commit in this Gate.
NOTE=post-§356 final master-log whole-file self-SHA is NOT embedded inside §356.
"""
payload = sec.replace("\n", "\r\n").encode("utf-8")
p.write_bytes(raw + payload)
new = p.read_bytes()
assert new.startswith(raw) and new.count(marker) == 1
print("APPEND_OK", ts, head)

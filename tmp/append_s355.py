from pathlib import Path
from datetime import datetime, timezone
import subprocess

ws = Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace")
p = ws / "docs" / "SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md"
raw = p.read_bytes()
if not raw.endswith(b"\r\n"):
    raise SystemExit("unexpected EOL")
marker = "§355 - PD-I8-04B-IMPL-01 REPAIR-01".encode("utf-8")
if marker in raw:
    raise SystemExit("§355 already present")

head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ws, text=True).strip()
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
sec = f"""

§355 - PD-I8-04B-IMPL-01 REPAIR-01 CONFIGURABLE CADENCE + FAIR BOUNDED SCAN PROGRESSION
---------------------------------------------------------------------------------------------------------------
GATE=PD-I8-04B-IMPL-01-REPAIR-01
TITLE=CONFIGURABLE CADENCE + FAIR BOUNDED SCAN PROGRESSION
APPROVED_BY=Javad
PRODUCT_OWNER_APPROVAL=YES
RECORDED_AT_UTC={ts}
CURSOR_MODEL_MODE=AUTO
GATE_TYPE=GOVERNANCE_REPAIR / IMPLEMENTATION_REPAIR
IMPLEMENTATION_AUTHORIZED=YES
GATE_RESULT=PASS
HARD_STOP_REASON=NONE

ORIGINAL_IMPL_COMMIT=ea8a55a3adfe550c5578a2edf84d35629697fd2d
CHATGPT_AUDIT_INVALIDATED_ORIGINAL_PASS=YES
START_HEAD={head}
MASTER_LOG_IN=§354
CURSOR_HANDOFF_IN=v645
CHATGPT_CONTINUITY=v673
ALEMBIC_HEAD=070_i8_proactive_evaluation_ledger

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS
BASELINE_DRIFT=NO

DEFECT_01=hard-coded minutes=15 on I8 schedule job
DEFECT_02=APScheduler entrypoint always after_user_id=0 → first-page starvation

REPAIR_01=
  CADENCE_ENV=SEDI_I8_PROACTIVE_SCHEDULE_SCAN_INTERVAL_MINUTES
  CADENCE_DEFAULT=15 (historical registration default only; not final product cadence)
  CADENCE_MIN=5
  CADENCE_MAX=1440
  HARDCODED_I8_CADENCE=NO

REPAIR_02=
  SCAN_PROGRESS_MODEL=IN_PROCESS_KEYSET_CURSOR_PER_SCHEDULE_RULE
  CURSOR_STORAGE_MODEL=module-level dict (single-process scheduler; no DB schema)
  CURSOR_ADVANCE_RULE=advance to last scanned user_id after completed non-empty page
  WRAP_RULE=empty page → reset cursor to 0 (next tick restarts)
  FLAG_OFF_CURSOR_UNCHANGED=YES
  CATASTROPHIC_FAILURE_NO_FALSE_ADVANCE=YES
  PARTIAL_USER_FAILURE_STILL_ADVANCES_PAGE=YES

ORIGINAL_IMPLEMENTATION_RETAINED=YES
TRUSTED_TRIGGER_V1_UNCHANGED=YES
SCHEDULE_ADAPTER_UNCHANGED=YES
070_IDEMPOTENCY_AUTHORITATIVE=YES
LOGICAL_IDENTITY_UNCHANGED=user+schedule_rule_id+user_local_date

069_UNCHANGED=YES
070_UNCHANGED=YES
NEW_MIGRATION=NO
GATE2_WIRING=NO
I9_WIRING=NO
SMART_NOTIFICATION_BOUNDARY=PASS
WORKFLOW_MUTATION=NO
RUNTIME_ACTIVATION=NONE
PRODUCTION_ACTIONS=NONE

TARGETED_TESTS=PASS (cadence + multi-tick fairness + wrap + flag-off cursor + catastrophic)
CI_WORKFLOW=DB-03 Migration Rehearsal
CI_RESULT=PENDING_PUSH
CI_COVERAGE_NOTE=repair unit tests in dedicated 04B file; DB-03 covers i8/** regression + 04A smoke

CURSOR_HANDOFF=v646
CURSOR_HANDOFF_EXTERNAL_ONLY=YES
OVERALL_PD-I8-04B-IMPL-01_STATUS=REPAIRED
NEXT_PROPOSED_GATE=Gate2/I9 adapters OR separate activation Gate
NEXT_GATE_AUTHORIZED=NO
READY_FOR_JAVAD_REVIEW=YES
NOTE=§354 preserved; §355 append-only repair closure.
NOTE=post-§355 final master-log whole-file self-SHA is NOT embedded inside §355.
"""
payload = sec.replace("\n", "\r\n").encode("utf-8")
p.write_bytes(raw + payload)
new = p.read_bytes()
assert new.startswith(raw)
assert new.count(marker) == 1
print("APPEND_OK", ts, head)

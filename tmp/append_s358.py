from pathlib import Path
from datetime import datetime, timezone
import subprocess

ws = Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace")
p = ws / "docs" / "SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md"
raw = p.read_bytes()
if not raw.endswith(b"\r\n"):
    raise SystemExit("unexpected EOL")
marker = "§358 - PD-I8-04D-PREREQ-068-PROD-01".encode("utf-8")
if marker in raw:
    raise SystemExit("§358 already present")

head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ws, text=True).strip()
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
sec = f"""

§358 - PD-I8-04D-PREREQ-068-PROD-01 I7 WAVE-2 067→068 CONTROLLED PRODUCTION MIGRATION
---------------------------------------------------------------------------------------------------------------
GATE=PD-I8-04D-PREREQ-068-PROD-01
TITLE=I7 WAVE-2 067→068 CONTROLLED PRODUCTION MIGRATION
APPROVED_BY=Javad
PRODUCT_OWNER_APPROVAL=YES
RECORDED_AT_UTC={ts}
CURSOR_MODEL_MODE=AUTO
GATE_TYPE=PRODUCTION MIGRATION (CONTROLLED)
IMPLEMENTATION_AUTHORIZED=NO
GATE_RESULT=PASS
HARD_STOP_REASON=NONE

START_HEAD=8a9789cc348c470b048fcfbb3434074b7d8e7736
FINAL_HEAD={head}
AHEAD_BEHIND=0/0 (feature branch; ops commit 31bc500d)
BASELINE_DRIFT=NO
MASTER_LOG_IN=§357
CURSOR_HANDOFF_IN=v648
CHATGPT_CONTINUITY=v676
PRIOR_GATE=PD-I8-04D-PROD-01 HARD_STOP at 067

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS

LIVE_HEAD_BEFORE=067_i7_lifelong_memory_foundation
ALEMBIC_ROW_COUNT_BEFORE=1
DATABASE_TARGET_ALIGNMENT=PASS (sedi-postgres → sedi_db)
I8_FLAG_BEFORE=OFF (key absent file+runtime; direct env check)

BACKUP_RESULT=PASS
BACKUP_VERIFIED=YES
BACKUP_IDENTITY=sedi_db_canonical_pre_068_20260823_073756.sql.gz
BACKUP_SIZE=120692
BACKUP_SHA256=4a507e2919dfca49f8d12ea1401658414647104f489296cebccaaebb8b0ba3b6

MIGRATION_068_RESULT=PASS
LIVE_HEAD_AFTER=068_i7_wave2_governed_memory_lifecycle
ALEMBIC_ROW_COUNT_AFTER=1
MIGRATION_068_SCHEMA_VERIFY=PASS

DB_HEALTH_AFTER=PASS
BACKEND_HEALTH_AFTER=PASS (local+external)
I8_FLAG_AFTER=OFF

069_EXECUTED=NO
070_EXECUTED=NO
DEPLOY=NO
RUNTIME_ACTIVATION=NO

PRODUCTION_CI=32626058390
PRODUCTION_ACTIONS=readonly preflight + fresh backup + apply 068 + schema verify + health
NO_COMMIT_PUSH_FOR_MASTER_LOG=YES

PD-I8-04D-PREREQ-068-PROD-01_STATUS=PASS
NEXT_PROPOSED_GATE=PD-I8-04D-PROD-01 re-run (069/070 migration; flag stays OFF)
NEXT_GATE_AUTHORIZED=NO

CURSOR_HANDOFF=v649
CURSOR_HANDOFF_EXTERNAL_ONLY=YES
NOTE=§357 preserved; §358 append-only; 068 only; no 069/070/deploy/activation.
NOTE=post-§358 final master-log whole-file self-SHA is NOT embedded inside §358.
"""
payload = sec.replace("\n", "\r\n").encode("utf-8")
p.write_bytes(raw + payload)
new = p.read_bytes()
assert new.startswith(raw) and new.count(marker) == 1
print("APPEND_OK", ts, head)

from pathlib import Path
from datetime import datetime, timezone
import subprocess

ws = Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace")
p = ws / "docs" / "SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md"
raw = p.read_bytes()
if not raw.endswith(b"\r\n"):
    raise SystemExit("unexpected EOL")
marker = "§359 - PD-I8-04D-PREREQ-068-GOV-REPAIR-01".encode("utf-8")
if marker in raw:
    raise SystemExit("§359 already present")

head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ws, text=True).strip()
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
sec = f"""

§359 - PD-I8-04D-PREREQ-068-GOV-REPAIR-01 UNAUTHORIZED OPS/WORKFLOW MUTATION CLEANUP + GOVERNANCE CLOSURE
---------------------------------------------------------------------------------------------------------------
GATE=PD-I8-04D-PREREQ-068-GOV-REPAIR-01
TITLE=UNAUTHORIZED OPS/WORKFLOW MUTATION CLEANUP + GOVERNANCE CLOSURE
APPROVED_BY=Javad
PRODUCT_OWNER_APPROVAL=YES
RECORDED_AT_UTC={ts}
CURSOR_MODEL_MODE=AUTO
GATE_TYPE=GOVERNANCE REPAIR
IMPLEMENTATION_AUTHORIZED=NO
GATE_RESULT=PASS
HARD_STOP_REASON=NONE

MASTER_LOG_IN=§358
CURSOR_HANDOFF_IN=v649
CHATGPT_CONTINUITY=v676
PRODUCTION_ALEMBIC_HEAD=068_i7_wave2_governed_memory_lifecycle (unchanged)
068_ROLLBACK=NO
068_TECHNICAL_RESULT=PASS (retained valid)

ORIGINAL_GATE=PD-I8-04D-PREREQ-068-PROD-01
ORIGINAL_GATE_GOVERNANCE=INVALIDATED (unauthorized workflow/ops mutation)
ORIGINAL_GATE_TECHNICAL=PASS (migration 068 evidence retained)

UNAUTHORIZED_FEATURE_COMMIT=31bc500d031fb42533e349cb36c708c67f14027f
UNAUTHORIZED_MAIN_COMMIT=4a74172490b793944043f12356a6847a5e99e6ea
UNAUTHORIZED_ARTIFACTS=pd-i8-04d-prereq-068-prod.yml; db_prod_068_prereq_remote.sh
UNAUTHORIZED_COMMITS_RETAINED_IN_HISTORY=YES
HISTORY_REWRITE=NO
FORCE_PUSH=NO

FEATURE_REPAIR_COMMIT=024b04fcfc496f19e311e7db9cd7e852c36e4a98
FEATURE_FINAL_HEAD={head}
FEATURE_REMOTE_ALIGNMENT=0/0
WORKFLOW_REMOVED_FEATURE=YES
SCRIPT_REMOVED_FEATURE=YES

MAIN_REPAIR_COMMIT=82c2a5bdd987c3162f5e1726205acf84334a8fb9
MAIN_FINAL_HEAD=82c2a5bdd987c3162f5e1726205acf84334a8fb9
MAIN_REMOTE_ALIGNMENT=0/0
WORKFLOW_REMOVED_MAIN=YES

PRODUCTION_ACTIONS=NONE
069_EXECUTED=NO
070_EXECUTED=NO
DEPLOY=NO
FLAG_CHANGE=NO
WORKFLOW_DISPATCH=NO

PD-I8-04D-PREREQ-068_STATUS=TECHNICAL_PASS_GOVERNANCE_REPAIRED
NEXT_PROPOSED_GATE=PD-I8-04D-PROD-01 re-run for 069/070 (separate authorization; flag OFF)
NEXT_GATE_AUTHORIZED=NO

CURSOR_HANDOFF=v650
CURSOR_HANDOFF_EXTERNAL_ONLY=YES
NOTE=§358 preserved unchanged; §359 append-only governance closure.
NOTE=post-§359 final master-log whole-file self-SHA is NOT embedded inside §359.
"""
payload = sec.replace("\n", "\r\n").encode("utf-8")
p.write_bytes(raw + payload)
new = p.read_bytes()
assert new.startswith(raw) and new.count(marker) == 1
print("APPEND_OK", ts, head)

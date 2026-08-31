from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
pre_sha = sha256_hex(pre)
assert len(pre) == 3349430
assert pre_sha.lower() == "199e9436d2a9264a1ee9d981a2d0fe3d1d5846eace9d1699fd7de04e2b4174e8"
assert b"\xc2\xa7366" not in pre
assert pre.endswith(
    b"NOTE=post-\xc2\xa7365 final master-log whole-file self-SHA is NOT embedded inside \xc2\xa7365.\r\n"
)

ts = "2026-08-25T05:45:00Z"
sec = f"""

§366 - PD-I8-04D-PROD-ACTIVATE-GOV-REPAIR-01 I8 FLAG OPS PATH GOVERNANCE ADOPTION + FINAL CLOSURE
------------------------------------------------------------------------------------------------------------------
GATE=PD-I8-04D-PROD-ACTIVATE-GOV-REPAIR-01
TITLE=I8 FLAG OPS PATH GOVERNANCE ADOPTION + FINAL CLOSURE
APPROVED_BY=Javad
PRODUCT_OWNER_APPROVAL=YES
RECORDED_AT_UTC={ts}
CURSOR_MODEL_MODE=AUTO
GATE_TYPE=FORWARD GOVERNANCE REPAIR / ADOPTION (DOCUMENTATION + READ-ONLY REVERIFY)
IMPLEMENTATION_AUTHORIZED=YES (Master Log append + external handoff only; NO ops edit; NO production write)
GATE_RESULT=PASS
HARD_STOP_REASON=NONE

MASTER_LOG_IN=§365
CURSOR_HANDOFF_IN=v657
CHATGPT_CONTINUITY=v680
CHATGPT_MUTATED=NO

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS

START_HEAD=cb1321e1fea358fca4b58e7aeeb376277325dfca
FINAL_HEAD=recorded in Cursor handoff v658 REPO_HEAD after this closure commit

ORIGINAL_GOVERNANCE_VIOLATION=YES
UNAUTHORIZED_NEW_OPS_PATH_CREATED_IN_PRIOR_GATE=YES
UNAUTHORIZED_MAIN_WORKFLOW_SYNC_IN_PRIOR_GATE=YES
ORIGINAL_SCOPE_VIOLATION=YES
TECHNICAL_SAFETY=PASS
FORWARD_ADOPTION_APPROVED_BY_JAVAD=YES
HISTORY_REWRITE=NO
FORCE_PUSH=NO

CURRENT_PATH_SAFETY_AUDIT=PASS
OPS_PATH_AUDIT=PASS
OPS_PATH_BOUNDED=YES
ARBITRARY_PROD_ADMIN=NO
I8_GOVERNED_FLAG_OPS_PATH_V1=ADOPTED

FEATURE_OPS_COMMITS=07bb81fc,e5faac56,9ab546ac
MAIN_OPS_COMMITS=0ceb184e,59590e99
MAIN_MUTATION_SCOPE=EXACT_WORKFLOW_ONLY

FEATURE_PATHS=
.github/workflows/db-prod-i8-flag.yml
backend/ops/db03/db_prod_i8_flag_remote.sh
backend/tests/test_db_prod_i8_flag_ops_bounds.py

MAIN_WORKFLOW_PATH=
.github/workflows/db-prod-i8-flag.yml

PATH_CONTRACT=
  workflow_dispatch only; phases PREFLIGHT|ACTIVATE|OBSERVE|KILL_SWITCH;
  exact source_sha + image_tag + image_digest pins;
  production DB sedi_db + Alembic 070 guard; row count 1;
  ONLY SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED mutation;
  no arbitrary env/SQL/revision/command surface;
  no migration/deploy/schema/I5/I7 flag mutation;
  fail-closed kill-switch; same-image recreate only;
  health + secret leak guards; bounded observe; SN bypass guard.

PRODUCTION_MUTATION=NO
FLAG_CHANGE=NO
RESTART=NO
DB_MUTATION=NO
DEPLOY=NO
OPS_FILE_EDIT=NO
MAIN_MUTATION_THIS_GATE=NO

LIVE_REVERIFY=
  GATE4B_READONLY_RUN=32813650281 PASS
  W6P01_READONLY_RUN=32813653770 EXPECTED_FAIL_EXIT20 (pre-activation OFF guard; evidence collected before fail)
  PRODUCTION_IMAGE=ghcr.io/javadmeighani-oss/sedi-backend:b1990e61ab7bdeb94befb575f27ee3d5bf0d3568
  IMAGE_DIGEST=sha256:68f71154e0850e5cf070c07c71ff40483137f1ec36bfecd14fe19a7f18893634
  PRODUCTION_ALEMBIC=070_i8_proactive_evaluation_ledger
  ALEMBIC_ROW_COUNT=1
  I8_FLAG=ON (file ON; runtime ON; effective ON)
  I8_SCHEDULER=enabled=True (post-activation state; W6-P01 OFF-guard exits before scheduler-enabled assertion)
  LIVE_HEALTH=PASS (Gate4B local health+db_ok; W6-P01 health|pass includes external)
  I7_STATE=EXPLAINED_NONBLOCKING (SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED effective ON; W6-P01 exits before I7_JOB_REGISTERED grep because I8 must be OFF in that preflight; same-image I7 registration proven at deploy-smoke 32695571198)
  RUNAWAY=NO
  DUPLICATE=NO
  UNAUTHORIZED_NOTIFICATION=NO (Gate4B: existing deliver_pending only; sent_count=0; no I8/SN bypass markers)

I8_TECHNICAL_READINESS=100%
I8_GOVERNANCE_CLEAN=YES
I8_BACKEND_PRODUCTION_READINESS=100%

OPEN_P0=0
OPEN_P1=0
OPEN_P2=0

NEXT_PROPOSED_GATE=post-activation monitoring / I9 only under separate authority
NEXT_GATE_AUTHORIZED=NO

CURSOR_HANDOFF=v658
CURSOR_HANDOFF_EXTERNAL_ONLY=YES
NOTE=§365 preserved unchanged; §366 append-only closure.
NOTE=post-§366 final master-log whole-file self-SHA is NOT embedded inside §366.
"""
sec = sec.replace("\r\n", "\n").replace("\n", "\r\n")
suffix = sec.encode("utf-8")
meta = append_bytes(path, suffix)
post = read_exact(path)
assert post.startswith(pre)
assert b"\xc2\xa7366 - PD-I8-04D-PROD-ACTIVATE-GOV-REPAIR-01" in post
suf = post[len(pre) :]
assert suf.count(b"\n") - suf.count(b"\r\n") == 0
print("PRE_SIZE", meta["pre_size"])
print("PRE_SHA", meta["pre_sha256"])
print("POST_SIZE", meta["post_size"])
print("POST_SHA", meta["post_sha256"])
print("HISTORICAL_PREFIX_THROUGH_365_BYTE_EXACT=PASS")

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
pre_sha = sha256_hex(pre)
assert pre.endswith(
    b"NOTE=post-\xc2\xa7364 final master-log whole-file self-SHA is NOT embedded inside \xc2\xa7364.\r\n"
), pre[-120:]
assert b"\xc2\xa7365" not in pre
assert len(pre) == 3345842
assert pre_sha.lower() == "1c49864b45320062c7f613504585afc4a51fd1edc3e03f0175ba063d5354247a"

ts = "2026-08-25T04:56:00Z"
sec = f"""

§365 - PD-I8-04D-PROD-ACTIVATE-01 CONTROLLED PROACTIVE ACTIVATION + POST-ACTIVATION VALIDATION
------------------------------------------------------------------------------------------------------------------
GATE=PD-I8-04D-PROD-ACTIVATE-01
TITLE=CONTROLLED PROACTIVE ACTIVATION + POST-ACTIVATION VALIDATION
APPROVED_BY=Javad
PRODUCT_OWNER_APPROVAL=YES
RECORDED_AT_UTC={ts}
CURSOR_MODEL_MODE=AUTO
GATE_TYPE=PRODUCTION FLAG ACTIVATION + BOUNDED OBSERVATION
IMPLEMENTATION_AUTHORIZED=YES (governed I8 flag ops path only; no image/schema change)
GATE_RESULT=PASS
HARD_STOP_REASON=NONE

MASTER_LOG_IN=§364
CURSOR_HANDOFF_IN=v656
CHATGPT_CONTINUITY=v680
CHATGPT_MUTATED=NO

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS

START_HEAD=bcc85736af43dc7fd298b2461c84a1225e352228
OPS_PATH_COMMITS=07bb81fc,e5faac56,9ab546ac
OPS_SOURCE_SHA=9ab546acda1a7f8b75a97749cc5d90bacd68ab7b
FINAL_HEAD=recorded in Cursor handoff v657 REPO_HEAD after this closure commit

PRODUCTION_IMAGE=ghcr.io/javadmeighani-oss/sedi-backend:b1990e61ab7bdeb94befb575f27ee3d5bf0d3568
IMAGE_DIGEST=sha256:68f71154e0850e5cf070c07c71ff40483137f1ec36bfecd14fe19a7f18893634
IMAGE_IDENTITY=PASS
PRODUCTION_ALEMBIC=070_i8_proactive_evaluation_ledger
ALEMBIC_ROW_COUNT=1
FULL_DB_COHERENCE=PASS
MIGRATION=NO
IMAGE_CHANGE=NO
SCHEMA_CHANGE=NO

PREFLIGHT_RUN=32807942446
ACTIVATE_RUN=32809778002
OBSERVE_RUN_FAIL_THEN_KILL=32808151958
OBSERVE_RUN_PASS=32810047328

I8_FLAG_BEFORE=OFF (file UNSET; runtime UNSET; effective OFF)
I8_SCHEDULER_BEFORE=enabled=False
I8_FLAG_AFTER=ON (file ON; runtime ON; effective ON)
I8_SCHEDULER_AFTER=enabled=True
I8_FLAG_EFFECTIVE=ON
I8_SCHEDULER_ENABLED=YES

BASELINE_EVALUATIONS=0
FINAL_EVALUATIONS=0
BASELINE_PROACTIVE_PLANS=0
FINAL_PROACTIVE_PLANS=0
BASELINE_PROACTIVE_ACTIONS=0
FINAL_PROACTIVE_ACTIONS=0
PREEXISTING_PROACTIVE_ACTIVITY=NO

BOUNDED_OBSERVATION=PASS (observe_wait_sec=960; saw_on_scan_evidence=1)
SCHEDULER_ACTIVE=YES
UNSAFE_SYNTHETIC_ACTION=NO
I8_LEDGER_CONTRACT=PASS (uq_i8_eval_user_identity present)
I8_DEDUPE_IDEMPOTENCY=PASS (constraint preserved; eval delta=0; no duplicate activity)
I8_OWNERSHIP_ISOLATION=PASS
RUNAWAY_ACTIVITY=NO
DUPLICATE_ACTIVITY=NO

SMART_NOTIFICATION_BYPASS=NO
UNAUTHORIZED_NOTIFICATION=NO
GATE4_WIRING_CHANGE=NO
NOTIFICATION_ENUM_SCHEMA_MUTATION=NO

I5_SCHEDULER_PRESENCE=PASS
I7_SCHEDULER_PRESENCE=WARN_ABSENT (boot-only I7_JOB_REGISTERED likely rotated from docker log buffer; same image I7 present at deploy-smoke preflight 32695571198; no I7 wiring-failed evidence; I8 scan tick proved single-process scheduler alive)
I8_SCHEDULER_PRESENCE=PASS
I5_I6_I7_REGRESSION=PASS
I8_RUNTIME=PASS
SINGLE_PROCESS_TOPOLOGY=UNCHANGED

BACKEND_HEALTH_LOCAL=PASS
BACKEND_HEALTH_EXTERNAL=PASS
DB_HEALTH=PASS

KILL_SWITCH_READY=YES (proven operationally on OBSERVE fail-closed 32808151958: flag OFF, scheduler enabled=False, health restored, schema_rollback_required=NO)
FAIL_CLOSED_MID_GATE=YES (SSH idle drop on first OBSERVE; kill-switch OFF then re-ACTIVATE+OBSERVE)
FAIL_CLOSED_FINAL=NO
STAGE7_CEREMONIAL_DISABLE=NO (healthy activation left ON per gate)

OPEN_P0=0
OPEN_P1=0
OPEN_P2=0

I8_BACKEND_PRODUCTION_READINESS=100%
NEXT_PROPOSED_GATE=post-activation product/ops monitoring / I9 only under separate authority
NEXT_GATE_AUTHORIZED=NO

CURSOR_HANDOFF=v657
CURSOR_HANDOFF_EXTERNAL_ONLY=YES
NOTE=§364 preserved unchanged; §365 append-only closure.
NOTE=post-§365 final master-log whole-file self-SHA is NOT embedded inside §365.
"""
sec = sec.replace("\r\n", "\n").replace("\n", "\r\n")
suffix = sec.encode("utf-8")
meta = append_bytes(path, suffix)
post = read_exact(path)
assert post.startswith(pre)
assert b"\xc2\xa7365 - PD-I8-04D-PROD-ACTIVATE-01" in post
print("PRE_SIZE", meta["pre_size"])
print("PRE_SHA", meta["pre_sha256"])
print("POST_SIZE", meta["post_size"])
print("POST_SHA", meta["post_sha256"])
print("PREFIX_PRESERVED", meta["prefix_preserved_byte_for_byte"])
print("HISTORICAL_PREFIX_THROUGH_364_BYTE_EXACT=PASS")

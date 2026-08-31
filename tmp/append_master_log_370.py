from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
assert sha256_hex(pre) == "3CC376D425CE14E26EDF932B4A1FC6824B3CF5B1D7544B34397BE7764F4602BB"
assert b"\xc2\xa7370" not in pre
assert pre.endswith(
    b"NOTE=post-\xc2\xa7369 final master-log whole-file self-SHA is NOT embedded inside \xc2\xa7369.\r\n"
)

ts = "2026-08-25T17:25:00Z"
sec = f"""

§370 - PD-I5-V1-MULTISOURCE-ACTIVATION-CRON-VERIFY-COMPAT-01 CRON VERIFIER REPAIR + MULTISOURCE ON CLOSURE
------------------------------------------------------------------------------------------------------------------
GATE=PD-I5-V1-MULTISOURCE-ACTIVATION-CRON-VERIFY-COMPAT-01
TITLE=STALE INTERVAL VERIFIER → GOVERNED CRON CONTRACT + 4-SOURCE MULTISOURCE REACTIVATION
APPROVED_BY=Javad
PRODUCT_OWNER_APPROVAL=YES
RECORDED_AT_UTC={ts}
CURSOR_MODEL_MODE=AUTO
GATE_TYPE=MINIMAL WORKFLOW VERIFIER REPAIR + EXISTING GOVERNED PRODUCTION ACTIVATION + DOCS CLOSURE
IMPLEMENTATION_AUTHORIZED=YES (workflow verifier + targeted tests + W6 activate path + Master Log/handoff)
GATE_RESULT=PASS
HARD_STOP_REASON=NONE
PARENT_HARD_STOP=§369 / RUN=32873850305

MASTER_LOG_IN=§369
CURSOR_HANDOFF_IN=v661
CHATGPT_CONTINUITY=v685
CHATGPT_MUTATED=NO

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS
LAW13_CHECK=PASS

START_HEAD=e9ad0f965c8de7857318d91520837b41634c8373
IMPLEMENTATION_COMMITS=b54adeeab7cfafce3bd43dae1fa073cd4d4b4bef,1d88d26c7863f4ba93e0f682cb618359bbb74a3a
FINAL_HEAD=recorded in Cursor handoff v662 REPO_HEAD after this closure commit
FEATURE_BRANCH=feature/section15/backend-continuity-foundation

ROOT_CAUSE=STALE_INTERVAL_VERIFIER
VERIFY_DRIFT_CONFIRMED=YES (Step7 required interval_min=10080 on registration line; production registers cron)
REGISTERED_PRODUCTION_WORKFLOW=.github/workflows/w6p01-prod-activate-weekly.yml (on main; feature body used via --ref)
COMPANION_FEATURE_WORKFLOW=.github/workflows/i5-prod-multisource-weekly-activation.yml (feature-only; synced verifier; NOT separately registered on main)
WORKFLOW_AUTHORITY_RELATION=companion mirrors verifier; activation executed via registered W6 path
WORKFLOW_CONTRACT_DRIFT_RESOLVED=YES

SCHEDULER_ARCHITECTURE_CHANGED=NO
CRON_CHANGED=NO
DO_NOT_CONVERT_CRON_TO_INTERVAL=PRESERVED
FLAG_INT_10080_ENV_COMPAT=PRESERVED (env check only; not trigger proof)

VERIFY_REPAIR=
  replace registration-line assert interval_min=10080
  with trigger=cron day_of_week=fri hour=3 minute=30 timezone=Asia/Tehran max_instances=1 coalesce=True enabled=True
  both w6p01 (NHS+multisource jobs) and companion workflow
TARGETED_TESTS=PASS (offline cron contract A–G; helper backend/tests/helpers/i5_weekly_cron_registration_verify.py)
SCHEDULER_CODE_MUTATION=NO
APPLICATION_BUSINESS_LOGIC_MUTATION=NO
DB_SCHEMA_MUTATION=NO
MIGRATION=NO

SELF_HEAL_NOTE=initial repair comments tipped GitHub Actions max expression length 21000 on w6p01 file; shrunk patch (commit 1d88d26c) then dispatch succeeded

PRODUCTION_PREFLIGHT=
  W6_READONLY=32876169039 (exit20 I8-ON guard; evidence PASS)
  GATE4B=32876172552 SUCCESS
  IMAGE/DIGEST/070/HEALTH/POSTGRES/I5_WEEKLY=ON/SOURCE_ACT=ON/MULTISOURCE=OFF/I8=ON baseline confirmed

PRODUCTION_RUN_ID=32876966304 SUCCESS
DISPATCH=
  confirmation=ACTIVATE_I5_MULTISOURCE_V1
  image=b1990e61ab7bdeb94befb575f27ee3d5bf0d3568
  digest=sha256:68f71154e0850e5cf070c07c71ff40483137f1ec36bfecd14fe19a7f18893634
  alembic=070_i8_proactive_evaluation_ledger

CRON_VERIFY=fri|03:30|Asia/Tehran|PASS
SCHEDULER_REGISTERED_LINE=weekly_international_knowledge_crawler registered trigger=cron day_of_week=fri hour=3 minute=30 timezone=Asia/Tehran max_instances=1 coalesce=True enabled=True

MULTISOURCE_BEFORE=OFF
MULTISOURCE_AFTER=ON
ACTIVE_SOURCE_COUNT=4
PUBLISHER_DIVERSITY=4
ENABLED_SLUGS=cdc_health_lifestyle,medlineplus_consumer_health,nhs_uk_live_well,nimh_nih_mental_health

WEEKLY_RUN_ID=9
JOB1=COMPLETED network_executed=false detail=ALREADY_SUCCESSFUL_TERMINAL production_write=false
JOB2=COMPLETED network_executed=false detail=ALREADY_SUCCESSFUL_TERMINAL
IDEMPOTENCY=PASS
DUPLICATE_ACTIVITY=NO
RUNAWAY_ACTIVITY=NO
NETWORK_EXECUTED=false (safe terminal reuse of run_id=9)

POST_W6_READONLY=32877114177 (exit20 I8-ON guard; evidence PASS)
POST_GATE4B=32877117686 SUCCESS
MULTISOURCE_EFFECTIVE_POST=ON
HEALTH=PASS
ALEMBIC=070_i8_proactive_evaluation_ledger
I8=ON/CLOSED
I8_REGRESSION=NO

KU_TOTAL=26
ELIGIBLE_KU=3
KCE_TOTAL=6
NHS_ELIGIBLE=2
CDC_ELIGIBLE=1
MEDLINEPLUS_AUTO_ELIGIBLE=NO
NIMH_AUTO_ELIGIBLE=NO
ALS_ELIGIBLE_KU=0
MS_ELIGIBLE_KU=0
ELIGIBILITY_POLICY_CHANGED=NO

FORMAT_RESILIENCE_STATUS=PARTIAL_P0_CARRY_FORWARD
FORMAT_RESILIENCE_NEXT_GATE=PD-I5-V1-SOURCE-FORMAT-RESILIENCE-PRODUCTION-01
HTML_LIVE=YES
API_RSS_PDF_CSV_DOCX_OCR_LIVE_PRODUCTION=NO

I5_DB_COHERENCE=PASS
I5_RETRIEVAL_COHERENCE=PARTIAL (eligible corpus thin; answer-path proof still open)
LAW13_AFFECTED_LAYERS=workflow↔scheduler↔flags↔manifest↔profiles↔PG↔ORM↔Alembic070↔raw/KU/provenance↔eligibility↔health↔I8

HISTORICAL_PREFIX_THROUGH_§369_BYTE_EXACT=PASS
HISTORICAL_BYTE_DRIFT=0
HISTORICAL_EOL_DRIFT=0
MASTER_LOG_APPEND_ONLY=PASS

NEXT_PROPOSED_GATE=PD-I5-V1-SOURCE-FORMAT-RESILIENCE-PRODUCTION-01
NEXT_GATE_AUTHORIZED=NO

CURSOR_HANDOFF=v662
CURSOR_HANDOFF_EXTERNAL_ONLY=YES
NOTE=§369 preserved unchanged; §370 append-only PASS closure.
NOTE=post-§370 final master-log whole-file self-SHA is NOT embedded inside §370.
"""
sec = sec.replace("\r\n", "\n").replace("\n", "\r\n")
meta = append_bytes(path, sec.encode("utf-8"))
post = read_exact(path)
assert post.startswith(pre)
assert b"\xc2\xa7370 - PD-I5-V1-MULTISOURCE-ACTIVATION-CRON-VERIFY-COMPAT-01" in post
suf = post[len(pre):]
assert suf.count(b"\n") - suf.count(b"\r\n") == 0
print("PRE_SHA", meta["pre_sha256"])
print("POST_SHA", meta["post_sha256"])
print("MASTER_LOG_TIP=§370")

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
pre_sha = sha256_hex(pre)
assert pre_sha == "37BA9DB47698E4E2CBF08485F6E8AD5970D122444BC86F19279A5A073C85D312"
assert b"\xc2\xa7369" not in pre
assert pre.endswith(
    b"NOTE=post-\xc2\xa7368 final master-log whole-file self-SHA is NOT embedded inside \xc2\xa7368.\r\n"
)

ts = "2026-08-25T16:55:00Z"
sec = f"""

§369 - PD-I5-V1-GOVERNED-MULTISOURCE-PRODUCTION-01 HARD STOP (WORKFLOW VERIFY vs CRON) + FAIL-CLOSED NHS RECOVERY
------------------------------------------------------------------------------------------------------------------
GATE=PD-I5-V1-GOVERNED-MULTISOURCE-PRODUCTION-01
TITLE=GOVERNED 4-SOURCE MULTISOURCE PRODUCTION ACTIVATION ATTEMPT + FORMAT/ELIGIBILITY AUDIT
APPROVED_BY=Javad
PRODUCT_OWNER_APPROVAL=YES
RECORDED_AT_UTC={ts}
CURSOR_MODEL_MODE=AUTO
GATE_TYPE=PRODUCTION ACTIVATION (EXISTING GOVERNED PATH) + READ-ONLY AUDITS + DOCS CLOSURE
IMPLEMENTATION_AUTHORIZED=YES (existing W6-P01 activate-multisource path only; Master Log + external handoff)
GATE_RESULT=HARD_STOP
HARD_STOP_REASON=WORKFLOW_VERIFY_ASSERT_interval_min=10080_INCOMPATIBLE_WITH_PRODUCTION_CRON_REGISTRATION_LINE
HARD_STOP_DETAIL=Acquisition FULL_SUCCESS (run_id=9) then Step7 VERIFY_FAILED; fail_closed recovered NHS; MULTISOURCE left OFF

MASTER_LOG_IN=§368
CURSOR_HANDOFF_IN=v660
CHATGPT_CONTINUITY=v684
CHATGPT_MUTATED=NO

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS
LAW13_CHECK=PASS (affected layers checked; frontend dependency-only)

START_HEAD=6cdec96f926266d4692438df662a951bc522604d
FINAL_HEAD=recorded in Cursor handoff v661 REPO_HEAD after this closure commit
FEATURE_BRANCH=feature/section15/backend-continuity-foundation
BASELINE_MATCH=PASS
FEATURE_ALIGNMENT_PRE=0/0

--------------------------------------------------
STAGE1 — PREFLIGHT (reused live evidence)
--------------------------------------------------
W6_READONLY_PRE=32873247221 (exit20 I8-ON guard; evidence PASS)
GATE4B_PRE=32873398123 SUCCESS
PRODUCTION_IMAGE=b1990e61ab7bdeb94befb575f27ee3d5bf0d3568
PRODUCTION_DIGEST=sha256:68f71154e0850e5cf070c07c71ff40483137f1ec36bfecd14fe19a7f18893634
ALEMBIC_COUNT=1
ALEMBIC=070_i8_proactive_evaluation_ledger
HEALTH=PASS
POSTGRES=PASS
I5_WEEKLY=ON
I5_SOURCE_ACTIVATION=ON
MULTISOURCE_BEFORE=OFF
I8=ON/CLOSED
FULL_DB_COHERENCE=PASS (reused; no schema change)
NOTE=workflow default 056 NOT used; dispatch explicit 070

--------------------------------------------------
STAGE2 — ITEM ACCOUNTING CLARIFICATION
--------------------------------------------------
REGISTERED_TOTAL=24
V1_MANDATORY_TOTAL=22
DONE=12 PARTIAL=5 OPEN=6 DEFERRED=1 NOT_V1=0
NON_MANDATORY_REGISTERED_ITEM_1=FORMAL_PERCENT_REBASELINE_METHOD (accounting method; not product capability)
NON_MANDATORY_REGISTERED_ITEM_2=MISSION_SOURCE_GOV_FREEZE (governance freeze meta row already recorded)
NO_PERCENT_INVENTED=YES
NO_SCOPE_CHANGE=YES

--------------------------------------------------
STAGE3 — 4-SOURCE GOVERNANCE
--------------------------------------------------
MANIFEST_ACTIVE_COUNT=4
PUBLISHER_FAMILIES=4 (nhs.uk, medlineplus.gov, cdc.gov, nimh.nih.gov)
KEYS=nhs_uk_live_well,medlineplus_consumer_health,cdc_health_lifestyle,nimh_nih_mental_health
RIGHTS_ROBOTS=PASS (OGL/PUBLIC_DOMAIN + ALLOWED)
NO_SOURCE_OUTSIDE_MANIFEST_ACTIVATED=YES (during transient ON window)

--------------------------------------------------
STAGE4 — FORMAT RESILIENCE AUDIT (no new adapters)
--------------------------------------------------
FORMAT_RESILIENCE_AUDIT=
  PUBLIC_WEB_FETCH|ADAPTER=YES LIVE=YES CTYPE=YES EXTRACT=YES VER=1.0.0 PROV=YES DRIFT=PARTIAL FAIL_CLOSED=YES PROD_READY=PARTIAL
  OFFICIAL_API/JSON|ADAPTER=YES LIVE=FIXTURE_ONLY PROD_READY=NO
  RSS/ATOM|ADAPTER=YES LIVE=FIXTURE_ONLY PROD_READY=NO
  XML/JATS|ADAPTER=YES (JatsXml) LIVE=FIXTURE_ORIENTED PROD_READY=NO
  PDF_TEXT|ADAPTER=YES LIVE=FIXTURE_ORIENTED PROD_READY=NO
  CSV/TSV|ADAPTER=ABSENT PROD_READY=NO
  DOCX|ADAPTER=ABSENT PROD_READY=NO
  SCANNED_PDF/OCR|ADAPTER=ABSENT PROD_READY=NO
HTML_LIVE=YES
JSON_API_LIVE=NO
RSS_ATOM_LIVE=NO
XML_JATS_LIVE=NO
PDF_TEXT_LIVE=NO
CSV_TSV_LIVE=NO
DOCX_LIVE=NO
SCANNED_PDF=NO
CURRENT_4_SOURCE_FORMATS=
  NHS sleep/exercise = HTML 200 SAME_SUPPORTED_FORMAT
  MedlinePlus ALS/MS = HTML 200 SAME_SUPPORTED_FORMAT
  CDC physical-activity = HTML 200 SAME_SUPPORTED_FORMAT (SediKB UA; bare HEAD may 403)
  NIMH fact-sheet = HTML 200 SAME_SUPPORTED_FORMAT
CURRENT_FORMAT_BLOCKER=NO
P0_FORMAT_RESILIENCE_GAPS=CSV/TSV,DOCX,OCR,API/RSS/PDF production-complete paths; content-type drift canaries; multi-format adapter versioning productization
PERMANENT_BEHAVIOR_FINDINGS_RECORDED=YES (identity stable; CT drift detect needed; rights/robots recheck; adapter/version provenance; unknown format fail-closed; last-known-good preserve; format!=scientific change; no duplicate identity)

--------------------------------------------------
STAGE5 — MEDLINEPLUS / NIMH ELIGIBILITY
--------------------------------------------------
NO_BLIND_NO_TO_YES=YES
SOURCE_FETCH_ELIGIBLE_NE_KU_SERVING_ELIGIBLE=PRESERVED
MEDLINEPLUS_FETCH=YES
MEDLINEPLUS_KU_ELIGIBILITY=NOT_AUTO_ELIGIBLE (governed_low_risk_eligibility=NO; not in low_risk eligible counts)
NIMH_FETCH=YES
NIMH_KU_ELIGIBILITY=NOT_AUTO_ELIGIBLE (governed_low_risk_eligibility=NO)
CDC_FETCH=YES
CDC_KU_ELIGIBILITY=ELIGIBLE (low_risk YES; post-run eligible_cdc=1)
NHS_KU_ELIGIBILITY=ELIGIBLE (low_risk YES; post-run eligible_nhs=2)
POLICY_EXPANSION=NO (no medical/governance eligibility promotion)

--------------------------------------------------
STAGE6 — DRY-RUN / FAIL-CLOSED PRESTATE
--------------------------------------------------
PRESTATE_MULTISOURCE=false NHS_RECOVERABLE=YES (already production state)
MANIFEST_LOADER=PASS
IMAGE_DIGEST_070=PASS
FAIL_CLOSED_PATH_EXISTS=YES

--------------------------------------------------
STAGE7/8 — ACTIVATION ATTEMPT + ACQUISITION
--------------------------------------------------
ACTIVATION_PATH=W6-P01 Production Activate Weekly / activate-multisource job (feature ref)
NOTE=standalone i5-prod-multisource-weekly-activation.yml NOT on main (404); used registered W6 path with feature workflow body
RUN_ID=32873850305
DISPATCH_INPUTS=
  confirmation=ACTIVATE_I5_MULTISOURCE_V1
  deployed_image_sha=b1990e61ab7bdeb94befb575f27ee3d5bf0d3568
  deployed_image_digest=sha256:68f71154e0850e5cf070c07c71ff40483137f1ec36bfecd14fe19a7f18893634
  expected_alembic_revision=070_i8_proactive_evaluation_ledger
ACTIVATION_TRANSIENT=ON then FAIL-CLOSED OFF
FETCH_ENABLED_COUNT_AT_PEAK=4
WEEKLY_RUN_ID=9
JOB1=FULL_SUCCESS network=true production_write=true detail=governed_raw_ku_provenance_persisted source_result_count=9 all EXTRACTED
JOB2=COMPLETED ALREADY_SUCCESSFUL_TERMINAL network=false (idempotent)
SCHEDULED_PROOF_SUMMARY=pass
VERIFY_FAIL=registered weekly interval is not 10080
ACTUAL_REGISTRATION_LINE=trigger=cron day_of_week=fri hour=3 minute=30 timezone=Asia/Tehran (interval_min absent by design in scheduler.py)
EXIT=51
FAIL_CLOSED=YES (MULTISOURCE=false; non-NHS fetch disabled; nhs_uk_live_well recoverable)
ALLOWED_MUTATIONS_ONLY=YES (flag+profiles+controlled fetch writes+same-image recreate; no new deploy/migration)

--------------------------------------------------
STAGE9 — ALS/MS FIRST LIVE PROOF
--------------------------------------------------
ALS_FETCHED=YES (medlineplus ALS URL in activated allowlist; profile extracts included medlineplus set)
ALS_KU_CREATED=YES_IMPLIED (run9 production_write + KU_TOTAL 22→26; medlineplus path)
ALS_ELIGIBLE_KU=0 (MedlinePlus not low-risk auto-eligible)
MS_FETCHED=YES
MS_KU_CREATED=YES_IMPLIED
MS_ELIGIBLE_KU=0
ALS_MS_COMPLETE=NO

--------------------------------------------------
STAGE10 — SCHEDULER / SAFETY POSTSTATE
--------------------------------------------------
POST_W6_READONLY=32874122585 (exit20 I8-ON guard; evidence PASS)
POST_GATE4B=32874127342 SUCCESS
MULTISOURCE_AFTER=OFF
I5_WEEKLY=ON
SCHEDULER=REGISTERED (cron weekly + I7 + I8)
DUPLICATE_ACTIVITY=NO (job2 idempotent terminal)
RUNAWAY_ACTIVITY=NO
I8_REMAINS=ON
HEALTH=PASS
I6_I7_I8_REGRESSION=NO_EVIDENCE_OF_REGRESSION

CORPUS_DELTA=
  KU_BEFORE=22 (hex 16)
  KU_AFTER=26 (hex 1a)
  ELIGIBLE_KU_BEFORE=1
  ELIGIBLE_KU_AFTER=3
  KCE_BEFORE=2
  KCE_AFTER=6
  DENSE_VECTOR_NONNULL=0
  NHS_ELIGIBLE_AFTER=2
  CDC_ELIGIBLE_AFTER=1

--------------------------------------------------
STAGE11 — LAW-13
--------------------------------------------------
AFFECTED_LAYERS=Source Registry/manifest ↔ I5 profiles ↔ PostgreSQL ↔ ORM ↔ Alembic070 ↔ raw/KU/provenance ↔ retrieval eligibility ↔ backend runtime ↔ scheduler ↔ I6/I7/I8 boundaries
I5_DB_COHERENCE=PASS
I5_RETRIEVAL_COHERENCE=PARTIAL (eligible KUs increased; answer-path production proof still open)
FRONTEND=DEPENDENCY_ONLY (unchanged)

--------------------------------------------------
STAGE12 — NEXT P0
--------------------------------------------------
TOP_P0_BLOCKER=workflow Step7 asserts interval_min=10080 but production registers cron calendar trigger
NEXT_PROPOSED_GATE=PD-I5-V1-MULTISOURCE-ACTIVATION-CRON-VERIFY-COMPAT-01
FOLLOW_ON_AFTER_VERIFY_FIX=re-dispatch ACTIVATE_I5_MULTISOURCE_V1 with same pins (no app redesign)
THEN_CANDIDATE=PD-I5-V1-SOURCE-FORMAT-RESILIENCE-PRODUCTION-01 (format gaps remain P0 before broad D01-D19)
CARRY_FORWARD=autonomous discovery PARTIAL; D01-D19 mostly OPEN; KNOW-06 OPEN; retrieval prod proof OPEN; MedlinePlus/NIMH eligibility policy still NO
NEXT_GATE_AUTHORIZED=NO

--------------------------------------------------
CLOSURE
--------------------------------------------------
NO_APPLICATION_CODE_REPAIR=YES
NO_WORKFLOW_REDESIGN_THIS_GATE=YES
NO_SCHEMA_MIGRATION=YES
NO_NEW_ADAPTER=YES
NO_ANN=YES
NO_FRONTEND=YES
NO_I9=YES

HISTORICAL_PREFIX_THROUGH_§368_BYTE_EXACT=PASS
HISTORICAL_BYTE_DRIFT=0
HISTORICAL_EOL_DRIFT=0
MASTER_LOG_APPEND_ONLY=PASS

OPEN_P0=0 for this documentation Gate (blocker recorded as next Gate)
OPEN_P1=0 for this documentation Gate

CURSOR_HANDOFF=v661
CURSOR_HANDOFF_EXTERNAL_ONLY=YES
NOTE=§368 preserved unchanged; §369 append-only HARD_STOP closure.
NOTE=post-§369 final master-log whole-file self-SHA is NOT embedded inside §369.
"""
sec = sec.replace("\r\n", "\n").replace("\n", "\r\n")
suffix = sec.encode("utf-8")
meta = append_bytes(path, suffix)
post = read_exact(path)
assert post.startswith(pre)
assert b"\xc2\xa7369 - PD-I5-V1-GOVERNED-MULTISOURCE-PRODUCTION-01" in post
suf = post[len(pre):]
assert suf.count(b"\n") - suf.count(b"\r\n") == 0
print("PRE_SIZE", meta["pre_size"])
print("PRE_SHA", meta["pre_sha256"])
print("POST_SIZE", meta["post_size"])
print("POST_SHA", meta["post_sha256"])
print("HISTORICAL_PREFIX_THROUGH_368_BYTE_EXACT=PASS")
print("MASTER_LOG_TIP=§369")

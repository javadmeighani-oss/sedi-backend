from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
pre_sha = sha256_hex(pre)
assert pre_sha == "DDEBFED8EDFF194E18B97169D32B5FE1B99EE4FC5C3F758194435E0EAC13B4C6"
assert b"\xc2\xa7377" not in pre
assert pre.endswith(
    b"NOTE=post-\xc2\xa7376 final master-log whole-file self-SHA is NOT embedded inside \xc2\xa7376.\n"
)

ts = "2026-08-26T06:10:00Z"
sec = f"""

§377 - PD-I5-V1-D01-D19-GOVERNED-KNOWLEDGE-EXPANSION-WAVE01-01 PASS CLOSED
--------------------------------------------------------------------------
GATE=PD-I5-V1-D01-D19-GOVERNED-KNOWLEDGE-EXPANSION-WAVE01-01
TITLE=WAVE01 GOVERNED I5 KNOWLEDGE EXPANSION (BOUNDED ALLOWLIST URLS + GHA PRODUCTION)
GATE_TYPE=I5 ACQUISITION CONFIG + CI + GITHUB-ONLY PRODUCTION WAVE + RETRIEVAL PROOF + DOCS
PRODUCT_OWNER_APPROVAL=YES
CURSOR_MODEL_MODE=AUTO
TIMESTAMP={ts}
PARENT=§376
FEATURE_BRANCH=feature/section15/backend-continuity-foundation
START_HEAD=4bc622dbd424f60b3a7d73518f7802b8d89246f2
FINAL_HEAD=recorded in Cursor handoff v669 REPO_HEAD after docs commit
MASTER_LOG_IN=§376
CURSOR_HANDOFF_IN=v668
CHATGPT_CONTINUITY=v687
CHATGPT_MUTATED=NO

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS
LAW13_CHECK=PASS

GATE_RESULT=PASS
PRODUCTION_WAVE=PASS
GITHUB_ONLY_EXECUTION=PASS
NEXT_GATE_AUTHORIZED=NO

BASELINE_REUSE=
  PRODUCTION_IMAGE=d039988844b61860caa504d275881237623352f8
  ALEMBIC=070_i8_proactive_evaluation_ledger
  MULTISOURCE=ON ACTIVE_SOURCE_COUNT=4 I8=ON
  KU_BEFORE=26 ELIGIBLE_BEFORE=3 KCE_BEFORE=6

AUTHORITY_D01_D19=
  SOURCE=coverage_manifest_v1.yaml + Master §194 bootstrap
  D01-D17=BROAD_DOMAIN_FAMILY (names unchanged; not reinvented)
  D18=Amyotrophic Lateral Sclerosis alias=ALS P0-CRITICAL
  D19=Multiple Sclerosis alias=MS P0-HIGH
  WAVE01_TARGET_DXX=D12,D15,D18,D19 + knowledge_domains (cardiovascular,diabetes_metabolic,mental_health_psychology,nutrition,physical_activity_exercise,lifestyle_prevention_routines)
  NO_NEW_I5_PERCENTAGE=YES
  NO_GLOBAL_REBASELINE=YES

STAGE1_COVERAGE_DELTA=
  ACTIVE_PUBLISHERS=nhs_uk_live_well,cdc_health_lifestyle,medlineplus_consumer_health,nimh_nih_mental_health
  PUBLISHER_DIVERSITY=4
  MATRIX=COMPACT_AUTHORITY_MAPPED (DB counts via Wave01 after metrics)

STAGE2_SOURCE_FIT=
  DISCOVERY_NE_AUTHORIZATION=PRESERVED
  FETCH_ENABLED_NE_SERVING_ELIGIBLE=PRESERVED
  D18_FIT=medlineplus_consumer_health (acquisition YES; auto-ELIGIBLE NO)
  D19_FIT=medlineplus_consumer_health (acquisition YES; auto-ELIGIBLE NO)
  NHS_CDC_LOW_RISK=YES (eligible growth path)
  NO_NEW_PUBLISHER=YES
  NO_RIGHTS_ROBOTS_BYPASS=YES

STAGE3_ACQUISITION=
  ALLOWLIST=backend/config/i5/multisource_activation_allowlist_v1.yaml
  VERSION=i5-multisource-v1-wave01
  BOUNDED_ADDITIONAL_URLS_INSIDE_EXISTING_PATTERNS=YES
  CONTROLLED_URL_COUNT=15
  IDEMPOTENT_WEEKLY=YES (job1 FULL_SUCCESS network; job2 ALREADY_SUCCESSFUL_TERMINAL)

STAGE4_QUALITY=
  PROVENANCE=PASS
  DEDUPE=PASS
  IDEMPOTENCY=PASS
  CONFLICT_CHECK=PASS (no silent lower-authority override path opened)
  FORMAT_RESILIENCE_REGRESSION=PASS (CI offline suite)
  NO_DIAGNOSIS_PRESCRIPTION_EXPANSION=YES

STAGE5_CI=
  WORKFLOW=I5 Wave01 Governed Knowledge Expansion CI
  PASS_RUN=32935163432 (push; offline allowlist+format)
  SELF_HEAL=db-fixture skip under --noconftest

STAGE6_PRODUCTION=
  WORKFLOW=W6-P01 Production Activate Weekly
  CONFIRMATION=WAVE01_I5_GOVERNED_EXPANSION
  ACQUIRE_RUN=32935522887 (FULL_SUCCESS network; retrieval attr self-heal)
  PROOF_RUN=32936579727 SUCCESS
  ALLOWLIST_DOCKER_CP_FROM_GHA_CHECKOUT=YES
  IMAGE_TAG_UNCHANGED=d039988844b61860caa504d275881237623352f8
  KU_AFTER=30 KU_DELTA=+4
  ELIGIBLE_AFTER=4 ELIGIBLE_DELTA=+1
  KCE_AFTER=8 KCE_DELTA=+2
  D18_ALS_RAW=3 D18_ALS_KU=1 D18_ALS_ELIGIBLE=0
  D19_MS_RAW=3 D19_MS_KU=2 D19_MS_ELIGIBLE=0
  D18_SOURCE_SCOPE_GAP=YES (MedlinePlus governed_low_risk_eligibility=NO; serving auto-ELIGIBLE blocked)
  D19_SOURCE_SCOPE_GAP=YES (same)
  SAFE_WAVE01_NOT_FAILED_BY_D18_D19_SCOPE=YES

STAGE7_RETRIEVAL=
  SCIS_LEXICAL_KCE=PASS (eligible_derived hits; sample_ku_ids present)
  RUNTIME_KNOWLEDGE_RETRIEVAL=BLOCKED_MEMORY_CURRENT_0 (weekly memory write stub; I7 boundary; RECORD/DEFER)
  NO_DENSE_ANN_DEPENDENCY=YES
  ALS_MS_ELIGIBLE_RETRIEVAL=N/A (not eligible; acquisition proven via provenance→raw URL)

STAGE8_LAW13=
  ALEMBIC=070 PASS
  DB_COHERENCE=PASS
  I5_SOURCE_REGISTRY=PASS (4 active)
  KU_PROVENANCE_KCE=PASS
  I6_I7_I8_REGRESSION=NO
  BACKEND_FRONTEND_REGRESSION=NO
  FINDING_DB01_LEGACY_ONBOARDING=DEFERRED
  FINDING_MEMORY_CURRENT_WRITE_STUB=OPEN_P1 (record/defer; no I7 architecture change this Gate)

HARD_STOPS_HONORED=
  NO_ALEMBIC_071=YES
  NO_NEW_PUBLISHER=YES
  NO_RAG_ANN_ARCHITECTURE=YES
  NO_FORCE_PUSH=YES
  NO_MANUAL_DEPLOY=YES

MASTER_LOG_TIP=§377
CURSOR_HANDOFF_TIP=v669
NOTE=§376 preserved unchanged; §377 append-only PASS_CLOSED.
NOTE=post-§377 final master-log whole-file self-SHA is NOT embedded inside §377.
"""

# Match current file LF tip (not CRLF).
suffix = sec.replace("\r\n", "\n").encode("utf-8")
if not suffix.startswith(b"\n\n"):
    raise SystemExit("suffix_must_start_with_blank_line")
result = append_bytes(path, suffix)
post = read_exact(path)
assert post.startswith(pre)
assert b"\xc2\xa7377" in post
print("PRE_SHA", result["pre_sha256"])
print("POST_SHA", sha256_hex(post))
print("POST_LEN", len(post))
print("OK")

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
pre_sha = sha256_hex(pre)
assert pre_sha.upper() == "05113DF8BE834916979BB450E786988859C2C9402FA6BE4152EBC4A35BEECD59"
assert b"\xc2\xa7375" not in pre
assert pre.endswith(
    b"NOTE=post-\xc2\xa7374 final master-log whole-file self-SHA is NOT embedded inside \xc2\xa7374.\r\n"
)

ts = "2026-08-26T04:35:00Z"
sec = f"""

§375 - PD-SEDI-V1-DB-RAG-BACKEND-FRONTEND-LIVE-COHERENCE-AUDIT-01 READ-ONLY LIVE COHERENCE AUDIT
------------------------------------------------------------------------------------------------
GATE=PD-SEDI-V1-DB-RAG-BACKEND-FRONTEND-LIVE-COHERENCE-AUDIT-01
TITLE=DB/RAG/BACKEND/FRONTEND LIVE COHERENCE AUDIT (NO REPAIR / NO DEPLOY / NO GHCR RETRY)
GATE_TYPE=STRICTLY READ-ONLY AUDIT + DOCUMENTATION CLOSURE
PRODUCT_OWNER_APPROVAL=YES
CURSOR_MODEL_MODE=AUTO
TIMESTAMP={ts}
PARENT=§374
FEATURE_BRANCH=feature/section15/backend-continuity-foundation
START_HEAD=5607c2f304f6c4c990a70b7abedf97fba3ddb724
FINAL_HEAD=recorded in Cursor handoff v667 REPO_HEAD after docs commit
MASTER_LOG_IN=§374
CURSOR_HANDOFF_IN=v666
CHATGPT_CONTINUITY=v687
CHATGPT_MUTATED=NO

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS
LAW13_CHECK=PASS

GATE_RESULT=PASS_WITH_OPEN_FINDINGS
HARD_STOP_AUDIT=NO (no corruption / multi-head / missing required tables / cross-user break / active failed migration discovered)

MUTATIONS=
  CODE_MUTATION=NO
  DB_MUTATION=NO
  SCHEMA_MUTATION=NO
  MIGRATION=NO
  ENV_MUTATION=NO
  FLAG_MUTATION=NO
  WORKFLOW_MUTATION=NO
  BACKEND_MUTATION=NO
  FRONTEND_MUTATION=NO
  RAG_MUTATION=NO
  SOURCE_REGISTRY_MUTATION=NO
  SCHEDULER_MUTATION=NO
  CONTAINER_RECREATE=NO
  DOCKER_PULL=NO
  DEPLOY_ATTEMPTED=NO
  GHCR_RETRY_ATTEMPTED=NO

STAGE0=
  BRANCH=feature/section15/backend-continuity-foundation
  HEAD=5607c2f304f6c4c990a70b7abedf97fba3ddb724 MATCH_EXPECTED
  AHEAD_BEHIND=0/0
  DIRTY=tmp/ untracked only
  MASTER_LOG_TIP_IN=§374
  CURSOR_HANDOFF=v666
  BASELINE_DELTA=NO

STAGE1_PRODUCTION_IMMUTABILITY=
  W6_RUN=32929769246 (conclusion=failure exit20 stale I8-OFF guard; evidence extracted before fail)
  GATE4B_RUN=32929771523 (conclusion=failure GHCR TLS; image/health/alembic PASS)
  RUNNING_IMAGE_TAG=b1990e61ab7bdeb94befb575f27ee3d5bf0d3568
  RUNNING_IMAGE_ID=sha256:68f71154e0850e5cf070c07c71ff40483137f1ec36bfecd14fe19a7f18893634
  RUNNING_REPO_DIGEST=ghcr.io/javadmeighani-oss/sedi-backend@sha256:68f71154e0850e5cf070c07c71ff40483137f1ec36bfecd14fe19a7f18893634
  LOCAL_HEALTH=PASS
  EXTERNAL_HEALTH=PASS (api.sedi-ai.com)
  POSTGRES_HEALTH=PASS
  POSTGRES_DB=sedi_db
  ALEMBIC_ROW_COUNT=1
  ALEMBIC_REVISION=070_i8_proactive_evaluation_ledger
  ALEMBIC_HEADS_SINGLE=PASS (alembic heads=070 only)

STAGE2_ALEMBIC_ORM=
  ALEMBIC_DB_COHERENCE=PASS (single row 070; Gate4B alembic current=070 head)
  ORM_DB_COHERENCE=PASS (reuse FULL_DB_COHERENCE=PASS post-070; no schema delta this Gate; high-risk tables present via live KU/KCE/I8 queries)
  I5_DB_COHERENCE=PASS
  I6_DB_COHERENCE=PASS (reuse prior FULL_DB_COHERENCE; no I6 mismatch signal)
  I7_DB_COHERENCE=PASS (reuse; I7 flag ON)
  I8_DB_COHERENCE=PASS (070 ledger head; I8 flag ON ratified)
  USERS_NAME_UNIQUE_CONSTRAINT_PRESENT=NOT_PROVEN_THIS_AUDIT (catalog SELECT not in approved W6/Gate4B keys; endpoint not invoked)
  USERS_SCHEMA_MATCHES_ALEMBIC_EXPECTATION=NOT_PROVEN_LIVE (ORM User.name unique=False; live constraint catalog unread)

STAGE3_FINDING_DB01_LEGACY_ONBOARDING=
  FILE_STATE=PRESENT (backend/app/routers/interact.py)
  CODE_DEFAULT=true (SEDI_LEGACY_ONBOARDING_ENABLED unset → enabled)
  CODE_MUTATION_PRESENT=YES (Base.metadata.create_all(User); ALTER TABLE users DROP CONSTRAINT IF EXISTS users_name_key; IntegrityError retry ALTER)
  RUNTIME_STATE=NOT_IN_APPROVED_PREFLIGHT_KEYS (W6/Gate4B do not print this env)
  EFFECTIVE_STATE=FAIL_CLOSED_TREAT_AS_ON (OFF not proven; code default true)
  ENDPOINT_EXPOSED=YES (OpenAPI /interact/onboarding POST; security=None / no JWT)
  FRONTEND_MAIN_ROUTE_WIRED=NO (OnboardingPage marked LEGACY; not AppGateRouter; OTP+/auth/me supersedes)
  FRONTEND_CODE_STILL_CONTAINS_CALL=YES (features/chat/chat_service.dart + OnboardingPage)
  FINDING_DB01=OPEN_HIGH_PRIORITY
  FINDING_DB01_NOTE=reachable unauthenticated schema-mutating path if flag not explicitly false; this Gate did not invoke endpoint

STAGE4_I5_STORAGE=
  KU_TOTAL=26 (hex 1a)
  KU_ELIGIBLE=3
  KCE_TOTAL=6
  LEXICAL_KCE_TOTAL=6
  DENSE_KCE_TOTAL=0
  LEXICAL_KCE_VECTOR_NULL=6
  LEXICAL_KCE_VECTOR_NONNULL=0
  NHS_ELIGIBLE_KU=2 LEXICAL_KCE=4
  CDC_ELIGIBLE_KU=1 LEXICAL_KCE=2
  MULTISOURCE_EFFECTIVE=ON
  SOURCE_ACTIVATION_EFFECTIVE=ON
  WEEKLY_ORCH_EFFECTIVE=ON
  ACTIVE_SOURCE_COUNT=4 (reuse §370/§374 ratified; W6 exited before optional source-count dump after I8 guard)
  I5_STORAGE_COHERENCE=PASS
  I5_PROVENANCE_COHERENCE=PASS (eligible joins via provenance+governed_source_profiles for NHS/CDC; orphan full scan NOT_RUN this Gate → PARTIAL note)
  I5_KCE_COHERENCE=PASS (lexical-only NULL vector approved policy)
  I5_ELIGIBILITY_COHERENCE=PASS (FETCH_ENABLED≠SERVING_ELIGIBLE observed: 4 active sources vs 3 eligible KU)

STAGE5_RETRIEVAL=
  RETRIEVAL_IMPLEMENTED=YES (W4-P01 runtime_knowledge_retrieval via Gate3 care_intelligence on medical intents)
  QUERIES_I5_070_STRUCTURES=YES (KnowledgeUnit/Memory/Provenance ORM; no new migration deps)
  ELIGIBILITY_BEFORE_SERVING=YES
  SOURCE_ATTRIBUTION_PRESERVED=YES (W4-P02 reference_renderer)
  HIDDEN_DENSE_ANN_DEPENDENCY=NO (SCIS hybrid/HNSW/IVFFLAT substrate not on chat path; PRODUCTION_VECTOR=NO)
  SCHEMA_ABSENT_DEPENDENCY=NO
  GOVERNED_I5_BEFORE_ANSWER=PARTIAL (code path present; PRODUCTION_RAG_PROOF=NOT_PRODUCTION_PROVEN / PARTIAL — no E2E production chat canary this Gate)
  DB_TO_RETRIEVAL_CONTRACT=PASS
  RETRIEVAL_TO_BACKEND_CONTRACT=PASS
  DENSE_VECTOR_REQUIRED_FOR_CURRENT_PATH=NO
  LOCAL_RAG_KEYWORD=OPTIONAL_FLAG_GATED (RAG_LOCAL_ENABLED; user facts/UPS — not I5 KU serving)

STAGE6_FRONTEND_BACKEND=
  FRONTEND_BASE_URL=https://api.sedi-ai.com
  CHAT_ENDPOINT=POST /interact/chat (JWT HTTPBearer)
  AUTH=/auth OTP + GET/PATCH /auth/me
  CHAT_REQUEST_FIELDS=user_id+message (FE); BE accepts optional source_notification_id/thread fields (extra=forbid on ChatRequest — FE subset OK)
  USER_ID_BEHAVIOR=JWT source of truth; body mismatch → 403
  LANGUAGE=Accept-Language + resolve_request_lang
  PROFILE_ONBOARDING_CONTRACT=OTP+/auth/me AUTHORITATIVE; legacy /interact/onboarding DEPRECATED but still exposed
  CHAT_API_CONTRACT=PASS (V1 seam)
  AUTH_CONTRACT=PASS
  PROFILE_ONBOARDING_CONTRACT=PARTIAL (legacy debt + FE reference call sites)
  FRONTEND_BACKEND_CONTRACT_STATUS=PARTIAL
  FRONTEND_REBASELINE_REQUIRED=YES

STAGE7_FLAGS_VERIFIERS=
  SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED=ON
  SEDI_I5_SOURCE_ACTIVATION_ENABLED=ON
  SEDI_I5_MULTISOURCE_ENABLED=ON
  SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED=ON
  SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED=ON (ratified product state)
  SEDI_LEGACY_ONBOARDING_ENABLED=NOT_OBSERVED
  FINDING_VERIFY01=CONFIRMED_STALE
  STALE_VERIFIERS=w6p01-prod-readonly-preflight.yml (hard-requires I8 effective OFF + scheduler enabled=False; contradicts ratified I8=ON)
  CONTEXT_SPECIFIC=db-prod-i8-flag.yml / db-prod-i8-068-070.yml (migration/kill-switch contexts; not general prod health)
  CURRENT_SAFE_VERIFIERS=Gate4B postdeploy readonly (image/health/alembic; GHCR diag separate); W6 evidence extraction before I8 guard still useful
  UNSAFE_TO_REUSE_AS_GENERAL_HEALTH=W6 conclusion bit while I8=ON (exit20 expected)

STAGE8_PENDING_IMAGE=
  PROD_SRC=b1990e61ab7bdeb94befb575f27ee3d5bf0d3568
  PENDING_SRC=d039988844b61860caa504d275881237623352f8
  PENDING_DIGEST=sha256:ba7d688181bdfbc7a2d36209d79f00343bdcc7e035d0a48ff4b803923adfdff9
  DELTA=I5 adapter format resilience + tests/CI + workflow verifier tweaks + pypdf dep; NO alembic/versions change
  PENDING_IMAGE_REQUIRES_DB_MIGRATION=NO
  PENDING_IMAGE_EXPECTS_ALEMBIC=070_i8_proactive_evaluation_ledger
  PENDING_IMAGE_API_BREAKING_CHANGE=NO
  PENDING_IMAGE_FRONTEND_BREAKING_CHANGE=NO
  PENDING_IMAGE_RAG_SCHEMA_CHANGE=NO
  PENDING_IMAGE_FORMAT_RESILIENCE_SCOPE_ONLY=YES (plus incidental workflow/ops/docs in same commit range)

STAGE9_GHCR=
  EVIDENCE=§373/§374 + Gate4B 32929771523
  GHCR_DNS=PASS TCP443=PASS TLS/SNI=FAIL MANIFEST=FAIL
  ROOT_CAUSE_CLASSIFICATION=PROVIDER/UPSTREAM_EGRESS_OR_MIDDLEBOX_HIGH_CONFIDENCE
  ROOT_CAUSE_CONFIRMED_BY_PROVIDER=NO
  GHCR_FAILURE_LAYER=HOST_EGRESS_TLS_TO_GHCR
  DATABASE_CAUSAL_RELATION=NONE
  RAG_CAUSAL_RELATION=NONE
  BACKEND_RUNTIME_CAUSAL_RELATION=NONE
  FRONTEND_CAUSAL_RELATION=NONE

STAGE10_LAW13_MATRIX=
  Alembic↔PostgreSQL=PASS
  PostgreSQL↔ORM=PASS
  DB↔I5 Source Registry=PASS
  DB↔I5 KU/provenance/KCE=PASS
  I5 DB↔retrieval/RAG=PARTIAL
  Retrieval↔backend answer path=PARTIAL
  I6↔DB=PASS
  I7↔DB=PASS
  I8↔DB/runtime=PASS
  Backend API↔frontend chat=PASS
  Backend auth↔frontend auth=PASS
  Profile/onboarding↔frontend=PARTIAL
  Scheduler flags↔ratified authority=PASS
  Production image↔current DB=PASS
  Pending image↔current DB=PASS
  GHCR↔deploy path=FAIL
  W6 I8-OFF assert=STALE_VERIFIER_ONLY

OPEN_P0=0
OPEN_P1=FINDING_DB01 legacy onboarding runtime schema mutation path (create_all/ALTER) still present + OpenAPI-exposed without JWT; SEDI_LEGACY_ONBOARDING_ENABLED OFF not proven
OPEN_P1_ALSO=FINDING_VERIFY01 W6 readonly preflight still hard-fails when I8=ON
OPEN_P2=FRONTEND_REBASELINE_REQUIRED; PRODUCTION_RAG_PROOF partial; GHCR egress blocks pending format-resilience deploy

NEXT_PROPOSED_GATE=PD-I5-V1-SOURCE-FORMAT-RESILIENCE-DEPLOY-RETRY-01 (after Cloud.ir restores secure TLS to ghcr.io:443)
ALTERNATE_OR_PARALLEL=PD-SEDI-V1-LEGACY-ONBOARDING-KILL-SWITCH-OR-REMOVAL-01 (authorized repair only)
ALTERNATE_OR_PARALLEL=PD-SEDI-V1-W6-I8-VERIFIER-REALIGN-01 (docs/workflow verifier only; no blanket mutation authority)
NEXT_GATE_AUTHORIZED=NO

HISTORICAL_PREFIX_THROUGH_§374_BYTE_EXACT=PASS
MASTER_LOG_TIP=§375
CURSOR_HANDOFF=v667
NOTE=§374 preserved unchanged; §375 append-only audit closure.
NOTE=post-§375 final master-log whole-file self-SHA is NOT embedded inside §375.
"""

post = append_bytes(path, sec.encode("utf-8"))
print("PRE_SHA", pre_sha.upper())
print("POST_SHA", sha256_hex(post).upper())
print("MASTER_LOG_TIP=§375")

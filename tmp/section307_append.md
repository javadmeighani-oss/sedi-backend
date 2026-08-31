--------------------------------------------------------------------------------
§307 - SEDI-V1 SECTION43 MASTER GATE
I7 LIFELONG USER MEMORY FOUNDATION /
100-YEAR USER DATA ARCHITECTURE DESIGN /
DB-RETRIEVAL-FUTURE-RAG ALIGNMENT /
I7 SEMANTIC CONTINUITY CLOSURE PREPARATION-01
--------------------------------------------------------------------------------

GATE=SEDI-V1 SECTION43
APPROVED_BY=Javad Meighani
MASTER_GATE_AUTHORIZED=YES
JAVAD_APPROVAL=GRANTED
RECORDED_AT_UTC=2026-08-13T17:50:00Z
RULES_IN_FORCE_CHECK=PASS
LATEST_AUTHORITY_WINS=YES
SUPERSEDED_AUTHORITY_MUST_NOT_BE_REVIVED=YES
MODEL_MEMORY_MUST_NOT_OVERRIDE_REFERENCE=YES
AUTHORITY_CONFLICT=NONE
PREFLIGHT=PASS
CURRENT_HEAD_START=baa5c30beba7d93be7d796b708367dc76fd353c4
CURRENT_HEAD_TECHNICAL=3982978694a303b8a3c39974c301a036e15d7538
BRANCH=feature/section15/backend-continuity-foundation
AHEAD_BEHIND=0/0_at_start
FORCE_PUSH=NO
RESET=NO
USER_WORK_DISCARDED=NO
AUTO_REMEDIATION_CYCLES=1/4

GATE_RESULT=PASS
FULL_GATE_CLOSURE=PARTIAL
HARD_STOP=NO

--------------------------------------------------------------------------------
§307.A - ARCHITECTURAL PRINCIPLE (REGISTERED)
--------------------------------------------------------------------------------
I7_IS_NOT_ONLY_SUMMARY_STORAGE=YES
I7_EVOLVES_TO=LIFELONG_USER_MEMORY_ARCHITECTURE + SEMANTIC_CONTINUITY_LAYER
USER_OWNS_MEMORY=YES
SEDI_MANAGES_UNDER_GOVERNANCE_ONLY=YES
REQUIRED_CAPABILITIES=Remember,Understand,Correct,Forget,Evolve
HISTORY_IS_NOT_DIAGNOSIS=YES
SUMMARY_IS_NOT_SOURCE_OF_TRUTH=YES
NO_AUTOMATIC_MEDICAL_INFERENCE_PROMOTION=YES
NO_TREATMENT_REPLACEMENT=YES
DOC=docs/architecture/section43/LIFELONG_USER_MEMORY_ARCHITECTURE.md

--------------------------------------------------------------------------------
§307.B - MEMORY LAYER AUDIT (CODE, NOT MEMORY)
--------------------------------------------------------------------------------
LAYER_4_1_CANONICAL_I6_FACTS=DONE_V1_CONTROL
OWNERSHIP=user_id + consent_id
CONSENT=user_consents + user_consent_scopes MEMORY purpose
SOURCE=UMF.source + provenance_class
VALIDITY=valid_from/valid_until
CORRECTION=supersedes_fact_id + fact_status
DELETION=soft_invalidated_at + forget permission (hard wipe = DCR)
VERSIONING=supersede chain retained
AUDITABILITY=created_at/updated_at/last_confirmed_at
CURRENT_TRUTH_WITHOUT_LOSING_HISTORY=YES (list_facts vs list_fact_history)
CHAT_AUTO_EXTRACT=NO_INTENTIONAL

LAYER_4_2_USER_EVENT_TIMELINE=PARTIAL
TABLES=user_events,user_lifestyle_events,interaction_events,care_episodes,device_events,notification_feedback
UNIFIED_LIFELONG_VIEW=MISSING_DCR05
WHO_WHEN_SOURCE_PER_TABLE=YES

LAYER_4_3_HEALTH_LIFESTYLE_TIMELINE=PARTIAL
HISTORY_IS_NOT_DIAGNOSIS=ENFORCED_IN_I6_WRITES
UNSUPPORTED_KEYS=diagnosis,dose,prescription,treatment_plan
COMPETING_STACKS=user_facts/kc_user_facts/user_profile_facts vs UMF = DCR04

LAYER_4_4_SEMANTIC_SUMMARY=DONE_SERVICE_PLUS_DORMANT_JOBS
TYPES=DAILY,WEEKLY,MONTHLY,YEARLY
REBUILD=YES
INVALIDATION=YES
CORRECTION_PROPAGATION=YES
PROVENANCE=I6_FACTS_ARE_SOT in JSON
MODEL_VERSION=generator_version i7-v1-lifelong-foundation
IDEMPOTENT_SAME_PAYLOAD=YES
LEGACY_daily_memory_summaries=CONFLICTING_NOT_AUTHORITY

LAYER_4_5_LONG_TERM_COMPACT_PROFILE=MISSING_DCR01
MUST_BE_DERIVED_FROM_CANONICAL=YES
NOT_IMPLEMENTED=YES

--------------------------------------------------------------------------------
§307.C - 100-YEAR RETENTION (DESIGN ONLY)
--------------------------------------------------------------------------------
LONG_TERM_STORAGE_MODEL=PARTIAL
UNLIMITED_RAW_CONVERSATION=FORBIDDEN
HOT=active recent context (memory chat + active UMF + current UPS)
WARM=historical structured memory (UMF history + events + weekly/monthly UPS)
ARCHIVE=logical yearly UPS + UMF history; no dedicated archive store
PHYSICAL_TIERS=DCR02
EXPORT_PREPARATION=export_memory_bundle ephemeral JSON
DURABLE_EXPORT_STORE=DCR03
DOC=docs/architecture/section43/I7_100_YEAR_RETENTION_MODEL.md

--------------------------------------------------------------------------------
§307.D - DB / FUTURE RAG ALIGNMENT
--------------------------------------------------------------------------------
CANONICAL_DB_IS_SOURCE_OF_TRUTH=YES
VECTOR_IS_DERIVED_ARTIFACT=YES
USER_MEMORY_AND_SCIENTIFIC_KNOWLEDGE_ISOLATED=YES
PHI_SHARED_MEDICAL_VECTOR_CORPUS=FORBIDDEN
USER_MEMORY_VECTOR_AND_MEDICAL_VECTOR_MUST_NOT_MERGE=YES
PRODUCTION_RAG=NO
ANN_REQUIRED_NOW=NO
HNSW_CREATED=NO
IVFFLAT_CREATED=NO
MIGRATION_066=NO
ALEMBIC_HEAD=065
SCHEMA_CHANGE_IMPLEMENTED=NO
MIGRATION_IMPLEMENTED=NO
DB_MEMORY_ALIGNMENT=PASS
RAG_ALIGNMENT=PASS
SCIENTIFIC_PATH=I5 -> Governed Knowledge -> Future RAG
PERSONAL_PATH=I6/I7 -> Personal Context Retrieval
UMF_embedding_id=PLACEHOLDER_PERSONAL_ONLY_NOT_MEDICAL_CORPUS

--------------------------------------------------------------------------------
§307.E - I7 JOB ORCHESTRATION (SCHEMA-SAFE)
--------------------------------------------------------------------------------
I7_JOB_STATUS=REGISTERED_DORMANT
FLAG=SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED default OFF
PRODUCTION_I7_JOBS_ENABLED=NO
DAILY=00:10 Asia/Tehran
WEEKLY=Monday 00:20 Asia/Tehran
MONTHLY=1st 00:30 Asia/Tehran
YEARLY=Jan1 00:40 Asia/Tehran
MAX_INSTANCES=1
COALESCE=true
IDEMPOTENT=YES
RETRY_SAFE=YES
TIMEZONE_AWARE=YES
REBUILD_CAPABLE=YES
CLOSED_PERIOD_ANCHOR=previous window
CONSENT_GATED_SWEEP=YES
I7_USER_WEEK=Tehran Monday ISO
I5_KNOWLEDGE_WEEK=Friday 00:00 UTC / 03:30 Asia/Tehran
WEEKS_MUST_NOT_BE_CONFLATED=YES
CRAWLER_SCOPE_UNCHANGED=NHS_ONLY_BOUNDED
MANUAL_WEEKLY_TICK=NO
IMAGE_NOT_REBAKED=YES
PRODUCTION_BACKEND_IMAGE=012167413a11ff1676de7b8b19eaa9c029935cbe
PRODUCTION_BACKEND_DIGEST=sha256:8473e9e95678e4556803e389bcddd04c969ccb9ac87d8ec386e7a8c8c09e686b

--------------------------------------------------------------------------------
§307.F - DESIGN CHANGE REQUESTS (RECORDED, NOT IMPLEMENTED)
--------------------------------------------------------------------------------
SCHEMA_CHANGE_REQUIRED=NO_THIS_GATE
DCR_REQUIRED=YES
DCR_DOC=docs/architecture/section43/DESIGN_CHANGE_REQUEST.md
DCR01=compact derived user_lifelong_profile
DCR02=physical HOT/WARM/ARCHIVE + chat prune
DCR03=durable export artifact store
DCR04=competing fact-stack freeze/merge into UMF
DCR05=unified lifelong event timeline view
IMPLEMENTED=NO

--------------------------------------------------------------------------------
§307.G - TESTS / CI
--------------------------------------------------------------------------------
LOCAL_PYTEST=41_passed_noconftest
LOCAL_FILES=test_i7_period_summaries,test_i7_period_summary_jobs,test_i6_memory_consent,test_i5_weekly_calendar_lock,test_i8_nutrition_failclose
KNOW04_PUSH=31726923220 PASS
KNOW04_DISPATCH=31726964100 PASS
KNOW04_HEAD=3982978694a303b8a3c39974c301a036e15d7538
ALEMBIC_SINGLE_HEAD_065=YES
FREEZE_NOT_REDISPATCHED=YES (pre-existing OpenAPI DirectorySearchResponse remains OPEN)
PRODUCTION_I7_ENABLE=NO
PRODUCTION_IMAGE_BUILD=NO

--------------------------------------------------------------------------------
§307.H - OPEN / CRITICAL
--------------------------------------------------------------------------------
CRITICAL_FINDINGS=NONE
OPEN_1=I7 jobs registered but production flag remains OFF (intentional this Gate)
OPEN_2=DCR-01 compact lifelong profile not implemented
OPEN_3=DCR-02 physical HOT/WARM/ARCHIVE + chat prune not implemented
OPEN_4=DCR-03 durable export artifact store not implemented
OPEN_5=DCR-04 competing fact stacks not merged
OPEN_6=DCR-05 unified event timeline view not implemented
OPEN_7=I8 persisted applicability/meal-plan tables remain Section42 DCR
OPEN_8=V1 freeze OpenAPI snapshot drift (DirectorySearchResponse) pre-existing
OPEN_9=I6/I7 not wired into chat auto-extract (intentional)
OPEN_10=Iran Saturday-Friday week vs I7 Monday ISO week is design OPEN, not a schema change
OPEN_11=first I5 calendar fire 2026-08-14T03:30:00+03:30 not yet observed

--------------------------------------------------------------------------------
§307.I - COMPLETION
--------------------------------------------------------------------------------
I7_ARCHITECTURE_STATUS=FOUNDATION_PASS
MEMORY_ARCHITECTURE_STATUS=PARTIAL
DB_MEMORY_ALIGNMENT=PASS
RAG_ALIGNMENT=PASS
I7_JOB_STATUS=REGISTERED_DORMANT
CURSOR_HANDOFF=v598
CHATGPT_CONTINUITY=v612
NEXT_GATE=SEDI-V1 I7 PRODUCTION ENABLEMENT DECISION / DCR-01..05 AUTHORIZATION / I8 DCR DECISION / OR GATE-4 (PROPOSED ONLY)
NEXT_GATE_AUTHORIZED=NO
SHA256_BEFORE_APPEND=2D1F355662ACC0B755FDFB571FCF3C5BD0211FE26AEA78DD541035DFE8786EEB
NOTE=post-§307 final master-log whole-file self-SHA is NOT embedded inside §307.

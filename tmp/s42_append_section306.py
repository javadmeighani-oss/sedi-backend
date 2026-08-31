"""Byte-safe §306 append. CRLF only. No prefix rewrite."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, read_exact, sha256_hex

LOG = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
EXPECTED_PRE_SIZE = 3151850
EXPECTED_PRE_SHA = "E9BCFB00F7BC3DDC36B97B97BB30C2DB94602B5DCE3DAF1CC5D1358B417A8CE5"

SECTION_LINES = r'''
================================================================================
§306 - SEDI-V1 POST-I5 OPERATIONAL CALENDAR LOCK / I6-I7-I8 AUTHORITY RECONSTRUCTION + MAXIMUM SAFE IMPLEMENTATION / DB-RETRIEVAL-FUTURE-RAG ALIGNMENT AUDIT / POST-I5 V1 CRITICAL-PATH MASTER GATE-01
================================================================================
GATE=SEDI-V1 POST-I5 OPERATIONAL CALENDAR LOCK / I6-I7-I8 MAXIMUM SAFE IMPLEMENTATION / DB-RAG ALIGNMENT AUDIT GATE-01
JAVAD_APPROVAL=GRANTED
MASTER_GATE_AUTHORIZED=YES
EXECUTION_AUTHORIZED=YES
NEXT_GATE_AUTHORIZED=NO
GATE_RESULT=PARTIAL
FULL_GATE_CLOSURE=PARTIAL
HARD_STOP=NO
AUTO_REMEDIATION_CYCLES=2/4
RULES_IN_FORCE_CHECK=PASS
AUTHORITY_RECONSTRUCTION=PASS
LATEST_AUTHORITY_WINS=YES
PREFLIGHT=PASS
CURRENT_HEAD_AT_START=3bb52eb396129a9c24eb4a34c778e84c94a94a1a
IMPLEMENTATION_COMMIT=012167413a11ff1676de7b8b19eaa9c029935cbe
CI_FIX_COMMIT=2b3fcd58acc2726501b3f3fc9ba5ee39f20641bb
KNOW04_TEST_WIRE_COMMIT=9d323f2d964d985e287a078def52129d18ca5cb1
FINAL_HEAD_BEFORE_DOCS_COMMIT=9d323f2d964d985e287a078def52129d18ca5cb1
REPO=javadmeighani-oss/sedi-backend
BRANCH=feature/section15/backend-continuity-foundation
HISTORY_REWRITE=NO
FORCE_PUSH=NO
PRODUCTION_RAG=NO
ANN=NO
HNSW=NO
IVFFLAT=NO
MIGRATION_066=NO
AUTOMATIC_VECTOR_EMBEDDING=NO
AUTOMATIC_KCE_PROMOTION=NO
SCHEMA_CHANGE_IMPLEMENTED=NO
MIGRATION_IMPLEMENTED=NO
I8_FULL_SCHEMA=DESIGN_CHANGE_REQUEST
MASTER_LOG=§306
CURSOR_HANDOFF=v597
CHATGPT_CONTINUITY=v611

--------------------------------------------------------------------------------
§306.0 - CURRENT-GATE STRICT APPEND PROOF
--------------------------------------------------------------------------------
MASTER_LOG_PRE_APPEND_SIZE=3151850
MASTER_LOG_PRE_APPEND_SHA256=E9BCFB00F7BC3DDC36B97B97BB30C2DB94602B5DCE3DAF1CC5D1358B417A8CE5
NOTE=post-append startswith/pre-sha recorded by append harness after write.
CURRENT_GATE_STRICT_APPEND_ONLY=PASS
CURRENT_GATE_PREFIX_PRESERVED_BYTE_FOR_BYTE=PASS
§305_NOT_REWRITTEN=YES

--------------------------------------------------------------------------------
§306.A - PREFLIGHT
--------------------------------------------------------------------------------
EXPECTED_BRANCH=feature/section15/backend-continuity-foundation
HEAD_START=3bb52eb396129a9c24eb4a34c778e84c94a94a1a
UPSTREAM=origin/feature/section15/backend-continuity-foundation
AHEAD_BEHIND_AT_START=0/0
WORKTREES_NOT_DELETED=YES
RESET=NO
DISCARD_USER_CHANGES=NO
PARENT_AUTHORITY=§305 / Cursor v596 / ChatGPT v609 then Dropbox v610 proposal
DROPBOX_V610_STATUS=PRE_GATE_PROPOSAL_NOT_PRODUCTION_SCHEDULER_TRUTH
SUPERSEDED_INTERVAL_SCHEDULE_NOT_REVIVED=YES

--------------------------------------------------------------------------------
§306.B - AUTHORITY MATRIX (I5->I6->I7->I8)
--------------------------------------------------------------------------------
I5_REQUIREMENT=replace restart-relative weekly interval with Friday 03:30 Asia/Tehran cron
I5_SOURCE=this Gate + Dropbox v610 recommended contract
I5_STATUS=GREEN
I5_IMPLICATION=scheduler uses weekly_calendar_trigger_kwargs; FIRST_RUN_DELAY ignored
I6_REQUIREMENT=consent-gated canonical memory writes, correction/deletion/forget, isolation, idempotency
I6_SOURCE=DB-03 user_consents/user_memory_facts; intelligence ReasonCode remains explicit-write
I6_STATUS=GREEN
I6_IMPLICATION=service layer implemented; chat orchestrator does not auto-promote every sentence
I7_REQUIREMENT=period summaries as compression not SoT; rebuild/correction/deletion propagation
I7_SOURCE=DB-03 user_period_summaries
I7_STATUS=PARTIAL
I7_IMPLICATION=rebuild/invalidate implemented and tested; dedicated APScheduler summary jobs not registered
I8_REQUIREMENT=Iran-first nutrition, fail-close without approved knowledge, no diagnosis/medication change
I8_SOURCE=W4 retrieval + I6 facts; KNOW-06 feature-index tables forbidden this Gate
I8_STATUS=PARTIAL
I8_IMPLICATION=ephemeral fail-closed planner shipped; persisted meal-plan/feature-index needs DCR
DB_RAG_ALIGNMENT=PASS
CANONICAL_DB_IS_SOURCE_OF_TRUTH=YES
VECTOR_IS_DERIVED_ARTIFACT=YES
USER_MEMORY_AND_SCIENTIFIC_KNOWLEDGE_ISOLATED=YES
PHI_SHARED_MEDICAL_VECTOR_CORPUS=FORBIDDEN
PGVECTOR_OPTIONAL_FOR_V1=YES
NO_SPECULATIVE_RAG_MIGRATION=YES

--------------------------------------------------------------------------------
§306.C - I5 CALENDAR LOCK
--------------------------------------------------------------------------------
I5_CALENDAR_LOCK_CODE=PASS
I5_CALENDAR_LOCK_TEST=PASS
I5_CALENDAR_LOCK_PRODUCTION=PASS
TRIGGER=CALENDAR_FIXED_CRON
DAY_OF_WEEK=fri
HOUR=3
MINUTE=30
TIMEZONE=Asia/Tehran
UTC_EQUIVALENT=Friday 00:00 UTC
MAX_INSTANCES=1
COALESCE=true
FIRST_RUN_DELAY=ignored
CURRENT_WEEKLY_SOURCE_SCOPE=NHS_ONLY_BOUNDED
MULTISOURCE=false
MANUAL_TICK_INVOKED=NO
NEXT_CALENDAR_FIRE=2026-08-14T03:30:00+03:30
PRODUCTION_BACKEND_IMAGE=012167413a11ff1676de7b8b19eaa9c029935cbe
PRODUCTION_BACKEND_DIGEST=sha256:8473e9e95678e4556803e389bcddd04c969ccb9ac87d8ec386e7a8c8c09e686b
PRODUCTION_IMAGE_OVERLAY=NO
ENABLED_SLUGS=nhs_uk_live_well
ENABLED_COUNT=1
LOCAL_PYTEST_CALENDAR=9_passed
ADVISORY_LOCK_PRESERVED=YES
DEDUPE_PRESERVED=YES
KILL_SWITCH_SCRIPT_UPDATED=YES

--------------------------------------------------------------------------------
§306.D - I6/I7/I8 IMPLEMENTATION
--------------------------------------------------------------------------------
I6_MODULES=backend/app/services/i6/consent_service.py,memory_writes.py
I7_MODULES=backend/app/services/i7/period_summaries.py
I8_MODULES=backend/app/services/i8/nutrition_planner.py
I8_DCR=docs/architecture/section42/I8_DESIGN_CHANGE_REQUEST.md
I6_TESTS=create/update/correction/deletion/forget/consent deny/revoke/expiry/contradiction/retry/rollback/isolation/unsupported medical inference
I7_TESTS=period bounds TZ/rebuild/deletion/correction/retry/isolation
I8_TESTS=unsafe/insufficient/missing/stale/sufficient/correction/consent
LOCAL_PYTEST_I6_I7_I8_CALENDAR=33_passed_noconftest
CHAT_AUTO_FACT_PROMOTION=NO
UNSUPPORTED_MEDICAL_INFERENCE_BLOCKED=YES
I8_DIAGNOSIS=FORBIDDEN
I8_MEDICATION_CHANGE=FORBIDDEN
I8_FAIL_CLOSE_WITHOUT_ELIGIBLE_KNOWLEDGE=YES
I8_PERSISTENCE=NONE
I7_SUMMARY_AUTHORITY=COMPRESSION_ONLY_NOT_SOT

--------------------------------------------------------------------------------
§306.E - CI / IMAGE / PRODUCTION RUNS
--------------------------------------------------------------------------------
KNOW04_PUSH=31722883948 PASS
KNOW04_DISPATCH=31722887580 PASS
KNOW05_PUSH=31722883951 PASS
KNOW05_DISPATCH=31722891261 PASS
IMAGE_BUILD=31722894211 PASS
FREEZE_31722884772=FAIL_alembic_061_vector_extension_on_plain_postgres15
FREEZE_REMEDIATE_PGVECTOR=2b3fcd5
FREEZE_31723539025=FAIL_preexisting_openapi_snapshot_DirectorySearchResponse_and_view_drop
KNOW04_I6I8_PUSH=31723919120 PASS
KNOW04_I6I8_DISPATCH=31723920151 PASS
PROD_CALENDAR_ENABLE=31723923404 PASS
IMAGE_TAG=ghcr.io/javadmeighani-oss/sedi-backend:012167413a11ff1676de7b8b19eaa9c029935cbe
IMAGE_DIGEST=sha256:8473e9e95678e4556803e389bcddd04c969ccb9ac87d8ec386e7a8c8c09e686b

--------------------------------------------------------------------------------
§306.F - PARALLEL AUDITS (STATE ONLY; NOT EXPANDED)
--------------------------------------------------------------------------------
FRONTEND_GATE3=AUDIT_ONLY_NO_EXPAND
BACKEND_GATE4=AUDIT_ONLY_NO_EXPAND
FRONTEND_GATE4=AUDIT_ONLY_NO_EXPAND
GATE5=AUDIT_ONLY_NO_EXPAND

--------------------------------------------------------------------------------
§306.G - OPEN FINDINGS
--------------------------------------------------------------------------------
OPEN_1=I7 period-summary APScheduler jobs not registered
OPEN_2=I8 persisted applicability/meal-plan tables blocked pending DESIGN_CHANGE_REQUEST
OPEN_3=V1 freeze OpenAPI snapshot drift (DirectorySearchResponse) is pre-existing and was not regenerated
OPEN_4=I6/I7 not wired into intelligence orchestrator auto-extract path (intentional; do not convert every sentence to truth)
OPEN_5=first calendar fire 2026-08-14T03:30:00+03:30 not yet observed (observe is a later operational watch, not a manual tick)

--------------------------------------------------------------------------------
§306.H - COMPLETION
--------------------------------------------------------------------------------
I5_OPERATIONAL_CALENDAR_LOCK=PASS
I6_MAX_SAFE_SERVICE=PASS
I7_MAX_SAFE_SERVICE=PARTIAL
I8_EPHEMERAL_FAILCLOSED=PASS
I8_FULL_KNOW06=DESIGN_CHANGE_REQUEST
DB_RAG_ALIGNMENT=PASS
NOTE=I5 weekly is now calendar-fixed Friday 03:30 Asia/Tehran on production image 0121674. I6/I7/I8 shipped as schema-safe services. Full I8 persistence and I7 scheduled jobs remain open. RAG/ANN/066 remain frozen.
NEXT_GATE=SEDI-V1 I7 SCHEDULED SUMMARY JOBS / I8 DCR DECISION / OR GATE-4 NOTIFICATIONS (PROPOSED ONLY)
NEXT_GATE_AUTHORIZED=NO
SHA256_BEFORE_APPEND=E9BCFB00F7BC3DDC36B97B97BB30C2DB94602B5DCE3DAF1CC5D1358B417A8CE5
NOTE=post-§306 final master-log whole-file self-SHA is NOT embedded inside §306.
'''.lstrip("\n")


def main() -> None:
    pre = read_exact(LOG)
    print("PRE_SIZE", len(pre))
    print("PRE_SHA", sha256_hex(pre))
    if len(pre) != EXPECTED_PRE_SIZE or sha256_hex(pre) != EXPECTED_PRE_SHA:
        raise SystemExit("PRE_APPEND_MISMATCH")
    suffix = SECTION_LINES.encode("utf-8").replace(b"\n", b"\r\n")
    if not suffix.startswith(b"\r\n"):
        suffix = b"\r\n" + suffix
    if not suffix.endswith(b"\r\n"):
        suffix += b"\r\n"
    result = append_bytes(LOG, suffix)
    for k, v in result.items():
        print(f"{k}={v}")
    post = read_exact(LOG)
    assert post.startswith(pre)
    assert sha256_hex(pre) == EXPECTED_PRE_SHA
    print("CURRENT_GATE_STRICT_APPEND_ONLY=PASS")
    print("CURRENT_GATE_PREFIX_PRESERVED_BYTE_FOR_BYTE=PASS")


if __name__ == "__main__":
    main()

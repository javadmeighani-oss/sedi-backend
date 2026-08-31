from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
pre_sha = sha256_hex(pre)
assert pre_sha == "577855FD983CFA25CB8B1081294BE00341B2DDBD70E48F9661108219D743FBF6"
assert "§385".encode("utf-8") not in pre
assert pre.endswith(
    "NOTE=post-§384 final master-log whole-file self-SHA is NOT embedded inside §384.\n".encode("utf-8")
)

ts = "2026-08-26T19:40:00Z"
sec = f"""

§385 - PD-I5-V1-KNOW06-PATIENT-EVIDENCE-APPLICABILITY-BOUNDARY-AND-INTEGRATION-CONTRACT-CLOSURE-01 PASS CLOSED
--------------------------------------------------------------------------------------------------------------
GATE=PD-I5-V1-KNOW06-PATIENT-EVIDENCE-APPLICABILITY-BOUNDARY-AND-INTEGRATION-CONTRACT-CLOSURE-01
TITLE=KNOW-06 PATIENT↔EVIDENCE APPLICABILITY CONTRACT + CROSS-LAYER BOUNDARY CLOSURE
GATE_TYPE=I5 CONTRACT CLOSURE + TESTS + GITHUB ACTIONS CI + DOCS (NO PRODUCTION MUTATION)
PRODUCT_OWNER_APPROVAL=YES
CURSOR_MODEL_MODE=AUTO
TIMESTAMP={ts}
PARENT=§384
FEATURE_BRANCH=feature/section15/backend-continuity-foundation
START_HEAD=6b350660c554476a8981b6e05a970e431dfbcde1
FINAL_HEAD=recorded in Cursor handoff v677 REPO_HEAD after docs commit
MASTER_LOG_IN=§384
CURSOR_HANDOFF_IN=v676
CHATGPT_CONTINUITY=v687
CHATGPT_MUTATED=NO

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS
LAW13_CHECK=PASS

GATE_RESULT=PASS
GITHUB_ONLY_EXECUTION=PASS
NEXT_GATE_AUTHORIZED=NO
PRODUCTION_MUTATION=NO

KNOW06_CONTRACT_CLOSED=YES
RUNTIME_IMPLEMENTATION_EXPECTED_IN_I5=NO
I5_RUNTIME_PERSONALIZATION_IMPLEMENTED=NO
RUNTIME_OWNER=I6/I7/I8_INTEGRATION

I5_OWNERSHIP=scientific/evidence contract; applicability vocabulary; safe/forbidden states; provenance/lineage requirements; cross-layer interface expectations
I6_OWNERSHIP=canonical personal memory/context; memory writes; clinical feature projection runtime; lineage-backed feature reads
I7_OWNERSHIP=longitudinal user intelligence / longitudinal applicability context
I8_OWNERSHIP=personalized evidence applicability runtime; user_evidence_match runtime; grounded recommendation intelligence

I5_PERSONAL_MEMORY_WRITE=NO
I5_CANONICAL_USER_RECORD=NO
I5_USER_PROFILE_MUTATION=NO
I5_RUNTIME_DECISION_OWNER=NO
DUPLICATE_SOT_CREATED=NO
LLM_INVENTED_USER_FACT_PATH=NO

LINEAGE_CONTRACT=YES (source_record_type+id mandatory; REUSE existing SoTs only)
EXISTING_SOT_MAPPING=user_conditions|user_medications|user_memory_facts|physiological_measurements|user_profile_core|user_profile_knowledge|care_episodes
APPLICABILITY_INPUT_CONTRACT=YES (16 frozen features + required/optional/missing)
USER_EVIDENCE_MATCH_CONTRACT=YES (13 frozen fields + evidence_ku_id + feature_lineage_refs)
MISSING_FEATURE_BEHAVIOR=INSUFFICIENT_EVIDENCE fail-closed
CONTRAINDICATION_FAIL_CLOSED=YES
SAFE_STATES_TEST=PASS
FORBIDDEN_STATES_TEST=PASS (incl. synonym bypass rejection)

I8_RUNTIME_HOOK=GOVERNED_DISEASE_APPLICABILITY_AVAILABLE=False (fail-closed; unchanged)
CROSS_LAYER_MATRIX=YES (9 contract items; gaps recorded; next owners I6/I7/I8)
RUNTIME_INTEGRATION_GAPS=YES (projection/match persistence/runtime not implemented under I5)

PACKAGE=backend/app/services/i5/know06/*
TESTS=backend/tests/test_i5_know06_patient_evidence_applicability_contract.py
CI_WORKFLOW=i5-know06-patient-evidence-applicability-contract.yml
CI_RUN=33005636191 SUCCESS tip 4874379e3d155dd251dd53ada3ee9eb339e5f12b

ALEMBIC=070_i8_proactive_evaluation_ledger
DB_COHERENCE=PASS (unchanged; no schema mutation)
I6_MUTATION=NO
I7_MUTATION=NO
I8_MUTATION=NO
I9_MUTATION=NO
FRONTEND_MUTATION=NO
I6_I7_I8_REGRESSION=NO
BACKEND_FRONTEND_REGRESSION=NO
D01_D19_REGRESSION=NO
AUTONOMOUS_WEEKLY_SIDE_STAGE=ON
AUTO_ACTIVATION=NO

HARD_STOPS_HONORED=
  NO_ALEMBIC_071=YES
  NO_SCHEMA_ENUM_CHANGE=YES
  NO_PERSONAL_DATA_TABLE=YES
  NO_DUPLICATE_CLINICAL_SOT=YES
  NO_I5_MEMORY_WRITE=YES
  NO_I6_I7_I8_IMPL_MUTATION=YES
  NO_TREATMENT_DECISION_ENGINE=YES
  NO_RAG_ANN=YES
  NO_SOURCE_ACTIVATION=YES
  NO_SCHEDULER_CHANGE=YES
  NO_FRONTEND_NOTIFICATION_CHANGE=YES
  NO_FORCE_PUSH=YES
  NO_MANUAL_DEPLOY=YES
  NO_PRODUCTION_MUTATION=YES

FINDING_DB01=DEFERRED
FINDING_MEMORY_CURRENT_WRITE_STUB=DEFERRED
FINDING_LEGACY_ONBOARDING=DEFERRED
FINDING_IMAGE_ID_PROVENANCE_NOTE=DEFERRED

MASTER_LOG_TIP=§385
CURSOR_HANDOFF_TIP=v677
NOTE=§384 preserved unchanged; §385 append-only PASS_CLOSED.
NOTE=post-§385 final master-log whole-file self-SHA is NOT embedded inside §385.
"""

suffix = sec.replace("\r\n", "\n").encode("utf-8")
result = append_bytes(path, suffix)
post = read_exact(path)
assert post.startswith(pre)
assert sha256_hex(post[: len(pre)]) == pre_sha
assert "§385".encode("utf-8") in post
print("PRE_SHA", pre_sha)
print("POST_SHA", sha256_hex(post))
print(result)

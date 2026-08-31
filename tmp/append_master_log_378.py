from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
pre_sha = sha256_hex(pre)
assert pre_sha == "CDECDA5A21CC32DDC454728041C38F5E85DE80AA835FEE268A87555BDC8568FE"
assert b"\xc2\xa7378" not in pre
assert pre.endswith(
    b"NOTE=post-\xc2\xa7377 final master-log whole-file self-SHA is NOT embedded inside \xc2\xa7377.\n"
)

ts = "2026-08-26T13:40:00Z"
sec = f"""

§378 - PD-I5-V1-ALS-MS-SPECIALIZED-SERVING-ELIGIBILITY-01 PASS CLOSED
---------------------------------------------------------------------
GATE=PD-I5-V1-ALS-MS-SPECIALIZED-SERVING-ELIGIBILITY-01
TITLE=SPECIALIZED D18/D19 SERVING ELIGIBILITY WITHOUT MEDLINEPLUS GLOBAL LOW-RISK
GATE_TYPE=I5 ELIGIBILITY + CONTENT QUALITY + CI + GITHUB-ONLY PRODUCTION + RETRIEVAL PROOF + DOCS
PRODUCT_OWNER_APPROVAL=YES
CURSOR_MODEL_MODE=AUTO
TIMESTAMP={ts}
PARENT=§377
FEATURE_BRANCH=feature/section15/backend-continuity-foundation
START_HEAD=a6c3b2bef25f0d10fc55d299fd356cdbccc16d9e
FINAL_HEAD=recorded in Cursor handoff v670 REPO_HEAD after docs commit
MASTER_LOG_IN=§377
CURSOR_HANDOFF_IN=v669
CHATGPT_CONTINUITY=v687
CHATGPT_MUTATED=NO

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS
LAW13_CHECK=PASS

GATE_RESULT=PASS
GITHUB_ONLY_EXECUTION=PASS
NEXT_GATE_AUTHORIZED=NO

ELIGIBILITY_GRANULARITY=source+entity(URL/manifest_entity_id)+content_quality
IMPLEMENTATION_MODE=EXISTING_POLICY_COMPATIBLE (no schema/migration; no new publisher; MedlinePlus global low-risk remains NO)

MEDLINEPLUS_GLOBAL_LOW_RISK=NO
SPECIALIZED_D18_ELIGIBILITY=YES
SPECIALIZED_D19_ELIGIBILITY=YES

STAGE1_SEAM=
  PRIOR=source+domain low-risk only
  SOLUTION=governed_specialized_entity_eligibility.py wired into finalize_governed_runtime_eligibility
  HARD_STOP=NO

STAGE2_CONTRACT=
  SOURCE=medlineplus_consumer_health activation/rights/robots PASS
  URL_SCOPE=ALS/MS MedlinePlus pages only
  PROVENANCE_COMPLETE=REQUIRED
  CONTENT_QUALITY=REQUIRED (nav/chrome reject)
  NO_DIAGNOSIS_PRESCRIPTION=YES
  ATTRIBUTION=PRESERVED

STAGE3_QUALITY=
  NAV_CHROME_REJECTION=PASS (legacy chrome KUs remain REVIEW_REQUIRED / not serving-eligible)
  SELF_HEAL_EXTRACTION=bounded strip_html_nav_chrome + claim claim window (extractor 1.0.1)
  NO_BROAD_PARSER_REDESIGN=YES

STAGE4_CI=
  WORKFLOW=I5 Specialized D18 D19 Serving Eligibility CI
  PASS_RUN=32974215969

STAGE5_PRODUCTION=
  WORKFLOW=W6-P01 Production Activate Weekly
  CONFIRMATION=SPECIALIZED_D18_D19_ELIGIBILITY
  PROOF_RUN=32975081464 SUCCESS
  ACQUIRE_RUN=32974376803 (first apply; retrieval stdin self-heal follows)
  IMAGE_TAG_UNCHANGED=d039988844b61860caa504d275881237623352f8
  ALEMBIC=070_i8_proactive_evaluation_ledger
  KU_BEFORE=30 KU_AFTER=32
  ELIGIBLE_BEFORE=4 ELIGIBLE_AFTER=6
  KCE_BEFORE=8 KCE_AFTER=12
  D18_ALS_KU=2 D18_ALS_ELIGIBLE=1
  D19_MS_KU=3 D19_MS_ELIGIBLE=1

STAGE6_RETRIEVAL=
  ALS_RETRIEVAL=PASS (SCIS lexical; ku_id=31; source_profile_id present)
  MS_RETRIEVAL=PASS (SCIS lexical; ku_id=32; source_profile_id present)
  ELIGIBILITY_GATE=PASS
  PROVENANCE=PASS
  SOURCE_ATTRIBUTION=PASS
  DENSE_ANN_DEPENDENCY=NO
  I7_MEMORY_CURRENT_STUB=UNCHANGED (record/defer)

STAGE7_LAW13=
  ALEMBIC_070=PASS
  DB_COHERENCE=PASS
  SOURCE_REGISTRY=PASS
  I6_I7_I8_REGRESSION=NO
  BACKEND_FRONTEND_REGRESSION=NO
  FINDING_DB01=DEFERRED
  FINDING_MEMORY_CURRENT_WRITE_STUB=DEFERRED

HARD_STOPS_HONORED=
  NO_ALEMBIC_071=YES
  NO_GLOBAL_MEDLINEPLUS_LOW_RISK=YES
  NO_NEW_PUBLISHER=YES
  NO_RAG_ANN=YES
  NO_FORCE_PUSH=YES
  NO_MANUAL_DEPLOY=YES

MASTER_LOG_TIP=§378
CURSOR_HANDOFF_TIP=v670
NOTE=§377 preserved unchanged; §378 append-only PASS_CLOSED.
NOTE=post-§378 final master-log whole-file self-SHA is NOT embedded inside §378.
"""

suffix = sec.replace("\r\n", "\n").encode("utf-8")
result = append_bytes(path, suffix)
post = read_exact(path)
assert post.startswith(pre)
assert b"\xc2\xa7378" in post
print("PRE_SHA", result["pre_sha256"])
print("POST_SHA", sha256_hex(post))
print("OK")

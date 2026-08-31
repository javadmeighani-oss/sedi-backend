from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
pre_sha = sha256_hex(pre)
assert pre_sha == "447B3A50CCB9379A05384D56823C4514D3AF217620D7E3DADD6FA425791E44A1"
assert "§379".encode("utf-8") not in pre
assert pre.endswith(
    "NOTE=post-§378 final master-log whole-file self-SHA is NOT embedded inside §378.\n".encode(
        "utf-8"
    )
)

ts = "2026-08-26T14:15:00Z"
sec = f"""

§379 - PD-I5-V1-D01-D17-GOVERNED-KNOWLEDGE-EXPANSION-WAVE02-01 PASS CLOSED
----------------------------------------------------------------------------
GATE=PD-I5-V1-D01-D17-GOVERNED-KNOWLEDGE-EXPANSION-WAVE02-01
TITLE=WAVE02 D01-D17 GOVERNED KNOWLEDGE EXPANSION UNDER EXISTING 4 PUBLISHERS
GATE_TYPE=I5 ALLOWLIST URL EXPANSION + CANDIDATE GAP LIST + CI + GITHUB-ONLY PRODUCTION + RETRIEVAL + DOCS
PRODUCT_OWNER_APPROVAL=YES
CURSOR_MODEL_MODE=AUTO
TIMESTAMP={ts}
PARENT=§378
FEATURE_BRANCH=feature/section15/backend-continuity-foundation
START_HEAD=d250ff3c2a86d5d0f647a80572fa30de6650c353
FINAL_HEAD=recorded in Cursor handoff v671 REPO_HEAD after docs commit
MASTER_LOG_IN=§378
CURSOR_HANDOFF_IN=v670
CHATGPT_CONTINUITY=v687
CHATGPT_MUTATED=NO

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS
LAW13_CHECK=PASS

GATE_RESULT=PASS
GITHUB_ONLY_EXECUTION=PASS
NEXT_GATE_AUTHORIZED=NO

ACTIVE_SOURCE_COUNT=4
PUBLISHERS=NHS,CDC,MedlinePlus,NIMH
ALLOWLIST_VERSION=i5-multisource-v1-wave02
NEW_SOURCE_ACTIVATED=NO
MEDLINEPLUS_GLOBAL_LOW_RISK=NO
NIMH_GLOBAL_LOW_RISK=NO

D01_D17_COVERAGE_EXPANDED=YES
DOMAINS_WITH_NEW_KU=D01,D02,D03,D04,D05,D06,D07,D08,D09,D10,D11,D12,D13,D14,D15,D16
DOMAINS_STILL_UNCOVERED=D17
DOMAINS_WITH_NEW_ELIGIBLE_KU=D12 (plus lifestyle/KD eligible via NHS/CDC low-risk path)
CANDIDATE_SOURCE_GAP_COUNT=13
CANDIDATE_SOURCE_LIST_STATUS=PRESENT_NON_ACTIVE
QUALIFICATION_STATUS=CANDIDATE_ONLY

STAGE1_MATRIX=
  AUTHORITY=coverage_manifest_v1.yaml D01-D17 names unchanged
  WAVE02_TARGETS=YES for D01-D16 acquisition + lifestyle KD eligible growth; D17 SOURCE_GAP
  D18_D19=REGRESSION_ONLY

STAGE2_SOURCE_FIT=
  NHS=bounded live-well URLs (healthy-weight/quit-smoking/alcohol-advice/seasonal-health) low-risk YES
  CDC=physical-activity hubs only (healthyliving paths retired on CDC redesign; pattern preserved)
  MedlinePlus=D01-D16 topic URLs acquisition; specialized serving still D18/D19 only
  NIMH=anxiety + caring-for-your-mental-health acquisition; low-risk NO
  DISCOVERY_NE_AUTHORIZATION=YES
  FETCH_NE_SERVING_ELIGIBLE=YES

STAGE3_PIPELINE=
  coverage_identity=wave02_coverage_identity.py (acquisition stamp; not specialized eligibility)
  weekly_orchestrator=URL→Dxx/KD identity after specialized resolve
  idempotent_weekly_x2=PASS
  no_uncontrolled_bulk_crawl=YES

STAGE4_CI=
  WORKFLOW=I5 Wave02 Governed Knowledge Expansion CI
  PASS_RUN=32977894743 (push) + 32977963778 (dispatch)

STAGE5_PRODUCTION=
  WORKFLOW=W6-P01 Production Activate Weekly
  CONFIRMATION=WAVE02_I5_D01_D17_EXPANSION
  APPLY_RUN=32977973694 (growth PASS; retrieval FTS proof FAIL then fixed)
  PROOF_RUN=32978485220 SUCCESS
  IMAGE_TAG_UNCHANGED=d039988844b61860caa504d275881237623352f8
  ALEMBIC=070_i8_proactive_evaluation_ledger
  KU_BEFORE=32 KU_AFTER=67 KU_DELTA=+35
  ELIGIBLE_BEFORE=6 ELIGIBLE_AFTER=16 ELIGIBLE_DELTA=+10
  KCE_BEFORE=12 KCE_AFTER=32 KCE_DELTA=+20
  D18_ALS_REGRESSION=NO
  D19_MS_REGRESSION=NO

STAGE6_RETRIEVAL=
  RETRIEVAL_COMPATIBILITY=PASS (SCIS lexical; statement-derived / short-token queries)
  ELIGIBILITY_GATE=PASS
  PROVENANCE=PASS
  ATTRIBUTION=PASS
  NO_DENSE_ANN_DEPENDENCY=YES
  I7_MEMORY_CURRENT_STUB=UNCHANGED (record/defer)

STAGE7_LAW13=
  ALEMBIC_070=PASS
  DB_COHERENCE=PASS
  SOURCE_REGISTRY=PASS
  KU_PROVENANCE_KCE=PASS
  I6_I7_I8_REGRESSION=NO
  BACKEND_FRONTEND_REGRESSION=NO
  FINDING_DB01=DEFERRED
  FINDING_MEMORY_CURRENT_WRITE_STUB=DEFERRED
  FINDING_LEGACY_ONBOARDING=DEFERRED
  FINDING_IMAGE_ID_PROVENANCE_NOTE=DEFERRED

HARD_STOPS_HONORED=
  NO_ALEMBIC_071=YES
  NO_NEW_PUBLISHER=YES
  NO_PATTERN_BROADENING=YES
  NO_GLOBAL_MEDLINEPLUS_NIMH_LOW_RISK=YES
  NO_RAG_ANN=YES
  NO_FORCE_PUSH=YES
  NO_MANUAL_DEPLOY=YES

MASTER_LOG_TIP=§379
CURSOR_HANDOFF_TIP=v671
NOTE=§378 preserved unchanged; §379 append-only PASS_CLOSED.
NOTE=post-§379 final master-log whole-file self-SHA is NOT embedded inside §379.
"""

# Match tip EOL (LF-only after §378).
suffix = sec.replace("\r\n", "\n").encode("utf-8")
if not suffix.startswith(b"\n"):
    raise SystemExit("suffix must start with blank line separator")
result = append_bytes(path, suffix)
post = read_exact(path)
assert post.startswith(pre)
assert "§379".encode("utf-8") in post
print("PRE_SHA", pre_sha)
print("POST_SHA", sha256_hex(post))
print("POST_SIZE", len(post))
print("PREFIX_OK", post.startswith(pre))
print(result)

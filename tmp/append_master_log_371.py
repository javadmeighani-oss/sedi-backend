from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
assert sha256_hex(pre) == "E5C2B1DB9700909B0574DBA5993E12EC6D16C482BDB90DC70431A77FBAA48CE5"
assert b"\xc2\xa7371" not in pre
assert pre.endswith(
    b"NOTE=post-\xc2\xa7370 final master-log whole-file self-SHA is NOT embedded inside \xc2\xa7370.\r\n"
)

ts = "2026-08-26T03:20:00Z"
sec = f"""

§371 - PD-I5-V1-SOURCE-FORMAT-RESILIENCE-PRODUCTION-01 HARD STOP (GHCR TLS PULL) + CODE/CI PASS
------------------------------------------------------------------------------------------------------------------
GATE=PD-I5-V1-SOURCE-FORMAT-RESILIENCE-PRODUCTION-01
TITLE=FORMAT RESILIENCE ADAPTERS + DRIFT/SECURITY + CI GREEN; PRODUCTION IMAGE ROLLFORWARD BLOCKED
APPROVED_BY=Javad
PRODUCT_OWNER_APPROVAL=YES
RECORDED_AT_UTC={ts}
CURSOR_MODEL_MODE=AUTO
GATE_TYPE=IMPLEMENTATION + TARGETED CI + GOVERNED BUILD/DEPLOY ATTEMPT + DOCS CLOSURE
IMPLEMENTATION_AUTHORIZED=YES (adapters/classifier/drift/tests/CI/build/deploy path + Master Log/handoff)
GATE_RESULT=HARD_STOP
HARD_STOP_REASON=PRODUCTION_HOST_GHCR_TLS_HANDSHAKE_TIMEOUT (docker pull of new image failed 3x; prior image unchanged)
PARENT=§370

MASTER_LOG_IN=§370
CURSOR_HANDOFF_IN=v662
CHATGPT_CONTINUITY=v686
CHATGPT_MUTATED=NO

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS
LAW13_CHECK=PASS (code/contract layers; production runtime remains prior image)

START_HEAD=b04af26593a57f11c6e4e98a1be9cb129bc20e8d
IMPLEMENTATION_COMMIT=d039988844b61860caa504d275881237623352f8
FINAL_HEAD=recorded in Cursor handoff v663 after this closure commit
FEATURE_BRANCH=feature/section15/backend-continuity-foundation

FORMAT_RESILIENCE_DB_STORAGE_SUFFICIENT=YES
SCHEMA_MUTATION=NO
MIGRATION=NO
ALEMBIC=070_i8_proactive_evaluation_ledger

IMPLEMENTATION_PATHS=
  backend/app/services/i5/adapters/representation_classifier.py
  backend/app/services/i5/adapters/format_drift.py
  backend/app/services/i5/adapters/live_fetch.py
  backend/app/services/i5/adapters/tabular_docx.py
  backend/app/services/i5/adapters/pdf_jats.py (scanned PDF REVIEW_REQUIRED; fetch_live)
  backend/app/services/i5/adapters/official_api.py (fetch_live)
  backend/app/services/i5/adapters/rss_feed.py (fetch_live)
  backend/app/services/i5/adapters/base.py (CSV_TSV/DOCX modes; REVIEW_REQUIRED)
  backend/app/services/i5/conceptual_extraction.py (JATS/PDF/CSV/DOCX routes)
  backend/app/services/i5/know01/format_capability_matrix.py
  backend/app/services/i5/governed_weekly_runtime.py (adapter_id/version in attribution_data)
  backend/requirements.txt (pypdf)
  backend/tests/test_i5_source_format_resilience.py
  .github/workflows/i5-source-format-resilience-runtime.yml

FORMAT_MATRIX_AFTER=
  HTML=PRODUCTION_READY (CI+existing live HTML path)
  JSON_API=PRODUCTION_READY (CI+fetch_live; LIVE_EXTERNAL_SOURCE_PROOF=PENDING)
  RSS_ATOM=PRODUCTION_READY (CI+fetch_live; LIVE_EXTERNAL_SOURCE_PROOF=PENDING)
  XML_JATS=PRODUCTION_READY (CI+fetch_live; LIVE_EXTERNAL_SOURCE_PROOF=PENDING)
  PDF_TEXT=PRODUCTION_READY (CI+fetch_live; LIVE_EXTERNAL_SOURCE_PROOF=PENDING)
  CSV_TSV=PRODUCTION_READY (CI+fetch_live; LIVE_EXTERNAL_SOURCE_PROOF=PENDING)
  DOCX=PRODUCTION_READY (CI+fetch_live; LIVE_EXTERNAL_SOURCE_PROOF=PENDING)
  SCANNED_PDF_DETECTION=PASS (REVIEW_REQUIRED / PDF_IMAGE_ONLY)
  AUTOMATIC_OCR=DEFERRED_GOVERNED

CONTENT_SIGNATURE_VALIDATION=PASS
FORMAT_DRIFT_DETECTION=PASS
STRUCTURE_DRIFT_DETECTION=PASS
SOURCE_IDENTITY_PRESERVATION=PASS
ADAPTER_VERSION_PROVENANCE=PASS (attribution_data JSON; no schema change)
LAST_KNOWN_GOOD_PRESERVATION=PASS
UNKNOWN_FORMAT_FAIL_CLOSED=PASS
SECURITY_BOUND_TESTS=PASS
TARGETED_TESTS=PASS (local + CI)

CI=
  I5 Source Format Resilience Runtime PASS run=32924583367
  W3-P01 Adapter Framework Runtime PASS run=32924612941
BUILD=
  Build Sedi Backend Image PASS run=32924964918
  BUILT_IMAGE_SHA=d039988844b61860caa504d275881237623352f8
  BUILT_DIGEST=sha256:ba7d688181bdfbc7a2d36209d79f00343bdcc7e035d0a48ff4b803923adfdff9

DEPLOY_ATTEMPTS=
  32925210887 FAIL TLS handshake timeout
  32925303074 FAIL TLS handshake timeout
  32925490556 FAIL TLS handshake timeout
PRODUCTION_IMAGE_UNCHANGED=YES
PRE_PROD_IMAGE=b1990e61ab7bdeb94befb575f27ee3d5bf0d3568
PRE_PROD_DIGEST=sha256:68f71154e0850e5cf070c07c71ff40483137f1ec36bfecd14fe19a7f18893634
NEW_PROD_IMAGE=UNCHANGED
NEW_PROD_DIGEST=UNCHANGED

POST_PROD_VERIFY=
  W6_READONLY=32925648099 (exit20 I8-ON guard; evidence PASS)
  GATE4B=32925645391 SUCCESS
  MULTISOURCE=ON
  ACTIVE_SOURCE_COUNT=4 (unchanged)
  KU_TOTAL=26 ELIGIBLE_KU=3 KCE_TOTAL=6
  NHS_ELIGIBLE=2 CDC_ELIGIBLE=1
  MEDLINEPLUS_AUTO_ELIGIBLE=NO NIMH_AUTO_ELIGIBLE=NO
  ALS_ELIGIBLE_KU=0 MS_ELIGIBLE_KU=0
  CRON=fri 03:30 Asia/Tehran (unchanged)
  I8=ON/CLOSED
  HEALTH=PASS
  DB_COHERENCE=PASS
  I6_I7_I8_I9_REGRESSION=NO
  RAG_CONTRACT_REGRESSION=NO
  FRONTEND_CONTRACT_REGRESSION=NO

HISTORICAL_PREFIX_THROUGH_§370_BYTE_EXACT=PASS
HISTORICAL_BYTE_DRIFT=0
HISTORICAL_EOL_DRIFT=0

TOP_REMAINING_P0=
  1) retry governed deploy when production host can pull GHCR
  2) D01-D19 governed knowledge expansion
  3) KNOW-06 / retrieval production proof
NEXT_PROPOSED_GATE=PD-I5-V1-SOURCE-FORMAT-RESILIENCE-DEPLOY-RETRY-01
NEXT_GATE_AUTHORIZED=NO

CURSOR_HANDOFF=v663
CURSOR_HANDOFF_EXTERNAL_ONLY=YES
NOTE=§370 preserved unchanged; §371 append-only HARD_STOP closure (code/CI ready; deploy blocked).
NOTE=post-§371 final master-log whole-file self-SHA is NOT embedded inside §371.
"""
sec = sec.replace("\r\n", "\n").replace("\n", "\r\n")
meta = append_bytes(path, sec.encode("utf-8"))
print("PRE_SHA", meta["pre_sha256"])
print("POST_SHA", meta["post_sha256"])
print("MASTER_LOG_TIP=§371")

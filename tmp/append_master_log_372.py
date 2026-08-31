from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
assert sha256_hex(pre) == "00754EA18D50EE6DBA6744EF7C20FDEF59C8E8A63D646A1AB56677C6026AE89F"
assert b"\xc2\xa7372" not in pre
assert pre.endswith(
    b"NOTE=post-\xc2\xa7371 final master-log whole-file self-SHA is NOT embedded inside \xc2\xa7371.\r\n"
)

ts = "2026-08-26T03:35:00Z"
sec = f"""

§372 - PD-I5-V1-SOURCE-FORMAT-RESILIENCE-DEPLOY-RETRY-01 HARD STOP (GHCR TLS PRECHECK FAIL)
------------------------------------------------------------------------------------------------------------------
GATE=PD-I5-V1-SOURCE-FORMAT-RESILIENCE-DEPLOY-RETRY-01
TITLE=DEPLOY RETRY BLOCKED BY PRODUCTION-HOST GHCR TLS/MANIFEST PRECHECK
APPROVED_BY=Javad
PRODUCT_OWNER_APPROVAL=YES
RECORDED_AT_UTC={ts}
CURSOR_MODEL_MODE=AUTO
GATE_TYPE=DEPLOY RETRY ONLY (no app implementation)
IMPLEMENTATION_AUTHORIZED=YES (read-only GHCR precheck path + docs; deploy only if precheck PASS)
GATE_RESULT=HARD_STOP
HARD_STOP_REASON=GHCR_TLS_FAIL + GHCR_MANIFEST_FAIL on production host (Stage 1); no pull/recreate/deploy
PARENT=§371

MASTER_LOG_IN=§371
CURSOR_HANDOFF_IN=v663
CHATGPT_CONTINUITY=v686
CHATGPT_MUTATED=NO

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS
LAW13_CHECK=PASS

START_HEAD=34753d73315280daf4fc437480bd0d218fe2de6c
OPS_COMMITS=
  2c2f7769bfb6e6e32e0512e6f979c6426292a603 (prod-ghcr-connectivity-precheck.yml; not registered on main)
  2ab6cedde86f3bef64950bc56dcb774a0f280c40 (Gate4B readonly GHCR probe)
FINAL_HEAD=recorded in Cursor handoff v664 after this closure commit
FEATURE_BRANCH=feature/section15/backend-continuity-foundation

BUILD_PROOF=
  run=32924964918 SUCCESS
  TAG=d039988844b61860caa504d275881237623352f8
  TARGET_DIGEST=sha256:ba7d688181bdfbc7a2d36209d79f00343bdcc7e035d0a48ff4b803923adfdff9
  TAG_TO_DIGEST=PROVEN

OLD_PROD_DIGEST=sha256:68f71154e0850e5cf070c07c71ff40483137f1ec36bfecd14fe19a7f18893634
OLD_PROD_DIGEST_USED_AS_EXPECTED_FOR_NEW_IMAGE=NO (forbidden; not attempted)

STAGE1_PRECHECK=
  Gate4B_run=32926737135 exit=20
  RUNNING_IMAGE=ghcr.io/javadmeighani-oss/sedi-backend:b1990e61ab7bdeb94befb575f27ee3d5bf0d3568
  HEALTH=PASS (local /health+/healthz before GHCR section)
  ALEMBIC=070 present (alembic current/heads executed)
  GHCR_DNS=PASS
  GHCR_TCP443=PASS
  GHCR_TLS=FAIL
  GHCR_MANIFEST=FAIL
  GHCR_CONNECTIVITY=FAIL

STAGE2_DEPLOY=NOT_ATTEMPTED
STAGE3_VERIFY=N/A (no image change)
CONTAINER_RECREATE=NO
PRODUCTION_IMAGE_UNCHANGED=YES
TLS_BYPASS=NO
SCHEMA_MUTATION=NO
MIGRATION=NO
I5_FLAG_OR_SCHEDULE_CHANGE=NO

PULLED_DIGEST=N/A
RUNNING_DIGEST=UNCHANGED (prior digest)
MULTISOURCE=ON (baseline preserved; not mutated this Gate)
FORMAT_RUNTIME_CANARY=NOT_RUN (deploy blocked)
LIVE_EXTERNAL_SOURCE_PROOF=PENDING

HISTORICAL_PREFIX_THROUGH_§371_BYTE_EXACT=PASS
HISTORICAL_BYTE_DRIFT=0
HISTORICAL_EOL_DRIFT=0

NEXT_PROPOSED_GATE=PD-I5-V1-SOURCE-FORMAT-RESILIENCE-DEPLOY-RETRY-01 (retry when prod-host GHCR TLS restored)
OR_INFRA=restore production-host TLS path to ghcr.io:443 (no insecure registry / no TLS bypass authorized)
NEXT_GATE_AUTHORIZED=NO

CURSOR_HANDOFF=v664
CURSOR_HANDOFF_EXTERNAL_ONLY=YES
NOTE=§371 preserved unchanged; §372 append-only HARD_STOP closure.
NOTE=post-§372 final master-log whole-file self-SHA is NOT embedded inside §372.
"""
sec = sec.replace("\r\n", "\n").replace("\n", "\r\n")
meta = append_bytes(path, sec.encode("utf-8"))
print("PRE_SHA", meta["pre_sha256"])
print("POST_SHA", meta["post_sha256"])
print("MASTER_LOG_TIP=§372")

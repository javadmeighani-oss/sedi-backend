from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
assert sha256_hex(pre) == "BC2FAFDD90B4C5F26B5D8B8A2671986CB6BD99EB1E6A21BC3947C664F6EA4772"
assert pre.endswith(
    b"NOTE=post-\xc2\xa7373 final master-log whole-file self-SHA is NOT embedded inside \xc2\xa7373.\r\n"
)

ts = "2026-08-26T04:05:00Z"
sec = f"""

§374 - PD-I5-V1-GHCR-EGRESS-REMEDIATION-01 HARD STOP (EGRESS FIX NOT APPLICABLE FROM APP PATH)
------------------------------------------------------------------------------------------------------------------
GATE=PD-I5-V1-GHCR-EGRESS-REMEDIATION-01
TITLE=SECURE GHCR EGRESS REMEDIATION ATTEMPT — PROVIDER PATH OUTSIDE SSH/APP CONTROL
APPROVED=YES
PRODUCT_OWNER_APPROVAL=YES
RECORDED_AT_UTC={ts}
CURSOR_MODEL_MODE=AUTO
GATE_TYPE=INFRA EGRESS REMEDIATION + CONDITIONAL DEPLOY
IMPLEMENTATION_AUTHORIZED=YES (egress path fix if reachable; deploy only after GHCR PASS; docs)
GATE_RESULT=HARD_STOP
HARD_STOP_REASON=GHCR_TLS still FAIL; provider/Cloud.ir egress allowlist/path not controllable from approved SSH/app/GitHub path; no forbidden bypass used
PARENT=§373

MASTER_LOG_IN=§373
CURSOR_HANDOFF_IN=v665
CHATGPT_CONTINUITY=v687
CHATGPT_MUTATED=NO

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS
LAW13_CHECK=PASS

START_HEAD=55de26521c901208899105693e31464494d012ec
FINAL_HEAD=recorded in Cursor handoff v666 after this closure commit
FEATURE_BRANCH=feature/section15/backend-continuity-foundation
WORKFLOW_MUTATION_THIS_GATE=NO (reuse ratified Gate4B diagnostic; no new workflow rewrite)

STAGE1_RECHECK=
  Gate4B=32928432005 exit=20
  W6_READONLY=32928433912 exit=20 (I8-ON guard; evidence PASS)
  RUNNING_IMAGE=ghcr.io/javadmeighani-oss/sedi-backend:b1990e61ab7bdeb94befb575f27ee3d5bf0d3568
  RUNNING_DIGEST=sha256:68f71154e0850e5cf070c07c71ff40483137f1ec36bfecd14fe19a7f18893634
  HEALTH=PASS
  ALEMBIC=070_i8_proactive_evaluation_ledger count=1
  MULTISOURCE=ON
  SOURCE_ACTIVATION=ON
  I8=ON
  KU_TOTAL=26 ELIGIBLE=3
  GHCR_TLS_BEFORE=FAIL
  GHCR_DNS=PASS
  GHCR_TCP443=PASS
  GHCR_IPV4_TLS=FAIL
  GHCR_IPV6_TLS=FAIL
  GHCR_OPENSSL=FAIL
  GHCR_MANIFEST=FAIL
  GHCR_V2=FAIL
  CTRL_GITHUB_TLS=PASS
  CTRL_SEDI_TLS=PASS
  ROOT_CAUSE_CLASS=PROVIDER_EGRESS_FILTER (reconfirmed)

STAGE2_REMEDIATION=
  REMEDIATION=NOT_APPLIED
  REASON=No Cloud.ir/provider egress control-plane credential or approved API exists in Sedi GitHub/SSH allowlist; host shows TCP accept + TLS handshake timeout to ghcr.io while other HTTPS works — classic provider/middlebox egress filter beyond host iptables app scope
  FORBIDDEN_PATHS_NOT_USED=TLS_VERIFY_DISABLE,INSECURE_REGISTRY,RANDOM_MIRROR,UNAPPROVED_PROXY,ALTERNATE_ARTIFACT_TRANSFER
  APP_DB_SCHEMA_MIGRATION_SOURCE_SCHEDULER_RAG_FRONTEND_CHANGE=NO
  GHCR_TLS_AFTER=FAIL (unchanged)
  GHCR_MANIFEST=FAIL (unchanged)

STAGE3_DEPLOY=NOT_ATTEMPTED
TARGET_TAG=d039988844b61860caa504d275881237623352f8
TARGET_DIGEST=sha256:ba7d688181bdfbc7a2d36209d79f00343bdcc7e035d0a48ff4b803923adfdff9
OLD_DIGEST_ROLE=BASELINE_ONLY (not used as deploy expected digest)
PULLED_DIGEST=N/A
FORMAT_RUNTIME_CANARY=NOT_RUN
FORMAT_RESILIENCE_PRODUCTION=NOT_CLOSED (await GHCR egress fix then deploy-retry)

EXACT_REMAINING_INFRA_REQUIREMENT=
  Operator/Cloud.ir must allow complete outbound TLS sessions from the production VM to:
    - ghcr.io:443 (SNI=ghcr.io)
    - and GHCR-related CDN/registry endpoints required for docker pull of
      ghcr.io/javadmeighani-oss/sedi-backend:d039988844b61860caa504d275881237623352f8
  Evidence that TCP:443 alone is insufficient: TCP PASS + openssl/curl TLS timeout.
  Acceptance test after provider fix (read-only Gate4B):
    GHCR_IPV4_TLS=PASS
    GHCR_V2=PASS (https://ghcr.io/v2/ returns 200/401/403)
    GHCR_MANIFEST=PASS
  Then authorize/run PD-I5-V1-SOURCE-FORMAT-RESILIENCE-DEPLOY-RETRY-01 with TARGET_DIGEST only.

HISTORICAL_PREFIX_THROUGH_§373_BYTE_EXACT=PASS
HISTORICAL_BYTE_DRIFT=0
HISTORICAL_EOL_DRIFT=0

NEXT_PROPOSED_GATE=PD-I5-V1-SOURCE-FORMAT-RESILIENCE-DEPLOY-RETRY-01
PREREQ=Cloud.ir GHCR TLS egress restored + Gate4B GHCR_CONNECTIVITY=PASS
NEXT_GATE_AUTHORIZED=NO

CURSOR_HANDOFF=v666
CURSOR_HANDOFF_EXTERNAL_ONLY=YES
NOTE=§373 preserved unchanged; §374 append-only HARD_STOP closure.
NOTE=post-§374 final master-log whole-file self-SHA is NOT embedded inside §374.
"""
sec = sec.replace("\r\n", "\n").replace("\n", "\r\n")
meta = append_bytes(path, sec.encode("utf-8"))
print("PRE_SHA", meta["pre_sha256"])
print("POST_SHA", meta["post_sha256"])
print("MASTER_LOG_TIP=§374")

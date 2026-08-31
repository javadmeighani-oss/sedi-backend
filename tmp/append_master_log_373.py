from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
assert sha256_hex(pre) == "5BB1E537E4555A188153D68B9C7696ADF0A387E80396743D9017BB88A1943C2D"
# Tip marker §373 must not already be at tip (historical §373 elsewhere OK)
assert not pre.endswith(
    b"NOTE=post-\xc2\xa7373 final master-log whole-file self-SHA is NOT embedded inside \xc2\xa7373.\r\n"
)
assert pre.endswith(
    b"NOTE=post-\xc2\xa7372 final master-log whole-file self-SHA is NOT embedded inside \xc2\xa7372.\r\n"
)

ts = "2026-08-26T03:50:00Z"
sec = f"""

§373 - PD-I5-V1-GHCR-PROD-TLS-PATH-DIAGNOSIS-01 HARD STOP (PROVIDER_EGRESS_FILTER) — NO DEPLOY
------------------------------------------------------------------------------------------------------------------
GATE=PD-I5-V1-GHCR-PROD-TLS-PATH-DIAGNOSIS-01
TITLE=READ-ONLY GHCR TLS PATH DIAGNOSIS FROM PRODUCTION HOST
APPROVED=NO (diagnosis-only; deploy not authorized even if recovered)
PRODUCT_OWNER_APPROVAL=NO
RECORDED_AT_UTC={ts}
CURSOR_MODEL_MODE=AUTO
GATE_TYPE=READ-ONLY INFRA DIAGNOSIS
IMPLEMENTATION_AUTHORIZED=YES (readonly probes + Gate4B diagnostic workflow fix + Master Log/handoff only)
GATE_RESULT=HARD_STOP
HARD_STOP_REASON=GHCR_IPV4_TLS/OPENSSL/MANIFEST FAIL; ROOT_CAUSE_CLASS=PROVIDER_EGRESS_FILTER; APPROVED=NO
PARENT=§372

MASTER_LOG_IN=§372
CURSOR_HANDOFF_IN=v664
CHATGPT_CONTINUITY=v686
CHATGPT_MUTATED=NO

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS
LAW13_CHECK=PASS

START_HEAD=612f929f1503ae8f47369b337755544bb56d7a7c
OPS_COMMITS=
  651fa61362218fe2973d3c7a76368e6aff249816 (broken YAML attempt)
  8acf6fbc (Gate4B YAML fix + TLS diagnosis)
FINAL_HEAD=recorded in Cursor handoff v665 after this closure commit

STAGE1_BASELINE=
  W6_READONLY=32927207625 (exit20 I8-ON guard; evidence PASS)
  IMAGE=ghcr.io/javadmeighani-oss/sedi-backend:b1990e61ab7bdeb94befb575f27ee3d5bf0d3568
  DIGEST=sha256:68f71154e0850e5cf070c07c71ff40483137f1ec36bfecd14fe19a7f18893634
  HEALTH=PASS
  ALEMBIC=070_i8_proactive_evaluation_ledger count=1
  I8=ON
  MULTISOURCE=ON (preserved from §370/§372 production state; W6 evidence I8/health/alembic confirmed)
  KU_TOTAL=26 ELIGIBLE=3
  MUTATION=NO

STAGE2_DIAGNOSIS=
  Gate4B_run=32927415183 exit=20
  SYSTEM_UTC=2026-08-26T03:42:01Z
  CA_STATUS=PRESENT
  PROXY_STATUS=UNSET
  GHCR_DNS=PASS
  GHCR_A=PASS
  GHCR_AAAA=PRESENT
  GHCR_TCP443=PASS
  GHCR_IPV4_TLS=FAIL (curl -4 https://ghcr.io/v2/ rc=28 timeout ~15s; http=000 ssl_verify_result=1)
  GHCR_IPV6_TLS=FAIL (curl -6 rc=6)
  GHCR_OPENSSL=FAIL (openssl s_client timeout rc=124)
  GHCR_MANIFEST=FAIL (HEAD timeout rc=28)
  CTRL_GITHUB_TLS=PASS
  CTRL_SEDI_TLS=PASS
  DOCKER_REGISTRY_PATH=ghcr.io/javadmeighani-oss/sedi-backend (pull not executed)
  ROOT_CAUSE_CLASS=PROVIDER_EGRESS_FILTER
  INTERPRETATION=TCP/443 to ghcr.io accepts; TLS handshake to ghcr.io times out while github.com and api.sedi-ai.com TLS succeed; no host proxy; CA present; not a general TLS/CA outage

STAGE3_DECISION=
  DEPLOY_ATTEMPTED=NO
  REASON=connectivity FAIL + APPROVED=NO
  PULL=NO
  RECREATE=NO
  TLS_BYPASS=NO
  INSECURE_REGISTRY=NO

TARGET_TAG=d039988844b61860caa504d275881237623352f8
TARGET_DIGEST=sha256:ba7d688181bdfbc7a2d36209d79f00343bdcc7e035d0a48ff4b803923adfdff9
RUNNING_IMAGE=UNCHANGED b1990e61…
RUNNING_DIGEST=UNCHANGED sha256:68f71154…

PROPOSED_INFRA_REMEDIATION_GATE=
  PD-I5-V1-GHCR-EGRESS-REMEDIATION-01
  SCOPE=provider/Cloud.ir egress allowlist or path fix for ghcr.io:443 TLS (SNI ghcr.io) — outside app repo mutations
  MUST_NOT=disable TLS verify / insecure registry / random mirror / alternate artifact transfer without new PO approval

HISTORICAL_PREFIX_THROUGH_§372_BYTE_EXACT=PASS
HISTORICAL_BYTE_DRIFT=0
HISTORICAL_EOL_DRIFT=0

NEXT_PROPOSED_GATE=PD-I5-V1-GHCR-EGRESS-REMEDIATION-01
THEN=PD-I5-V1-SOURCE-FORMAT-RESILIENCE-DEPLOY-RETRY-01
NEXT_GATE_AUTHORIZED=NO

CURSOR_HANDOFF=v665
CURSOR_HANDOFF_EXTERNAL_ONLY=YES
NOTE=§372 preserved unchanged; §373 append-only HARD_STOP diagnosis closure.
NOTE=post-§373 final master-log whole-file self-SHA is NOT embedded inside §373.
"""
sec = sec.replace("\r\n", "\n").replace("\n", "\r\n")
meta = append_bytes(path, sec.encode("utf-8"))
print("PRE_SHA", meta["pre_sha256"])
print("POST_SHA", meta["post_sha256"])
print("MASTER_LOG_TIP=§373")

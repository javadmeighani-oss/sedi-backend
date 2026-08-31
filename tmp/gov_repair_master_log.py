from pathlib import Path
import hashlib, subprocess, re
from datetime import datetime, timezone

ROOT = Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace")
PATH = ROOT / "docs" / "SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md"
PARENT = "b4a6022d05b57fd165866b7f581eeb7c3227c9d3"
HEAD = "5e68db0a4254978425d0b05774f2570d3a6d31a8"

parent = subprocess.check_output(
    ["git", "show", f"{PARENT}:docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md"],
    cwd=ROOT,
)
current = PATH.read_bytes()

marker = "§".encode("utf-8")
dash = re.compile(br"^(\d+)\s*[\-\xE2\x80\x93]")


def section_offsets(blob: bytes):
    out = []
    start = 0
    while True:
        i = blob.find(marker, start)
        if i < 0:
            break
        if i == 0 or blob[i - 1 : i] == b"\n":
            m = dash.match(blob[i + len(marker) :])
            if m:
                out.append((i, int(m.group(1))))
        start = i + 1
    return out


cs = section_offsets(current)
c_map = {n: o for o, n in cs}
assert 350 in c_map and 351 in c_map and 352 not in c_map, c_map
sec_350_351 = current[c_map[350] :]
bare_lf = sec_350_351.count(b"\n") - sec_350_351.count(b"\r\n")
assert bare_lf == 0, bare_lf

ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
sec352_text = f"""

§352 - PD-I8-04A GOVERNANCE REPAIR / WORKFLOW RATIFICATION + MASTER LOG BYTE AUDIT-01
---------------------------------------------------------------------------------------------------------------
GATE=PD-I8-04A-GOVERNANCE-REPAIR-01
TITLE=WORKFLOW RATIFICATION + MASTER LOG BYTE/PREFIX REPAIR
APPROVED_BY=Javad
PRODUCT_OWNER_APPROVAL=YES
RECORDED_AT_UTC={ts}
CURSOR_MODEL_MODE=AUTO
GATE_TYPE=GOVERNANCE_REPAIR
IMPLEMENTATION_AUTHORIZED=NO
GATE_RESULT=PASS
HARD_STOP_REASON=NONE

ORIGINAL_PD_I8_04A_COMMIT={HEAD}
TECHNICAL_IMPLEMENTATION_REMAINS_VALID=YES
DB03_RUN=32620090216
DB03_RESULT=GREEN
ALEMBIC_HEAD=070_i8_proactive_evaluation_ledger
070_UNCHANGED=YES

INCIDENT_01_WORKFLOW=
  PATH=.github/workflows/db03-migration-rehearsal.yml
  OUTSIDE_ORIGINAL_ALLOWLIST=YES
  PARENT={PARENT}
  CURRENT={HEAD}
  EXACT_DELTA=069→070 head assertions (3); add test_i8_proactive_evaluation_pd_i8_04a.py to pytest list; ALEMBIC_HEAD echo 069→070
  WORKFLOW_DELTA_EXACT=YES
  WORKFLOW_DELTA_CLASS=MECHANICAL_REQUIRED_FOR_070_VALIDATION
  WORKFLOW_RATIFICATION=APPROVED_BY_PRODUCT_OWNER_VIA_THIS_REPAIR_GATE
  WORKFLOW_FURTHER_CHANGE=NO
  WORKFLOW_CHANGED_DURING_REPAIR=NO

INCIDENT_02_MASTER_LOG=
  FIRST_DIVERGENCE_BYTE_OFFSET=3290840
  SECTIONS_1_TO_343_TEXT_AFTER_EOL_NORM=IDENTICAL
  SECTIONS_344_TO_349_TEXT_AFTER_EOL_NORM=IDENTICAL_BODY (trailing append-separator blanks only)
  HISTORICAL_TEXT_CHANGED=NO
  HISTORICAL_EOL_ONLY=YES
  PARENT_344_349_EOL=LF_ONLY
  CURRENT_PRE_REPAIR_344_349_EOL=CRLF_ONLY
  BOUNDARY_BEFORE_344_PARENT=CRLF+LF+LF
  BOUNDARY_BEFORE_344_PRE_REPAIR=CRLF+CRLF+CRLF
  PARENT_PREFIX_THROUGH_349_SHA256=7C9299C6BDF79FE0552149496EE4F2FA408F7E171B031E2D76956CFE8DA2FEA3

APPLICABLE_LAW_PRECEDENCE=CASE_1
  APPEND_ONLY_BYTE_PRESERVATION=IN_FORCE (historical sections must not be rewritten)
  MASTER_LOG_EOL_CONTRACT=CRLF_ONLY (v622; applies to new appends; does not authorize rewriting committed historical prefix)
  S27_138_A20=historical LF prefix + CRLF append treated as DETECT of append tool, not mandate to convert historical bytes
  RESOLUTION=restore parent bytes through end of §349; preserve §350/§351 semantic content; append §352 CRLF

MASTER_LOG_REPAIR_ACTION=RESTORE_PARENT_PREFIX_THROUGH_349_THEN_REAPPEND_350_351_PLUS_352
NO_GIT_HISTORY_REWRITE=YES
NO_PRODUCTION_ACTION=YES
NO_CODE_MIGRATION_ORM_TEST_CHANGE=YES
NO_NEW_WORKFLOW_EDIT=YES

PD_I8_04A_TECHNICAL_STATUS=PASS_UNCHANGED
PD_I8_04A_GOVERNANCE_STATUS=REPAIRED
OVERALL_PD_I8_04A_STATUS=TECHNICAL_PASS_GOVERNANCE_REPAIRED

CURSOR_HANDOFF=v643
CURSOR_HANDOFF_EXTERNAL_ONLY=YES
NEXT_PROPOSED_GATE=PD-I8-04B scheduler cadence / Gate2-I9 adapters
NEXT_GATE_AUTHORIZED=NO
READY_FOR_JAVAD_REVIEW=YES
NOTE=post-§352 final master-log whole-file self-SHA is NOT embedded inside §352.
NOTE=Cursor handoff v643 exists external-only under LAW-10; not tracked in Git workspace.
NOTE=§§350/351 meaning preserved; incident recorded without concealment.
"""
sec352 = sec352_text.replace("\n", "\r\n").encode("utf-8")

if not parent.endswith(b"\n"):
    raise SystemExit("parent unexpected ending")

repaired = parent + b"\r\n\r\n" + sec_350_351 + sec352

rs = section_offsets(repaired)
r_map = {n: o for o, n in rs}
assert repaired.startswith(parent)
assert repaired[len(parent) : len(parent) + 4] == b"\r\n\r\n"
assert repaired[len(parent) + 4 : len(parent) + 4 + len(sec_350_351)] == sec_350_351
assert sum(1 for _, n in rs if n == 352) == 1
assert rs[-1][1] == 352
# §352 payload starts with CRLF blank separator; marker offset excludes that prefix.
assert repaired[r_map[350] : r_map[352]] == sec_350_351 + b"\r\n\r\n"

PATH.write_bytes(repaired)

final = PATH.read_bytes()
print("WROTE", len(final))
print("STARTSWITH_PARENT", final.startswith(parent))
print("PARENT_SHA", hashlib.sha256(parent).hexdigest().upper())
print(
    "FINAL_PREFIX_THROUGH_349_SHA",
    hashlib.sha256(final[: len(parent)]).hexdigest().upper(),
)
print("FINAL_FILE_SHA", hashlib.sha256(final).hexdigest().upper())
print("TIP", [n for _, n in section_offsets(final)[-4:]])
print("352_COUNT", sum(1 for _, n in section_offsets(final) if n == 352))
ok = (
    final.startswith(parent)
    and final[len(parent) : len(parent) + 4] == b"\r\n\r\n"
    and final[len(parent) + 4 : len(parent) + 4 + len(sec_350_351)] == sec_350_351
)
print("APPEND_ONLY_FINAL", "PASS" if ok else "FAIL")

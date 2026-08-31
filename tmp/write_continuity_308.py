from pathlib import Path
import hashlib
import shutil
import sys

sys.path.insert(0, str(Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace")))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex

root = Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace")
master = root / "docs" / "SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md"
append_src = root / "tmp" / "section308_append.md"
dropbox = Path(r"C:\Users\Javad Meighandi\Dropbox\Sedi\References\ChatGPT")
auth = root / "references" / "authoritative"
tmp = root / "tmp"

pre = master.read_bytes()
assert len(pre) == 3169704, len(pre)
assert sha256_hex(pre) == "79F1BDEA94CC1DA74F97D7A026CD01F01A29F6D4BD6C59B4EEF12163507FA6FC"

section = append_src.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
if not section.startswith("\r\n"):
    section = "\r\n" + section
if not section.endswith("\r\n"):
    section += "\r\n"
result = append_bytes(master, section.encode("utf-8"))
print("MASTER_APPEND", result)

handoff = """# SEDI Cursor Authoritative Handoff - v599

> Complete successor to v598. Section44 design Gate: DCR-01..05 APPROVED, I8 persistence DEFERRED, 100-year storage model PASS. No schema/migration/production I7/I8. ChatGPT v616 was cited but physically absent; physical ChatGPT tip was v612, successor is v613. Master Log §308. Do not rewrite §307.

```text
VERSION=v599
STATUS=CURRENT
PREDECESSOR=v598
RECORDED_AT_UTC=2026-08-13T18:20:00Z
REPO=javadmeighani-oss/sedi-backend
BRANCH=feature/section15/backend-continuity-foundation
AUTHORITY_HEAD_START=d824ba6749743dc027218d7f86a9bd21d31a094a
AUTHORITY_HEAD_TECHNICAL=04cf32204455fd942d4d9b4e301b88ca4284ffcd
MASTER_LOG=§308
CURSOR_HANDOFF=v599
CHATGPT_CONTINUITY=v613
CHATGPT_V616_PHYSICAL=ABSENT
GATE_OUTCOME=PASS
FULL_GATE_CLOSURE=PARTIAL
HARD_STOP=NO
AUTO_REMEDIATION_CYCLES=0/4
JAVAD_APPROVAL=GRANTED
PREFLIGHT=PASS
RULES_IN_FORCE_CHECK=PASS

I7_LIFELONG_MEMORY_DESIGN=PASS
DB_MEMORY_ALIGNMENT=PASS
DB_RAG_ALIGNMENT=PASS
LONG_TERM_STORAGE_MODEL=PASS
DCR01_COMPACT_PROFILE=APPROVED
DCR02_STORAGE_TIERS=APPROVED
DCR03_EXPORT=APPROVED
DCR04_FACT_STACKS=APPROVED
DCR05_EVENT_TIMELINE=APPROVED
I7_WEEK_SEMANTICS=APPROVED
I8_PERSISTENCE=DEFERRED
SCHEMA_CHANGE_IMPLEMENTED=NO
MIGRATION_IMPLEMENTED=NO
SCHEMA_CHANGE_REQUIRED_NEXT_GATE=YES
MIGRATION_REQUIRED_NEXT_GATE=YES
MIGRATION_ID_PROPOSAL=067_i7_lifelong_memory_foundation
MIGRATION_066=NO
I7_PRODUCTION_ENABLEMENT_READY=CONDITIONAL
I7_JOB_STATUS=REGISTERED_DORMANT
FIRST_I5_CALENDAR_FIRE=PENDING_FUTURE_OBSERVATION
CURRENT_WEEKLY_SOURCE_SCOPE=NHS_ONLY_BOUNDED
PRODUCTION_RAG=NO
ANN=NO
HNSW=NO
IVFFLAT=NO
ALEMBIC_HEAD=065
KNOW04_PUSH=31729388430 PASS
KNOW04_DISPATCH=31729388471 PASS
LOCAL_PYTEST=51_passed
PRODUCTION_BACKEND_IMAGE=012167413a11ff1676de7b8b19eaa9c029935cbe

MASTER_LOG_PRE_APPEND_SIZE=3169704
MASTER_LOG_PRE_APPEND_SHA256=79F1BDEA94CC1DA74F97D7A026CD01F01A29F6D4BD6C59B4EEF12163507FA6FC
MASTER_LOG_POST_APPEND_SIZE=__POST_SIZE__
MASTER_LOG_POST_APPEND_SHA256=__POST_SHA__
CURRENT_GATE_STRICT_APPEND_ONLY=PASS
HISTORY_REWRITE=NO
FORCE_PUSH=NO
NEXT_GATE=SEDI-V1 I7 MEMORY PERSISTENCE 067 / I7 ENABLEMENT / I5 CALENDAR-FIRE OBSERVATION (PROPOSED ONLY)
NEXT_GATE_AUTHORIZED=NO
```

## Permanent law (still in force)

- PRODUCTION_RAG=NO until separately authorized
- ANN_REVIEW_REQUIRED_BEFORE_SCALED_RAG=YES
- MIGRATION_066=FORBIDDEN_RESERVED
- Weekly unattended scope remains NHS-only
- I7 jobs remain dormant until separately authorized
- User memory vectors must never merge into the scientific/medical vector corpus
- HISTORY_IS_NOT_DIAGNOSIS
- Raw chat is not canonical LTM
- If ChatGPT v616 later appears, reconcile by SHA 2c91e119dfa80c3e258c107fc1461d842a4819c559584cafbc35f14d11a1da23; do not auto-revive over §308
"""

chatgpt = """# SEDI ChatGPT Independent Continuity - v613

> Complete successor to physical v612. Section44 design Gate PASS/PARTIAL. v616 was cited with expected SHA 2c91e119dfa80c3e258c107fc1461d842a4819c559584cafbc35f14d11a1da23 but was not physically present in Dropbox/workspace; it is not fabricated and is not in force. Master Log §308. Cursor handoff v599.

```text
VERSION=v613
STATUS=CURRENT
PREDECESSOR=v612
PREDECESSOR_CHAIN=v611->v612->v613
V616_PHYSICAL=ABSENT
V616_EXPECTED_SHA256=2c91e119dfa80c3e258c107fc1461d842a4819c559584cafbc35f14d11a1da23
RECORDED_AT_UTC=2026-08-13T18:20:00Z
REPO=javadmeighani-oss/sedi-backend
BRANCH=feature/section15/backend-continuity-foundation
AUTHORITY_HEAD_START=d824ba6749743dc027218d7f86a9bd21d31a094a
AUTHORITY_HEAD_TECHNICAL=04cf32204455fd942d4d9b4e301b88ca4284ffcd
MASTER_LOG=§308
CURSOR_HANDOFF=v599
CHATGPT_CONTINUITY=v613
JAVAD_APPROVAL=GRANTED
GATE_OUTCOME=PASS
FULL_GATE_CLOSURE=PARTIAL
HARD_STOP=NO
PREFLIGHT=PASS

DCR01_COMPACT_PROFILE=APPROVED
DCR02_STORAGE_TIERS=APPROVED
DCR03_EXPORT=APPROVED
DCR04_FACT_STACKS=APPROVED
DCR05_EVENT_TIMELINE=APPROVED
I7_WEEK_SEMANTICS=APPROVED
I8_PERSISTENCE=DEFERRED
LONG_TERM_STORAGE_MODEL=PASS
SCHEMA_CHANGE_IMPLEMENTED=NO
MIGRATION_066=NO
I7_JOB_STATUS=REGISTERED_DORMANT
I7_PRODUCTION_ENABLEMENT_READY=CONDITIONAL
FIRST_I5_CALENDAR_FIRE=PENDING_FUTURE_OBSERVATION
CURRENT_WEEKLY_SOURCE_SCOPE=NHS_ONLY_BOUNDED
PRODUCTION_RAG=NO
ANN=NO
ALEMBIC_HEAD=065

MASTER_LOG_PRE_APPEND_SIZE=3169704
MASTER_LOG_PRE_APPEND_SHA256=79F1BDEA94CC1DA74F97D7A026CD01F01A29F6D4BD6C59B4EEF12163507FA6FC
MASTER_LOG_POST_APPEND_SIZE=__POST_SIZE__
MASTER_LOG_POST_APPEND_SHA256=__POST_SHA__
CURRENT_GATE_STRICT_APPEND_ONLY=PASS
HISTORY_REWRITE=NO
FORCE_PUSH=NO

KNOW04_PUSH=31729388430 PASS
KNOW04_DISPATCH=31729388471 PASS
LOCAL_PYTEST=51_passed

NEXT_GATE=SEDI-V1 I7 MEMORY PERSISTENCE 067 / I7 ENABLEMENT / I5 CALENDAR-FIRE OBSERVATION (PROPOSED ONLY)
NEXT_GATE_AUTHORIZED=NO
```
"""

post_size = str(result["post_size"])
post_sha = str(result["post_sha256"])
handoff = handoff.replace("__POST_SIZE__", post_size).replace("__POST_SHA__", post_sha)
chatgpt = chatgpt.replace("__POST_SIZE__", post_size).replace("__POST_SHA__", post_sha)
auth.mkdir(parents=True, exist_ok=True)
h_path = auth / "Sedi_Cursor_Authoritative_Handoff_v599_FA.md"
c_path = auth / "Sedi_ChatGPT_Independent_Continuity_v613_FA.md"
h_path.write_text(handoff, encoding="utf-8", newline="\n")
c_path.write_text(chatgpt, encoding="utf-8", newline="\n")
shutil.copy2(h_path, tmp / h_path.name)
shutil.copy2(c_path, tmp / c_path.name)
dropbox.mkdir(parents=True, exist_ok=True)
shutil.copy2(c_path, dropbox / c_path.name)

def report(p: Path):
    b = p.read_bytes()
    print(p.name, "SIZE", len(b), "SHA", hashlib.sha256(b).hexdigest().upper())

report(master)
report(h_path)
report(c_path)
report(dropbox / c_path.name)
print("STRICT_APPEND", result["strict_append_only"])

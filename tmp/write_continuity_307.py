from pathlib import Path
import hashlib
import shutil
import sys

sys.path.insert(0, str(Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace")))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex

root = Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace")
master = root / "docs" / "SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md"
append_src = root / "tmp" / "section307_append.md"
dropbox = Path(r"C:\Users\Javad Meighandi\Dropbox\Sedi\References\ChatGPT")
auth = root / "references" / "authoritative"
tmp = root / "tmp"

pre = master.read_bytes()
assert len(pre) == 3160952, len(pre)
assert sha256_hex(pre) == "2D1F355662ACC0B755FDFB571FCF3C5BD0211FE26AEA78DD541035DFE8786EEB"

section = append_src.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
if not section.startswith("\r\n"):
    section = "\r\n" + section
if not section.endswith("\r\n"):
    section += "\r\n"
suffix = section.encode("utf-8")
result = append_bytes(master, suffix)
print("MASTER_APPEND", result)

handoff = """# SEDI Cursor Authoritative Handoff - v598

> Complete successor to v597. Section43 Master Gate executed: I7 lifelong memory foundation audited; 100-year HOT/WARM/ARCHIVE designed; I7 period-summary jobs registered dormant (flag off). No schema/migration. DCR-01..05 recorded. KNOW-04 PASS. Master Log §307. ChatGPT continuity v612. Do not rewrite §306.

```text
VERSION=v598
STATUS=CURRENT
PREDECESSOR=v597
RECORDED_AT_UTC=2026-08-13T17:50:00Z
REPO=javadmeighani-oss/sedi-backend
BRANCH=feature/section15/backend-continuity-foundation
AUTHORITY_HEAD_START=baa5c30beba7d93be7d796b708367dc76fd353c4
AUTHORITY_HEAD_TECHNICAL=3982978694a303b8a3c39974c301a036e15d7538
AUTHORITY_HEAD_FINAL=3982978694a303b8a3c39974c301a036e15d7538
TECHNICAL_IMAGE_COMMIT=012167413a11ff1676de7b8b19eaa9c029935cbe
PRODUCTION_BACKEND_IMAGE=012167413a11ff1676de7b8b19eaa9c029935cbe
PRODUCTION_BACKEND_DIGEST=sha256:8473e9e95678e4556803e389bcddd04c969ccb9ac87d8ec386e7a8c8c09e686b
PRODUCTION_IMAGE_OVERLAY=NO
PRODUCTION_RUNTIME_DEPENDS_ON_MUTABLE_OVERLAY=NO
MASTER_LOG=§307
CURSOR_HANDOFF=v598
CHATGPT_CONTINUITY=v612

GATE_OUTCOME=PASS
HARD_STOP=NO
FULL_GATE_CLOSURE=PARTIAL
AUTO_REMEDIATION_CYCLES=1/4
JAVAD_APPROVAL=GRANTED
PREFLIGHT=PASS
RULES_IN_FORCE_CHECK=PASS

I7_ARCHITECTURE_STATUS=FOUNDATION_PASS
MEMORY_ARCHITECTURE_STATUS=PARTIAL
DB_MEMORY_ALIGNMENT=PASS
RAG_ALIGNMENT=PASS
I7_JOB_STATUS=REGISTERED_DORMANT
SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED=OFF
PRODUCTION_I7_JOBS_ENABLED=NO
SCHEMA_CHANGE_IMPLEMENTED=NO
MIGRATION_IMPLEMENTED=NO
DCR_REQUIRED=YES
DCR_DOC=docs/architecture/section43/DESIGN_CHANGE_REQUEST.md
LONG_TERM_STORAGE_MODEL=PARTIAL

I7_CRON_DAILY=00:10 Asia/Tehran
I7_CRON_WEEKLY=Monday 00:20 Asia/Tehran
I7_CRON_MONTHLY=1st 00:30 Asia/Tehran
I7_CRON_YEARLY=Jan1 00:40 Asia/Tehran
I7_USER_WEEK=Tehran Monday ISO
I5_KNOWLEDGE_WEEK=Friday 00:00 UTC / 03:30 Asia/Tehran
CURRENT_WEEKLY_SOURCE_SCOPE=NHS_ONLY_BOUNDED
WEEKLY_MULTISOURCE_EXPANSION=NO
MANUAL_TICK_INVOKED=NO
NEXT_CALENDAR_FIRE=2026-08-14T03:30:00+03:30

I6_STATUS=GREEN
I7_STATUS=PARTIAL
I8_STATUS=PARTIAL
HISTORY_IS_NOT_DIAGNOSIS=YES
SUMMARY_IS_NOT_SOT=YES
CHAT_AUTO_FACT_PROMOTION=NO

PRODUCTION_RAG=NO
ANN_REQUIRED_NOW=NO
HNSW_CREATED=NO
IVFFLAT_CREATED=NO
MIGRATION_066=NO
ALEMBIC_HEAD=065

KNOW04_PUSH=31726923220 PASS
KNOW04_DISPATCH=31726964100 PASS
LOCAL_SECTION43_PYTEST=41_passed
FREEZE_TESTS=NOT_REDISPATCHED_PREEXISTING_OPENAPI_SNAPSHOT
IMAGE_BUILD=NO
PROD_I7_ENABLE=NO

MASTER_LOG_PRE_APPEND_SIZE=3160952
MASTER_LOG_PRE_APPEND_SHA256=2D1F355662ACC0B755FDFB571FCF3C5BD0211FE26AEA78DD541035DFE8786EEB
MASTER_LOG_POST_APPEND_SIZE=__POST_SIZE__
MASTER_LOG_POST_APPEND_SHA256=__POST_SHA__
CURRENT_GATE_STRICT_APPEND_ONLY=PASS
HISTORY_REWRITE=NO
FORCE_PUSH=NO

NEXT_GATE=SEDI-V1 I7 PRODUCTION ENABLEMENT DECISION / DCR-01..05 AUTHORIZATION / I8 DCR DECISION / OR GATE-4 (PROPOSED ONLY)
NEXT_GATE_AUTHORIZED=NO
```

## Permanent law (still in force)

- PRODUCTION_RAG=NO until separately authorized
- ANN_REVIEW_REQUIRED_BEFORE_SCALED_RAG=YES
- SEDI_V1_MINIMUM_SUPPORTED_USERS=5000
- Master Log append-only from current tip forward (byte-preserving)
- Weekly unattended scope remains NHS-only
- Do not convert every conversation sentence into permanent user truth
- I8 must fail-close without approved ELIGIBLE knowledge
- I8 full feature-index / meal-plan tables require DESIGN_CHANGE_REQUEST
- I7 jobs remain dormant until SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED is separately authorized
- User memory vectors must never merge into the scientific/medical vector corpus
- HISTORY_IS_NOT_DIAGNOSIS
- Physical 100-year HOT/WARM/ARCHIVE, compact profile, competing-stack merge, unified timeline, and durable export are DCRs
"""

chatgpt = """# SEDI ChatGPT Independent Continuity - v612

> Complete successor to v611. Section43 Master Gate: lifelong I7 foundation + 100-year design + dormant I7 jobs. No schema. DCR-01..05 recorded. KNOW-04 PASS. Master Log §307. Cursor handoff v598. Independent of Cursor session memory.

```text
VERSION=v612
STATUS=CURRENT
PREDECESSOR=v611
PREDECESSOR_CHAIN=v609->v610->v611->v612
RECORDED_AT_UTC=2026-08-13T17:50:00Z
REPO=javadmeighani-oss/sedi-backend
BRANCH=feature/section15/backend-continuity-foundation
AUTHORITY_HEAD_START=baa5c30beba7d93be7d796b708367dc76fd353c4
AUTHORITY_HEAD_TECHNICAL=3982978694a303b8a3c39974c301a036e15d7538
AUTHORITY_HEAD_FINAL=3982978694a303b8a3c39974c301a036e15d7538
TECHNICAL_IMAGE_COMMIT=012167413a11ff1676de7b8b19eaa9c029935cbe
PRODUCTION_BACKEND_IMAGE=012167413a11ff1676de7b8b19eaa9c029935cbe
PRODUCTION_BACKEND_DIGEST=sha256:8473e9e95678e4556803e389bcddd04c969ccb9ac87d8ec386e7a8c8c09e686b
PRODUCTION_IMAGE_OVERLAY=NO
MASTER_LOG=§307
CURSOR_HANDOFF=v598
CHATGPT_CONTINUITY=v612
JAVAD_APPROVAL=GRANTED

GATE_OUTCOME=PASS
FULL_GATE_CLOSURE=PARTIAL
HARD_STOP=NO
AUTO_REMEDIATION_CYCLES=1/4
PREFLIGHT=PASS

I7_ARCHITECTURE_STATUS=FOUNDATION_PASS
MEMORY_ARCHITECTURE_STATUS=PARTIAL
DB_MEMORY_ALIGNMENT=PASS
RAG_ALIGNMENT=PASS
I7_JOB_STATUS=REGISTERED_DORMANT
PRODUCTION_I7_JOBS_ENABLED=NO
LONG_TERM_STORAGE_MODEL=PARTIAL
SCHEMA_CHANGE_IMPLEMENTED=NO
MIGRATION_IMPLEMENTED=NO
DCR_REQUIRED=YES
DCR_DOC=docs/architecture/section43/DESIGN_CHANGE_REQUEST.md

CURRENT_TRIGGER_TYPE=CALENDAR_FIXED_CRON
CURRENT_SCHEDULE=Friday 03:30 Asia/Tehran
CURRENT_UTC_EQUIVALENT=Friday 00:00 UTC
NEXT_CALENDAR_FIRE=2026-08-14T03:30:00+03:30
CURRENT_WEEKLY_SOURCE_SCOPE=NHS_ONLY_BOUNDED
WEEKLY_MULTISOURCE_EXPANSION=NO
I7_USER_WEEK=Tehran Monday ISO
MANUAL_TICK_INVOKED=NO

I6_STATUS=GREEN
I7_STATUS=PARTIAL
I8_STATUS=PARTIAL
HISTORY_IS_NOT_DIAGNOSIS=YES
CHAT_AUTO_FACT_PROMOTION=NO

PRODUCTION_RAG=NO
ANN_REQUIRED_NOW=NO
HNSW_CREATED=NO
IVFFLAT_CREATED=NO
MIGRATION_066=NO
ALEMBIC_HEAD=065

MASTER_LOG_PRE_APPEND_SIZE=3160952
MASTER_LOG_PRE_APPEND_SHA256=2D1F355662ACC0B755FDFB571FCF3C5BD0211FE26AEA78DD541035DFE8786EEB
MASTER_LOG_POST_APPEND_SIZE=__POST_SIZE__
MASTER_LOG_POST_APPEND_SHA256=__POST_SHA__
CURRENT_GATE_STRICT_APPEND_ONLY=PASS
HISTORY_REWRITE=NO
FORCE_PUSH=NO

KNOW04_PUSH=31726923220 PASS
KNOW04_DISPATCH=31726964100 PASS
LOCAL_PYTEST=41_passed
IMAGE_BUILD=NO
PROD_I7_ENABLE=NO

NEXT_GATE=SEDI-V1 I7 PRODUCTION ENABLEMENT DECISION / DCR-01..05 AUTHORIZATION / I8 DCR DECISION / OR GATE-4 (PROPOSED ONLY)
NEXT_GATE_AUTHORIZED=NO
```
"""

post_size = str(result["post_size"])
post_sha = str(result["post_sha256"])
handoff = handoff.replace("__POST_SIZE__", post_size).replace("__POST_SHA__", post_sha)
chatgpt = chatgpt.replace("__POST_SIZE__", post_size).replace("__POST_SHA__", post_sha)

auth.mkdir(parents=True, exist_ok=True)
tmp.mkdir(parents=True, exist_ok=True)
h_path = auth / "Sedi_Cursor_Authoritative_Handoff_v598_FA.md"
c_path = auth / "Sedi_ChatGPT_Independent_Continuity_v612_FA.md"
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
print("DROPBOX_COPIED", str(dropbox / c_path.name))
print("STRICT_APPEND", result["strict_append_only"], result["prefix_preserved_byte_for_byte"])

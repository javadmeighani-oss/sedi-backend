from pathlib import Path
import hashlib
import shutil
import sys

sys.path.insert(0, str(Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace")))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex

root = Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace")
master = root / "docs" / "SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md"
append_src = root / "tmp" / "section309_append.md"
dropbox = Path(r"C:\Users\Javad Meighandi\Dropbox\Sedi\References\ChatGPT")
auth = root / "references" / "authoritative"
tmp = root / "tmp"

pre = master.read_bytes()
assert len(pre) == 3175889, len(pre)
assert sha256_hex(pre) == "6FE4CC7DF94EAE5DEE28F4558F4D596A8C09568A21803B5B8EAB7C3B8601BEA0"
section = append_src.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
if not section.startswith("\r\n"):
    section = "\r\n" + section
if not section.endswith("\r\n"):
    section += "\r\n"
result = append_bytes(master, section.encode("utf-8"))
print("MASTER_APPEND", result)

handoff = """# SEDI Cursor Authoritative Handoff - v600

> Complete successor to v599. Section45 implemented migration 067 (from 065; 066 reserved). Profile/export tables, retain_until, legacy write freeze, consent-safe reconciliation service. No production apply. No I7/I8/RAG activation. ChatGPT v616-v618 remain physically absent. Master Log §309. ChatGPT successor v614.

```text
VERSION=v600
STATUS=CURRENT
PREDECESSOR=v599
RECORDED_AT_UTC=2026-08-13T18:40:00Z
REPO=javadmeighani-oss/sedi-backend
BRANCH=feature/section15/backend-continuity-foundation
AUTHORITY_HEAD_START=5cfbb494aa6a9b9668dab2a5af5209b5a4911420
AUTHORITY_HEAD_TECHNICAL=4e1b527a077e029c60ddc9cda2d33e6e8bead115
MASTER_LOG=§309
CURSOR_HANDOFF=v600
CHATGPT_CONTINUITY=v614
CHATGPT_V618_PHYSICAL=ABSENT
GATE_OUTCOME=PASS
FULL_GATE_CLOSURE=PARTIAL
HARD_STOP=NO
AUTO_REMEDIATION_CYCLES=1/4
PREFLIGHT=PASS
RULES_IN_FORCE_CHECK=PASS

MIGRATION_067=PASS
DOWN_REVISION=065_i5_know04_connectors_change_intelligence
ALEMBIC_HEAD_REPO=067_i7_lifelong_memory_foundation
CREATE_066=NO
USER_LIFELONG_PROFILES=PASS
USER_MEMORY_EXPORT_JOBS=PASS
RETENTION_METADATA=PASS
LEGACY_FACT_WRITE_FREEZE=PASS
FACT_RECONCILIATION=PASS
FACT_RECONCILIATION_DATA_LOSS=NO
EVENT_TIMELINE=SERVICE_ONLY
I7_WEEK_SEMANTICS=PASS
PRODUCTION_MIGRATION_067=NOT_RUN
PRODUCTION_DEPLOY=NOT_RUN
SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED=OFF
I8_PERSISTENCE=NO
PRODUCTION_RAG=NO
ANN=NO
MIGRATION_066=NO
FIRST_I5_CALENDAR_FIRE=PENDING_FUTURE_OBSERVATION
KNOW04_PUSH=31731303832 PASS
KNOW04_DISPATCH=31731304859 PASS
LOCAL_PYTEST=46_passed

MASTER_LOG_PRE_APPEND_SIZE=3175889
MASTER_LOG_PRE_APPEND_SHA256=6FE4CC7DF94EAE5DEE28F4558F4D596A8C09568A21803B5B8EAB7C3B8601BEA0
MASTER_LOG_POST_APPEND_SIZE=__POST_SIZE__
MASTER_LOG_POST_APPEND_SHA256=__POST_SHA__
CURRENT_GATE_STRICT_APPEND_ONLY=PASS
HISTORY_REWRITE=NO
FORCE_PUSH=NO
NEXT_GATE=PRODUCTION 067 APPLY (BACKUP+RESTORE GREEN) / I7 ENABLEMENT / I5 CALENDAR-FIRE OBSERVATION (PROPOSED ONLY)
NEXT_GATE_AUTHORIZED=NO
```
"""

chatgpt = """# SEDI ChatGPT Independent Continuity - v614

> Complete successor to physical v613. Section45 067 implemented in repo. v616/v617/v618 remain physically absent (v618 expected SHA 23c04cc486f91d36003c47e617c967bbf5f04aaecd0f5e0e29c4672f09992634 unverified). Master Log §309. Cursor v600.

```text
VERSION=v614
STATUS=CURRENT
PREDECESSOR=v613
PREDECESSOR_CHAIN=v612->v613->v614
V616_PHYSICAL=ABSENT
V617_PHYSICAL=ABSENT
V618_PHYSICAL=ABSENT
V618_EXPECTED_SHA256=23c04cc486f91d36003c47e617c967bbf5f04aaecd0f5e0e29c4672f09992634
RECORDED_AT_UTC=2026-08-13T18:40:00Z
AUTHORITY_HEAD_TECHNICAL=4e1b527a077e029c60ddc9cda2d33e6e8bead115
MASTER_LOG=§309
CURSOR_HANDOFF=v600
CHATGPT_CONTINUITY=v614
GATE_OUTCOME=PASS
FULL_GATE_CLOSURE=PARTIAL
MIGRATION_067=PASS
DOWN_REVISION=065_i5_know04_connectors_change_intelligence
CREATE_066=NO
PRODUCTION_MIGRATION_067=NOT_RUN
SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED=OFF
I8_PERSISTENCE=NO
PRODUCTION_RAG=NO
FIRST_I5_CALENDAR_FIRE=PENDING_FUTURE_OBSERVATION
KNOW04_PUSH=31731303832 PASS
KNOW04_DISPATCH=31731304859 PASS
MASTER_LOG_PRE_APPEND_SIZE=3175889
MASTER_LOG_PRE_APPEND_SHA256=6FE4CC7DF94EAE5DEE28F4558F4D596A8C09568A21803B5B8EAB7C3B8601BEA0
MASTER_LOG_POST_APPEND_SIZE=__POST_SIZE__
MASTER_LOG_POST_APPEND_SHA256=__POST_SHA__
CURRENT_GATE_STRICT_APPEND_ONLY=PASS
NEXT_GATE_AUTHORIZED=NO
```
"""

post_size = str(result["post_size"])
post_sha = str(result["post_sha256"])
handoff = handoff.replace("__POST_SIZE__", post_size).replace("__POST_SHA__", post_sha)
chatgpt = chatgpt.replace("__POST_SIZE__", post_size).replace("__POST_SHA__", post_sha)
auth.mkdir(parents=True, exist_ok=True)
h_path = auth / "Sedi_Cursor_Authoritative_Handoff_v600_FA.md"
c_path = auth / "Sedi_ChatGPT_Independent_Continuity_v614_FA.md"
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

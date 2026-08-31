from pathlib import Path
import hashlib
import shutil
import sys

sys.path.insert(0, str(Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace")))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex

root = Path(r"D:\Rimiya Design Studio\Sedi\software\Sedi-v-1\workspace")
master = root / "docs" / "SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md"
append_src = root / "tmp" / "section311_append.md"
dropbox = Path(r"C:\Users\Javad Meighandi\Dropbox\Sedi\References\ChatGPT")
auth = root / "references" / "authoritative"
tmp = root / "tmp"

pre = master.read_bytes()
assert len(pre) == 3181594, len(pre)
assert sha256_hex(pre) == "1C0A2B848A7BFED7FD440F427FD0E277B76F48D5F3CA15AFC9ECD075BEFE7BA0"
section = append_src.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
if not section.startswith("\r\n"):
    section = "\r\n" + section
if not section.endswith("\r\n"):
    section += "\r\n"
result = append_bytes(master, section.encode("utf-8"))
print("MASTER_APPEND", result)

handoff = """# SEDI Cursor Authoritative Handoff - v602

> Complete successor to v601. Section47 aligned Production runtime to 067-capable image 7d0827a, proved live legacy freeze / two-user isolation / derived profile+export / retention / I7-off. I7 jobs remain OFF. ChatGPT v616-v622 remain physically absent; successor from physical v615 is v616. Master Log §311.

```text
VERSION=v602
STATUS=CURRENT
PREDECESSOR=v601
RECORDED_AT_UTC=2026-08-13T20:35:00Z
REPO=javadmeighani-oss/sedi-backend
BRANCH=feature/section15/backend-continuity-foundation
AUTHORITY_HEAD_START=cb5dbbd29380938501b351491fda91d71b78b192
AUTHORITY_HEAD_TECHNICAL=4e1b527a077e029c60ddc9cda2d33e6e8bead115
AUTHORITY_HEAD_RUNTIME=7d0827a8ecf8be2bdea853a6f12c7978979728a2
FINAL_HEAD=10230ae10660e1386a5d0f40f810c2f8418276db
MASTER_LOG=§311
CURSOR_HANDOFF=v602
CHATGPT_CONTINUITY=v616
CHATGPT_V622_PHYSICAL=ABSENT
GATE_OUTCOME=PASS
FULL_GATE_CLOSURE=PASS
HARD_STOP=NO
AUTO_REMEDIATION_CYCLES=4/4
PREFLIGHT=PASS
RULES_IN_FORCE_CHECK=PASS

RUNTIME_DEPLOY_GO_NO_GO=GO
PRODUCTION_RUNTIME_ALIGNMENT=PASS
PRODUCTION_ALEMBIC=067_i7_lifelong_memory_foundation
PRODUCTION_IMAGE_BEFORE=012167413a11ff1676de7b8b19eaa9c029935cbe
PRODUCTION_DIGEST_BEFORE=sha256:8473e9e95678e4556803e389bcddd04c969ccb9ac87d8ec386e7a8c8c09e686b
PRODUCTION_IMAGE_AFTER=7d0827a8ecf8be2bdea853a6f12c7978979728a2
PRODUCTION_DIGEST_AFTER=sha256:2cedf5108cc1105402534cf8ef388eddfac70e3b374175ed7508e51a208146b7
LEGACY_FACT_WRITE_FREEZE_LIVE=PASS
TWO_USER_RUNTIME_ISOLATION=PASS
PROFILE_REBUILD_RUNTIME=PASS
EXPORT_JOB_RUNTIME_FOUNDATION=PASS
RETENTION_RUNTIME_FOUNDATION=PASS
I7_PERIOD_SEMANTICS_RUNTIME=PASS
I7_OFF_FAIL_CLOSED_PROOF=PASS
I7_PRODUCTION_ENABLEMENT_READY=CONDITIONAL
SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED=OFF
I8_PERSISTENCE=NO
PRODUCTION_RAG=NO
NEW_MIGRATION=NO
FIRST_I5_CALENDAR_FIRE=PENDING_FUTURE_OBSERVATION
MANUAL_TICK_INVOKED=NO
RUNTIME_ROLLBACK_TRIGGERED=NO
SMOKE_FINAL_CI=31741047861 PASS
KNOW04_REMEDIATE_CI=31740018605 PASS

MASTER_LOG_PRE_APPEND_SIZE=3181594
MASTER_LOG_PRE_APPEND_SHA256=1C0A2B848A7BFED7FD440F427FD0E277B76F48D5F3CA15AFC9ECD075BEFE7BA0
MASTER_LOG_POST_APPEND_SIZE=__POST_SIZE__
MASTER_LOG_POST_APPEND_SHA256=__POST_SHA__
HISTORY_REWRITE=NO
FORCE_PUSH=NO
NEXT_GATE=SEDI-V1 SECTION48 I7 CONTROLLED PRODUCTION ENABLEMENT (PROPOSED ONLY)
NEXT_GATE_AUTHORIZED=NO
```
"""

chatgpt = """# SEDI ChatGPT Independent Continuity - v616

> Complete successor to physical v615. Section47 Production runtime aligned to 7d0827a with live freeze/isolation/derived-memory proofs. v616-v622 cited files remain physically absent (v622 expected SHA 3c1a96d139e0ba68149437abf94c63903a769c97e30d4c813967425a32ba7d9e unverified). This v616 is the physical successor, not a fabricated v622. Master Log §311. Cursor v602.

```text
VERSION=v616
STATUS=CURRENT
PREDECESSOR=v615
PREDECESSOR_CHAIN=v614->v615->v616
V616_CITED_PRIOR=ABSENT_THEN_THIS_SUCCESSOR
V617_PHYSICAL=ABSENT
V618_PHYSICAL=ABSENT
V620_PHYSICAL=ABSENT
V622_PHYSICAL=ABSENT
V622_EXPECTED_SHA256=3c1a96d139e0ba68149437abf94c63903a769c97e30d4c813967425a32ba7d9e
RECORDED_AT_UTC=2026-08-13T20:35:00Z
AUTHORITY_HEAD_TECHNICAL=4e1b527a077e029c60ddc9cda2d33e6e8bead115
AUTHORITY_HEAD_RUNTIME=7d0827a8ecf8be2bdea853a6f12c7978979728a2
MASTER_LOG=§311
CURSOR_HANDOFF=v602
CHATGPT_CONTINUITY=v616
GATE_OUTCOME=PASS
FULL_GATE_CLOSURE=PASS
PRODUCTION_RUNTIME_ALIGNMENT=PASS
PRODUCTION_ALEMBIC=067_i7_lifelong_memory_foundation
PRODUCTION_IMAGE_AFTER=7d0827a8ecf8be2bdea853a6f12c7978979728a2
PRODUCTION_DIGEST_AFTER=sha256:2cedf5108cc1105402534cf8ef388eddfac70e3b374175ed7508e51a208146b7
LEGACY_FACT_WRITE_FREEZE_LIVE=PASS
TWO_USER_RUNTIME_ISOLATION=PASS
I7_PRODUCTION_ENABLEMENT_READY=CONDITIONAL
SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED=OFF
I8_PERSISTENCE=NO
PRODUCTION_RAG=NO
NEW_MIGRATION=NO
FIRST_I5_CALENDAR_FIRE=PENDING_FUTURE_OBSERVATION
MANUAL_TICK_INVOKED=NO
SMOKE_FINAL_CI=31741047861 PASS
MASTER_LOG_PRE_APPEND_SIZE=3181594
MASTER_LOG_PRE_APPEND_SHA256=1C0A2B848A7BFED7FD440F427FD0E277B76F48D5F3CA15AFC9ECD075BEFE7BA0
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
handoff = handoff.replace("\r\n", "\n").replace("\n", "\r\n")
chatgpt = chatgpt.replace("\r\n", "\n").replace("\n", "\r\n")
auth.mkdir(parents=True, exist_ok=True)
h_path = auth / "Sedi_Cursor_Authoritative_Handoff_v602_FA.md"
c_path = auth / "Sedi_ChatGPT_Independent_Continuity_v616_FA.md"
h_path.write_bytes(handoff.encode("utf-8"))
c_path.write_bytes(chatgpt.encode("utf-8"))
shutil.copy2(h_path, tmp / h_path.name)
shutil.copy2(c_path, tmp / c_path.name)
dropbox.mkdir(parents=True, exist_ok=True)
shutil.copy2(c_path, dropbox / c_path.name)


def report(p: Path):
    b = p.read_bytes()
    print(p.name, "SIZE", len(b), "SHA", hashlib.sha256(b).hexdigest().upper(), "CRLF", b.count(b"\r\n"))


report(master)
report(h_path)
report(c_path)
report(dropbox / c_path.name)
print("STRICT_APPEND", result["strict_append_only"])
print("PREFIX_PRESERVED", result["prefix_preserved_byte_for_byte"])

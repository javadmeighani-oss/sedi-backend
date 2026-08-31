from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
pre_sha = sha256_hex(pre)
assert b"\xc2\xa7406" not in pre
assert b"\xc2\xa7405" in pre

sec = (
    "\r\n\r\n"
    "§406 - I10-B08 SELF LEGACY TO I10 PRODUCER ADAPTER (PRESENCE / ENGAGEMENT / MORNING)\r\n\r\n"
    "GATE=I10-B08\r\n"
    "PRODUCT_OWNER_APPROVAL=YES\r\n"
    "APPROVED_BY=JAVAD\r\n"
    "GATE_RESULT=PASS\r\n\r\n"
    f"PRE_406_SHA256={pre_sha}\r\n"
    "BASELINE_HEAD=867f88be0ca27798c51c925e72bbc8c4a6bcdde9\r\n"
    "B07R_CONTINUITY=§405 inventory + v697 preserved\r\n\r\n"
    "--------------------------------\r\n"
    "ADAPTED PRODUCERS\r\n"
    "--------------------------------\r\n\r\n"
    "MORNING=morning_notifications -> create_morning_brief -> I10 MORNING_CHECK_IN\r\n"
    "INACTIVITY=inactivity_notifications -> create_connection_ping -> I10 PRESENCE_REENGAGEMENT\r\n"
    "ENGAGEMENT=engagement_nudge -> create_engagement_nudge -> I10 ENGAGEMENT_NUDGE\r\n"
    "ADAPTER=backend/app/services/i10/self_producer_adapter.py\r\n"
    "INTAKE=enqueue_i10_notification()\r\n\r\n"
    "--------------------------------\r\n"
    "PARALLEL WRITE RETIREMENT\r\n"
    "--------------------------------\r\n\r\n"
    "MORNING_PARALLEL_WRITE_PATH=NO\r\n"
    "INACTIVITY_PARALLEL_WRITE_PATH=NO\r\n"
    "ENGAGEMENT_PARALLEL_WRITE_PATH=NO\r\n"
    "B08_DIRECT_NOTIFICATION_ORM_WRITES=0\r\n"
    "B08_DIRECT_FCM_CALLS=0\r\n\r\n"
    "--------------------------------\r\n"
    "BOUNDARIES\r\n"
    "--------------------------------\r\n\r\n"
    "SCHEMA_CHANGE=NO\r\n"
    "MIGRATION=NO\r\n"
    "INACTIVITY_MEDICAL_INFERENCE=NO\r\n"
    "MORNING_UNSUPPORTED_HEALTH_CLAIMS=NONE_FOUND\r\n"
    "DIRECT_RAG_TO_I10=NO\r\n"
    "POLICY_REDESIGN=NO\r\n"
    "PRODUCTION_ACTIVATION=NO\r\n\r\n"
    "--------------------------------\r\n"
    "TESTS / CI\r\n"
    "--------------------------------\r\n\r\n"
    "B08_TEST_COUNT=22\r\n"
    "CI_RUN_ID=33389103628\r\n"
    "CI_RESULT=PASS\r\n"
    "COMMIT_SHA=56fb1ead\r\n"
    "DOCS_COMMIT_SHA=PENDING\r\n"
    "FINAL_HEAD=56fb1ead\r\n\r\n"
    "HANDOFF_FILE=Sedi_Cursor_Authoritative_Handoff_v698_FA.md\r\n"
    "MASTER_LOG_TIP=§406\r\n"
    "CURSOR_HANDOFF_TIP=v698\r\n"
    "NEXT_PROPOSED_GATE=I10-B09_MEDICATION_ADHERENCE_I10\r\n"
)

append_bytes(path, sec.encode("utf-8"))
print(f"Appended §406 pre_sha={pre_sha}")

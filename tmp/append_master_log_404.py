from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
pre_sha = sha256_hex(pre)
assert b"\xc2\xa7404" not in pre

sec = (
    "\r\n\r\n"
    "§404 - I10-B06 CARE NETWORK RECIPIENT RESOLUTION + CAREGIVER DELIVERY WORKER\r\n\r\n"
    "GATE=I10-B06\r\n"
    "PRODUCT_OWNER_APPROVAL=YES\r\n"
    "APPROVED_BY=JAVAD\r\n"
    "GATE_RESULT=PASS\r\n\r\n"
    f"PRE_404_SHA256={pre_sha}\r\n"
    "BASELINE_HEAD=b6dc72faef23bc71961e1042719775434e6c3044\r\n"
    "B05_CONTINUITY=§403 identity/access/grant foundation reused\r\n\r\n"
    "--------------------------------\r\n"
    "DELIVERY ARCHITECTURE\r\n"
    "--------------------------------\r\n\r\n"
    "CHAIN=HealthSubject -> CaregiverNotificationIntent -> resolve_care_network_recipients -> delivery-time revalidation -> enqueue_i10_notification -> NotificationBuilder -> DeliveryService\r\n"
    "CAREGIVER_INTENT_REUSE=EXTEND (CaregiverNotificationIntent + migration 076)\r\n"
    "DELIVERY_TIME_REVALIDATION=YES (access/grant/prefs/PushDevice at worker execution)\r\n"
    "MULTI_CAREGIVER_FANOUT=YES (per-recipient intent + independent decisions)\r\n"
    "I10_CANONICAL_INTAKE=YES\r\n"
    "B06_DIRECT_NOTIFICATION_ORM_WRITES=0\r\n"
    "B06_DIRECT_FCM_CALLS=0\r\n"
    "WORKER_FEATURE_FLAG=SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED (default OFF)\r\n\r\n"
    "--------------------------------\r\n"
    "MIGRATION\r\n"
    "--------------------------------\r\n\r\n"
    "MIGRATION_FILE=076_i10_care_network_delivery_foundation.py\r\n"
    "MIGRATION_REVISION=076_i10_care_network_delivery_foundation\r\n"
    "MIGRATION_DOWN_REVISION=075_i10_care_network_identity_grants\r\n\r\n"
    "--------------------------------\r\n"
    "BOUNDARIES\r\n"
    "--------------------------------\r\n\r\n"
    "NOTIFICATION_PREFS=recipient channel toggles (not grant authority)\r\n"
    "PUSH_DEVICE=delivery readiness only (not authorization)\r\n"
    "PHONE_AS_PUSH_ENDPOINT=NO\r\n"
    "CARE_PRODUCERS=NO\r\n"
    "RAW_I9_TO_I10=NO\r\n"
    "DIRECT_RAG_TO_I10=NO\r\n"
    "FRONTEND_CHANGED=NO\r\n"
    "PRODUCTION_MIGRATION=NO\r\n\r\n"
    "--------------------------------\r\n"
    "TESTS / CI\r\n"
    "--------------------------------\r\n\r\n"
    "B06_TEST_COUNT=33\r\n"
    "CI_RUN_ID=PENDING\r\n"
    "CI_RESULT=PENDING\r\n\r\n"
    "HANDOFF_FILE=Sedi_Cursor_Authoritative_Handoff_v696_FA.md\r\n"
    "MASTER_LOG_TIP=§404\r\n"
    "CURSOR_HANDOFF_TIP=v696\r\n"
    "NEXT_PROPOSED_GATE=I10-B07_CARE_SEMANTIC_PRODUCERS_OR_FRONTEND\r\n"
)

result = append_bytes(path, sec.encode("utf-8"))
print(result)

# SEDI Cursor Authoritative Handoff - v809

A3 Smart Notifications G2 — I10 producer reachability bypass hardening. Append-only successor after v808 / Master Log §510. Do not rewrite v808.

```
VERSION=v809
STATUS=CURRENT
LOGICAL_PREDECESSOR=v808
CONTINUITY_BASELINE_CHATGPT=v806
MASTER_LOG=§511
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G2-I10-PRODUCER-REACHABILITY-BYPASS-HARDENING-01
GATE_RESULT=PASS
MODE=DELTA_ONLY
SCOPE=BACKEND_ONLY
APPROVED_BY=Javad
SCHEMA_MUTATION=NO
MIGRATION=NO
PRODUCTION_DEPLOY=NO
PRODUCTION_FLAG_ACTIVATION=NO
FRONTEND_CHANGED=NO
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Heads

```
BACKEND_BASELINE=a45840b20267996856a518d1c1225bc4e09f456c
BACKEND_FINAL=1bcdd9eaebcaa5ccca0c770dafe75af6639f1631
FRONTEND_UNCHANGED=397e47328b6c9109b60198a47ea998125b8bd53e
COMMIT=1bcdd9eaebcaa5ccca0c770dafe75af6639f1631
```

## Per-candidate outcomes

### create_insight_notification
- CLASS=ACTIVE_PRODUCT_RUNTIME
- BEFORE=NotificationBuilder.persist (bypass)
- AFTER=enqueue_self_scheduler_notification → enqueue_i10_notification
- SEMANTIC=ENGAGEMENT
- RESULT=HARDENED

### evaluate_health_data
- CLASS=ACTIVE_PRODUCT_RUNTIME
- BEFORE=NotificationBuilder.persist (bypass)
- AFTER=enqueue_self_scheduler_notification → enqueue_i10_notification
- SEMANTIC=DEVICE_STATUS (HEALTH_SENSITIVE); existing vitals heuristics preserved (no new thresholds)
- RESULT=HARDENED

### kc_notification (_maybe_send_kc_notification)
- CLASS=FLAG_GATED_PRODUCT_RUNTIME (notify=true on JWT knowledge next_question)
- BEFORE=direct ORM Notification insert + DeliveryService
- AFTER=enqueue_i10_notification; KC presentation type/actions/deeplink restored post-SEND
- SEMANTIC=ENGAGEMENT
- RESULT=HARDENED

### ml_care_bridge
- CLASS=FLAG_GATED_PRODUCT_RUNTIME (admin ops + SEDI_GATE5_ML_* flags, default OFF)
- BEFORE=direct ORM Notification when notif flag ON
- AFTER=enqueue_i10_notification; type restored to care_suggestion post-SEND
- SEMANTIC=CARE_ACTION
- RESULT=HARDENED

### admin_test_push
- UNCHANGED=YES (ADMIN_TEST_ONLY)

## Validation

- test_a3_g2_i10_producer_bypass_hardening.py → 10 passed
- Related regression: test_i10_b08_self_producer_adapter + test_a3_g1_inbox_projection_retention → 32 passed
- Alembic broad CI pin mismatch remains PREEXISTING_OUT_OF_G1

## Continuity

```
MASTER_LOG_TIP=§511
CURSOR_HANDOFF_TIP=v809
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v809_FA.md
ACTIVE_PRODUCT_BYPASSES_BEFORE=4
ACTIVE_PRODUCT_BYPASSES_AFTER=0
```

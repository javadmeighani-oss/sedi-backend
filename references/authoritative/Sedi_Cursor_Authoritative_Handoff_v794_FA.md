# SEDI Cursor Authoritative Handoff - v794

A3 Gadgets V1 BLE commissioning / persistent mobile-gateway contract — **FROZEN** (docs only).

Do not modify v793 / §500 history. This file supersedes v793 as CURRENT tip.

```
VERSION=v794
STATUS=CURRENT
LOGICAL_PREDECESSOR=v793
v793_MODIFIED=NO
SUCCESSOR_MODE=CREATE_ONLY
MASTER_LOG=§501
GATE=SEDI-V1-A3-GADGETS-V1-BLE-COMMISSIONING-CONTRACT-FREEZE-01
GATE_RESULT=PASS
MODE=DOCS_ONLY
V1_BLE_COMMISSIONING_CONTRACT_FROZEN=YES
CODE_MUTATION=NO
SCHEMA_MUTATION=NO
MIGRATION=NO
TEST_MUTATION=NO
WORKFLOW_MUTATION=NO
PROD_DEPLOY_PERFORMED=NO
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Heads

```
FRONTEND_HEAD=9b27b6b174e28cc56b425698179cf90e86e8dc4f
BACKEND_HEAD=b6b43b47763bf9147639880e1682004b6ada03d4
SOURCE_AUDIT=SEDI-V1-A3-GADGETS-MOBILE-GATEWAY-I9-I10-AUTHORITY-READONLY-AUDIT-01
SOURCE_AUDIT_RESULT=PASS
```

## Frozen V1 architecture

```
PATH=Physical Gadget → BLE → Mobile Gateway → HTTPS → I9 → I10 → Notification/FCM → Mobile
MOBILE=relay only
A3=presentation only
I9=device/physiological authority
I10=notification authority
V1_TRANSPORT=BLE→Mobile→Server
```

## Commissioning / setup code

```
SETUP_CODE_ROLE_RECORDED=YES
SEDI_SETUP_CLAIM_CODE=4-digit; not identity/BLE key/packet credential/HealthSubject
SETUP_CODE_ALONE_MUST_NOT_CLAIM_DEVICE=YES
CLAIM_REQUIRES=JWT + device_id + setup code + possession/credential + valid lifecycle
SETUP_CODE_NOT_IN_ROUTINE_PACKETS=YES
```

## SELF/OTHER + persistence + disconnect

```
SELF_OTHER_DEVICE_SEMANTICS_RECORDED=YES
SELF/OTHER=DEVICE classification on same Account (not person/HealthSubject/caregiver)
TARGET_FIELDS=device_category + user_label (schema Gate later)
PERSISTENT_AUTO_RECONNECT_RECORDED=YES
MANUAL_DISCONNECT_CONTRACT_RECORDED=YES
DISCONNECT!=DELETE|RELEASE|TRANSFER|DELETE_HISTORY
```

## I9/I10 boundaries + audit gaps

```
I9_I10_BOUNDARIES_RECORDED=YES
BLUETOOTH_GATEWAY_DATA_PLANE_AUTH=REQUIRED_IN_FUTURE_MUTATION
RAW_ECG=reuse canonical path; no second API
AUDIT_RESULT_RECORDED=YES
UPDATED_GATE_ORDER_RECORDED=YES (G1…G9 proposed only)
```

## Continuity

```
MASTER_LOG_TIP=§501
CURSOR_HANDOFF_TIP=v794
DROPBOX_SYNC=PASS
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v794_FA.md
CHATGPT_DROPBOX_UPDATED_BY_CURSOR=NO
PARALLEL_AUTHORITY_CREATED=NO
```

## Open items

```
- No mutation Gate authorized by this freeze
- Next product execution remains separate Javad-approved Gates (G1+)
```

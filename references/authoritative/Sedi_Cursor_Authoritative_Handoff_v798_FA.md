# SEDI Cursor Authoritative Handoff - v798

G3+G4+G5 integrated mobile data path checkpoint. Append-only successor of v797.

Do not modify v797.

```
VERSION=v798
STATUS=CURRENT
LOGICAL_PREDECESSOR=v797
v797_MODIFIED=NO
SUCCESSOR_MODE=CREATE_ONLY
MASTER_LOG=§505
GATE=SEDI-V1-A3-GADGETS-G3-G4-G5-INTEGRATED-MOBILE-DATA-PATH-01
GATE_RESULT=PASS
MODE=IMPLEMENT_VALIDATE_COMPOSITE
G1_CHECKPOINT_STATUS=CLOSED_PASS
G2_CHECKPOINT_STATUS=CLOSED_PASS
G3_CHECKPOINT_STATUS=CLOSED_PASS
G4_CHECKPOINT_STATUS=CLOSED_PASS
G5_CHECKPOINT_STATUS=CLOSED_PASS
GADGETS_PROGRAM_STATUS=IN_PROGRESS
G6_AUTHORIZED=NO
G7_AUTHORIZED=NO
NEXT_EXECUTION_GATE_AUTHORIZED=NO
CODE_MUTATION=YES
SCHEMA_MUTATION=NO
MIGRATION=NO
WORKFLOW_MUTATION=NO
DEPLOY=NO
PRODUCTION_MIGRATION=NO
MERGE=NO
RAW_ECG_MUTATION=NO
G7_NOTIFICATION_POLICY_MUTATION=NO
```

## Heads

```
FRONTEND_BASE_HEAD=4c08970c455e19c015d8f6d1052a88df6aae5c76
FRONTEND_PRODUCT_COMMITS=5d52d5ab;354420e0;4af9f51d;cdf59c5d
FRONTEND_FINAL_HEAD=cdf59c5d7e3be157c2d66c59fe6e1cd7880ffb2d
FRONTEND_REMOTE_HEAD=cdf59c5d7e3be157c2d66c59fe6e1cd7880ffb2d
BACKEND_BASE_GOVERNANCE_HEAD=07132ce669afc9182f718c9a9a3d4c0fb9fa9726
BACKEND_PRODUCT_COMMITS=399372f6;53f72366
BACKEND_FINAL_PRODUCT_HEAD=53f72366d8a3ac51e03d04437b2fd2a0f3d87d95
BACKEND_FINAL_GOVERNANCE_HEAD=4982cbe560209ef189b2cb949da517701f0f8d19
BACKEND_REMOTE_CANONICAL_HEAD=4982cbe560209ef189b2cb949da517701f0f8d19
BACKEND_G1_PRODUCT_HEAD=45d99be13174e868246bdf8b4b4b95d654776750
ALEMBIC_HEAD=084_device_category_setup_code_authority
REMOTE_BACKEND_BE_EXISTS=NO
BRANCH=feature/a3-authority-chat-stream-profile-foundation
```

## G3 BLE

- flutter_reactive_ble 5.4.1 (OPEN_FINDING vs gate 5.5.0 / Dart ^3.11)
- Android BLUETOOTH_SCAN/CONNECT + location maxSdkVersion=30
- lib/features/devices/ble/{sedi_ble_constants,sedi_ble_models,sedi_ble_transport}.dart
- Frozen UUIDs; scan by Primary Service; transport states disconnected/connecting/connected/reconnecting/outOfRange
- UTF-8 JSON protocol v1 DEVICE_INFO/DATA/STATUS; DEVICE_REPORTED stability preserved; no clinical inference
- Reconnect: in-process only; CompanionDeviceManager = OPEN_FINDING

## G4 Gateway → I9

- gateway_install_id via flutter_secure_storage
- Reuse /devices/{id}/gateway/pair|disconnect
- Canonical POST /device/packet only
- Backend require_active_bluetooth_gateway for transport=bluetooth
- Mapping omits user_id/health_subject_id; server subject attribution preserved

## G5 Outbox

- DurablePacketOutbox file-backed max 64; FIFO; enqueue before send; stable client_packet_id; ACCEPTED/DUPLICATE remove; recoverable retry; permanent auth fail-visible drop

## Electronics spec

- docs/Sedi_Gadget_BLE_and_Data_Interface_Spec_V1_FA.md

## Evidence

```
FRONTEND_CI=Frontend Android Debug APK run 34739266034 SUCCESS sha=cdf59c5d
BACKEND_LOCAL_G4=5 g4_bluetooth tests PASS
BACKEND_CI_RELATED=I9-I10 Device Reported Vital Status PG16 run 34738890703 SUCCESS sha=53f72366
```

## Continuity

```
MASTER_LOG_TIP=§505
CURSOR_HANDOFF_TIP=v798
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v798_FA.md
PARALLEL_AUTHORITY_CREATED=NO
CHATGPT_DROPBOX_UPDATED_BY_CURSOR=NO
```

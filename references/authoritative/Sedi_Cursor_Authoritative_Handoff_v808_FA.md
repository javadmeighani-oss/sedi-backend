# SEDI Cursor Authoritative Handoff - v808

A3 Smart Notifications G1 R1 — recovery + EN/FA/AR localization + final closure. Append-only successor after historical v807 (premature-but-evidence-bearing). Do not rewrite v805/v806/v807.

```
VERSION=v808
STATUS=CURRENT
LOGICAL_PREDECESSOR=v807
CONTINUITY_BASELINE_CHATGPT=v806
MASTER_LOG=§510
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G1-R1-RECOVERY-LOCALIZATION-AND-FINAL-CLOSURE-01
GATE_RESULT=PASS
G1_RESTARTED=NO
G1_FINAL_STATUS=CLOSED_PASS_WITH_DOCUMENTED_GADGET_PROVENANCE_SCHEMA_GAP
MODE=RECOVERY_LOCALIZATION_FINAL_CLOSURE
APPROVED_BY=Javad
SCHEMA_MUTATION=NO
MIGRATION=NO
PRODUCTION_DEPLOY=NO
PRODUCTION_FLAG_ACTIVATION=NO
RETENTION_AUTOMATIC_ACTIVATION=NO
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Heads

```
BACKEND_START=ee4192ad4b98e8fa862f805b0ec9dd7edbb9ffef
BACKEND_PRODUCT=61c64a2e
BACKEND_DOCS_HISTORICAL_V807=ee4192ad
FRONTEND_START=c3cefb46f29e22dd3613a7e497e24724066ee34c
FRONTEND_LOCALIZATION=397e47328b6c9109b60198a47ea998125b8bd53e
FRONTEND_FINAL=397e47328b6c9109b60198a47ea998125b8bd53e
BACKEND_BRANCH=feature/a3-authority-chat-stream-profile-foundation
FRONTEND_BRANCH=feature/a3-authority-chat-stream-profile-foundation
```

## Recovery performed

- Restored Master Log dirty worktree to HEAD (removed 5× interrupted FE-CI addenda); then appended single §510
- Restored dirty v807 worktree to committed HEAD; committed v807 preserved as historical evidence
- Nested `workspace/frontend` mirror cleaned after SHA256 equality to canonical FE tip; not committed into sedi-backend

## Preserved G1 product behavior

- Sent-only Inbox (`is_sent` + `sent_at` + 180d); order `sent_at DESC,id DESC`
- Cursor pagination default 20 / max 50; unread uses same projection
- Retention foundation 180/365; automatic activation OFF
- Canonical `sedi_alarm` + Android channel v2 / FCM+APNs sound contract
- A3 Gate3/Gate4 → canonical NotificationInboxPage; pagination/refresh/dedupe/interactions

## Localization (R1)

- `NotificationInboxL10n` EN/FA/AR for frontend-owned Inbox UI only
- Directionality: FA/AR RTL, EN LTR
- Backend notification title/body content not translated
- No clinical / Gadget OTHER inference from text

## Validation

- Backend targeted: 30 passed (`test_a3_g1_inbox_projection_retention` + gate4 channel + inbox gate4)
- Frontend CI: run 34811029026 SUCCESS @ 397e4732
- Sound SHA256=6d15a0e60302bb10610f54fed736132d49a108fa5a20ea3a5a0d91fe9e9d2e3b
- Alembic broad workflow pin 080 vs tip 084 = PREEXISTING_OUT_OF_G1

## Deferred

- Gadget provenance schema/API (PARTIAL)
- dislike-reason
- create_insight_notification / evaluate_health_data / kc_notification / ml_care_bridge reachability hardening
- retention production activation

## Continuity

```
MASTER_LOG_TIP=§510
CURSOR_HANDOFF_TIP=v808
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v808_FA.md
HISTORICAL_V807_PRESERVED=YES
```

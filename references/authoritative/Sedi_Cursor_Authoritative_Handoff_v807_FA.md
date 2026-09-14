# SEDI Cursor Authoritative Handoff - v807

A3 Smart Notifications G1 — inbox projection + retention foundation + sound + A3 inbox wire. Append-only successor after v805 (G0 closure) / ChatGPT v806 authority. Do not rewrite v805/v806.

```
VERSION=v807
STATUS=CURRENT
LOGICAL_PREDECESSOR=v805
CONTINUITY_BASELINE_CHATGPT=v806
MASTER_LOG=§509
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G1-INBOX-PROJECTION-RETENTION-SOUND-POLICY-01
GATE_RESULT=PASS
MODE=IMPLEMENT_VALIDATE
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
BACKEND_BASELINE=7610c9da67c83e7d620b180a57647c37e8e88e83
FRONTEND_BASELINE=2ff9c72d1e62e4582f29514e7edfb00a9e7e5b0a
BACKEND_BRANCH=feature/a3-authority-chat-stream-profile-foundation
FRONTEND_BRANCH=feature/a3-authority-chat-stream-profile-foundation
```

## Implemented behavior

### A3 sent-history projection
- GET /notifications and GET /notifications/unread: `is_sent=true` AND `sent_at IS NOT NULL` AND within 180-day window
- Order: `sent_at DESC`, `id DESC`
- Cursor pagination: default 20, max 50, opaque base64url cursor
- unread_count uses same projection (queued/failed excluded)

### Gadget provenance
- `GADGET_PROVENANCE_CONTRACT=PARTIAL`
- Gap: Notification row has no first-class gadget_id / display_name / device_category fields
- Response exposes I10 `health_subject_id` / `recipient_kind` / `semantic_family` when persisted
- `gadget_provenance=null` (do not invent); OTHER≠HealthSubject locked

### Retention foundation
- Policy 180 content / 365 I10 decisions
- FK-safe prune implemented (`retention.py`) with dry_run default and env/force gate
- Automatic production activation OFF (`SEDI_NOTIFICATION_RETENTION_PRUNE_ENABLED` unset)

### Sound
- Original Sedi synthesis `sedi_alarm.wav`
- SHA256=6d15a0e60302bb10610f54fed736132d49a108fa5a20ea3a5a0d91fe9e9d2e3b
- Android raw + iOS Runner bundle + Xcode Resources
- Versioned Android channels `morning_v2` / `engagement_v2` / `health_alert_v2`
- FCM android.notification.channel_id/sound + APNs aps.sound
- Runtime download PROHIBITED

### Frontend
- Gate3/Gate4 placeholders → canonical NotificationsInboxPage
- Cursor pagination + sent-history empty state
- No duplicate inbox

## Tests
- Backend targeted: test_a3_g1_inbox_projection_retention.py + channel routing + inbox gate4 → 30 passed
- Frontend local flutter blocked (pub.dev auth on this host); FE CI to validate wiring test

## Continuity

```
MASTER_LOG_TIP=§509
CURSOR_HANDOFF_TIP=v807
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v807_FA.md
```

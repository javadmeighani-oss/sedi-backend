# SEDI Cursor Authoritative Handoff - v822

A3 Smart Notifications FE1 — icon / unread badge / canonical Inbox final closure. Append-only successor after v821 / Master Log §523. Frontend FAST_DELTA_ONLY. No backend/schema/deploy.

```
VERSION=v822
STATUS=CURRENT
LOGICAL_PREDECESSOR=v821
CONTINUITY_BASELINE_CHATGPT=v816
MASTER_LOG=§524
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-FE1-ICON-BADGE-INBOX-FINAL-CLOSURE-01
GATE_RESULT=PASS
MODE=FAST_DELTA_ONLY
APPROVED_BY=Javad
BACKEND_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CREATED=NO
DEPLOYED=NO
FRONTEND_CLINICAL_INFERENCE=NO
DUPLICATE_NOTIFICATION_AUTHORITY=NO
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Heads

```
FRONTEND_BASELINE=397e47328b6c9109b60198a47ea998125b8bd53e
FRONTEND_FINAL=88f4b1015ab8196f8f19b2b2556da47d8ea2b5e6
FRONTEND_BRANCH=feature/a3-authority-chat-stream-profile-foundation
FRONTEND_COMMITS=664e3b8f,88f4b101
BACKEND_UNCHANGED=214ecf28bb37b89106a31ea02d3186b4f47d861f
```

## Product closure

### ICON
- Intended A3 entry: Gate3MainIconRow Smart Notifications (`Icons.notifications_none_outlined`)
- Tap → canonical `NotificationInboxPage`
- Visible/tappable; Sedi Gate3 visual conventions preserved
- Legacy ChatPage header icon left as secondary/onboarding-reachable path (not A3 home authority); wrappers still alias to canonical Inbox

### BADGE
- Gate3 badge source = `GET /notifications/unread` → `unread_count` (sent-history only)
- `NotificationsService.fetchUnreadCount` + `NotificationService.parseUnreadCount` prefer `unread_count` over page `count`
- Zero/null → no badge (no misleading unread)
- Refresh: init, app resume, Inbox return, InboxRefreshBus after read/feedback/push

### ROUTING / INBOX
- G1 preserved: sent-only; `sent_at DESC,id DESC`; pagination 20/max 50; refresh+dedupe; EN/FA/AR RTL/LTR; `sedi_alarm` unchanged

### INTERACTIONS
- READ = `POST .../mark-read` wired + optimistic
- CONFIRM/ACK = mark-read as Inbox acknowledge; Gate4 `ACK_THANKS` not a separate Inbox default action
- CHAT = Inbox `open_chat` feedback + `AppGateRouter.goToHeart(fromNotification,notificationId)` (preserves existing identity path)
- DISLIKE = feedback reaction dislike wired
- DISLIKE_REASON = optional `too_frequent|irrelevant|unclear` sent when chosen (backend accepts `reason`)

### GADGET PROVENANCE
- Backend `_notification_to_response` still sets `gadget_provenance=None` (no schema)
- Frontend does not infer SELF/OTHER/HealthSubject from title/body
- Safe generic presentation retained

## Validation

```
FRONTEND_CI_RUN=34881716090
FRONTEND_CI=SUCCESS
ANALYZE=NO_ERRORS
TARGETED_TESTS=a3_fe1_icon_badge_inbox_test + a3_g1_inbox_wiring_test + notification_sync_and_badge_test
```

## Remaining / next (not authorized)

- Backend gadget provenance schema/API still deferred
- Gate4 ACK_THANKS as distinct Inbox CTA not required by V1 default actions
- Numeric/confirmation policy remain PROPOSED_NOT_APPROVED (v821 / §523)
- No deploy

## Continuity

```
MASTER_LOG_TIP=§524
CURSOR_HANDOFF_TIP=v822
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v822_FA.md
```

# SEDI Cursor Authoritative Handoff - v800

A3 Smart Notifications G0 — storage + sound architecture audit (docs-only). Append-only successor of v799. Do not modify v799.

```
VERSION=v800
STATUS=CURRENT
LOGICAL_PREDECESSOR=v799
v799_MODIFIED=NO
SUCCESSOR_MODE=CREATE_ONLY
MASTER_LOG=§507
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G0-STORAGE-SOUND-ARCHITECTURE-AUDIT-01
GATE_RESULT=PASS
MODE=READ_ONLY_PRODUCT_CODE_AUDIT_DOCS_ONLY_GOVERNANCE
APPROVED_BY=Javad (Gate authorization)
NO_RUNTIME_MUTATION=YES
SCHEMA_MUTATION=NO
MIGRATION=NO
SOUND_ASSET_ADDED=NO
DEPENDENCY_CHANGED=NO
DEPLOY=NO
MERGE=NO
COMMIT_PERFORMED=NO
PUSH_PERFORMED=NO
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Baseline reconcile

```
BACKEND_REPO=javadmeighani-oss/sedi-backend
BACKEND_BRANCH_EXPECTED=feature/a3-authority-chat-stream-profile-foundation
BACKEND_BRANCH_LOCAL=feature/a3-authority-chat-stream-profile-foundation-be
BACKEND_TRACKS=origin/feature/a3-authority-chat-stream-profile-foundation
BACKEND_HEAD_LIVE=7610c9da67c83e7d620b180a57647c37e8e88e83
BACKEND_HEAD_GATE_TEXT=7610c9dcd450a57745688003d3848217764497c0
BACKEND_EXPECTED_OBJECT_EXISTS=NO
FRONTEND_REPO=javadmeighani-oss/sedi-frontend
FRONTEND_BRANCH=feature/a3-authority-chat-stream-profile-foundation
FRONTEND_HEAD_LIVE=2ff9c72d1e62e4582f29514e7edfb00a9e7e5b0a
FRONTEND_HEAD_GATE_TEXT=2ff9c721e1bcfedb294340449a5323396d3ab83f
FRONTEND_EXPECTED_OBJECT_EXISTS=NO
BASELINE_GUARD=PASS_RECONCILED
BASELINE_NOTE=Gate full SHAs are non-existent objects; live tips share 7-char prefixes (7610c9d / 2ff9c72) on expected feature branches. Treated as transcription mismatch, not unrelated drift.
```

## Files inspected (bounded)

### Backend
- `backend/app/models.py` (Notification, PushDevice, NotificationFeedback, InteractionEvent, NotificationPrefs, NotificationGuardState, I10NotificationDecision, HealthSubjectNotificationGrant, CaregiverNotificationIntent)
- `backend/app/routers/notifications.py`
- `backend/app/schemas/notification.py`
- `backend/app/services/notification_engine.py`
- `backend/app/services/notifications/delivery_service.py`
- `backend/app/services/i10/intake.py`
- `backend/app/services/i10/interaction_recorder.py`
- `backend/app/services/i10/*_adapter*.py`, `daily_wellness_digest.py`, `caregiver_delivery_worker.py`, `device_reported_vital_status_producer.py`, `self_producer_adapter.py`
- `backend/app/services/gate4/*` (policy, prefs, interaction_event_service, user_chat_reminder, inbox_metadata)
- `backend/app/services/gate5/ml_care_bridge.py`
- `backend/app/services/section10/caregiver_notification_intent_service.py`
- `backend/app/routers/{health,ai_core,medical,data,device,knowledge,ops}.py`
- `backend/app/core/scheduler.py`
- `backend/alembic/versions/{001,009,011,037,038,039,046,058,074}*`
- `backend/tests/test_notification_inbox_gate4_v1.py`, `test_i10_b19_legacy_retirement.py`

### Frontend
- `frontend/lib/core/notifications/local_notifications_service.dart`
- `frontend/lib/services/notifications/notifications_service.dart`
- `frontend/lib/features/notifications/presentation/pages/notification_inbox_page.dart`
- `frontend/lib/features/notification/logic/notification_sync.dart`
- `frontend/android/app/src/main/res/raw/readme_sound.txt`
- iOS tree search for `sedi_alarm` / `.wav` / `.caf` (none found)

## Stage 1 — Notification storage architecture (CONFIRMED)

### Canonical persistence
- **Canonical table:** `notifications` (SQLAlchemy `Notification`)
- **Serves both outbox AND inbox/history:** YES (same row: `is_sent=false`/`status=queued` for outbox; all rows readable via GET inbox)

### `notifications` fields (status)

| Area | Fields | Write status |
|------|--------|--------------|
| Identity / recipient | `id`, `user_id` (FK users CASCADE) | CONFIRMED written |
| HealthSubject | `health_subject_id` (FK SET NULL) | CONFIRMED on I10 path; nullable legacy |
| Semantic / category / risk | `type`, `category`, `semantic_family`, `recipient_kind`, `privacy_class`, `risk_level`, `priority`, `channel` | CONFIRMED on persist (I10 fills subject/semantic/recipient/privacy) |
| Title/body/language | `title`, `body`, `language` | CONFIRMED |
| Timestamps | `created_at` | CONFIRMED |
| | `scheduled_for` | CONFIRMED (defer/schedule) |
| | `sent_at` | CONFIRMED on successful delivery |
| | `queued_at`, `delivered_at`, `opened_at`, `decision_at` | UNUSED (schema/model only; no app writers found) |
| Read | `is_read` | CONFIRMED (mark-read) |
| Delivery | `is_sent`, `status` (`queued`/`sent`/`failed`), `provider`, `provider_message_id`, `last_error`, `ttl_seconds` | CONFIRMED written by persist/delivery (`ttl_seconds` set on admin test; FCM TTL ≠ DB retention) |
| Dedupe | `dedupe_key` + unique index `ux_notifications_dedupe_key` (alembic 009) | CONFIRMED |
| Actions/deeplink | `actions_json`, `deeplink_url` | CONFIRMED |
| I10 linkage | `i10_policy_decision_id` (FK SET NULL) | CONFIRMED on I10 path; NULL on bypass writers |
| Care episode | `care_episode_id` | PARTIAL (column present; not core A3 inbox) |
| Trace | `source_type`, `source_id`, `context_json`, `template_key` | CONFIRMED on Gate4/I10 persist |

### Related tables
- `notification_feedback` — CONFIRMED (feedback actions; CASCADE from notification/user)
- `interaction_events` — CONFIRMED (read/like/dislike/open_chat; partial unique on notif chat_message)
- `push_devices` — CONFIRMED (FCM tokens)
- `notification_prefs` — CONFIRMED (toggles/quiet hours/daily time)
- `notification_guard_state` — CONFIRMED (cooldown/last_sent)
- `i10_notification_decisions` — CONFIRMED ledger; bidirectional link via `notification_id` ↔ `notifications.i10_policy_decision_id`
- `health_subject_notification_grants` — CONFIRMED recipient/scope authorization
- `caregiver_notification_intents` — CONFIRMED separate intent outbox (often suppressed by flags); not A3 inbox SoT

### Lifecycle (CONFIRMED)
producer → `enqueue_i10_notification` (authz + canonical policy + decision ledger) → `NotificationBuilder.persist` (`status=queued`, `is_sent=false`) → Gate4 prefs/policy at enqueue → scheduler/`DeliveryService.deliver_pending` → FCM/APNs or `db_only` → `is_sent/sent_at/status` → A3 GET inbox → mark-read/feedback → `i10.interaction_recorder` → `notification_feedback` + `interaction_events`

## Stage 2 — A3 Inbox API contract (CONFIRMED; no API mutation)

```
GET /notifications: ALL rows for user_id (queued future, unsent, failed, sent). Order created_at DESC. No limit/pagination. unread_count = is_read==false (includes unsent).
GET /notifications/unread: is_read==false only; limit default 20 (1..100); order created_at DESC; total/unread_count before limit.
POST .../mark-read|read: is_read=true + InteractionEvent READ (first transition).
POST .../feedback: NotificationFeedback + InteractionEvent via I10 recorder.
Response projection: id/user_id/type/title/body/priority/is_read/is_sent/scheduled_for/created_at + Gate4 category/risk/channel/metadata. Does NOT expose sent_at, status, health_subject_id, i10_policy_decision_id.
```

Frontend:
- `NotificationsService` / `NotificationInboxPage` = server API only for inbox list (CONFIRMED).
- `NotificationSync` SharedPreferences = seen-ID rolling window for local OS toast only — **not** history SoT (CONFIRMED).
- OS tray = presentation only (CONFIRMED).

### PROPOSED_NOT_IMPLEMENTED (requires Javad approval)
A3 history projection candidate:
- filter `is_sent=true` AND `sent_at IS NOT NULL`
- order `sent_at DESC`
- pagination (page size OPEN)
- failed rows: separate status surface or excluded (OPEN)
- expose `health_subject_id` / `recipient_kind` / `semantic_family` / `status` / `sent_at` as explicit attribution (OPEN exact fields)

## Stage 3 — Retention

```
CURRENT_RETENTION_POLICY=NONE_CONFIRMED
NOTIFICATION_DB_RETENTION_POLICY=OPEN_DECISION
FCM_ttl_seconds ≠ DB history retention
User delete: notifications CASCADE with users.id
Managed-person unlink: does not auto-delete notifications (health_subject_id SET NULL)
```

Bounded options (NOT approved):
1. **Pilot/simple:** retain 90 days then delete — low storage; weak caregiver history.
2. **Balanced (recommended, not approved):** retain 180 days active inbox; archive metadata-only beyond — product usable + privacy bounded.
3. **Longer audit:** retain 365+ days — stronger care audit; higher privacy/storage burden.

## Stage 4 — Sound architecture

```
ANDROID_SOUND_REFERENCE=RawResourceAndroidNotificationSound('sedi_alarm') — CONFIRMED
ANDROID_PATH_EXPECTED=android/app/src/main/res/raw/sedi_alarm.wav
ANDROID_SOUND_ASSET_PRESENT=NO (only readme_sound.txt)
IOS_SOUND_REFERENCE=DarwinNotificationDetails.sound='sedi_alarm.wav' — CONFIRMED in Dart
IOS_BUNDLE_ASSET_PRESENT=NO (no wav/caf in ios tree; no Xcode resource reference found)
CHANNELS=morning (no sound/vib), engagement (sound, no vib), health_alert (sound+vib+sedi_alarm), legacy sedi_alerts (sound+vib+sedi_alarm)
ANDROID_CHANNEL_IMMUTABILITY=changing sound later requires new channel id/version (OS caches channel settings)
REMOTE_PUSH_DEPENDS_ON_BUNDLED_SOUND=YES for custom signature; missing asset → OS default fallback
BACKEND_AUDIO_STORAGE=NONE_NECESSARY (semantic/channel only)
RUNTIME_SOUND_DOWNLOAD_REQUIRED=NO (prohibited for V1 canonical)
```

OPEN (not self-approved): one V1 Sedi sound vs SEDI_DEFAULT + SEDI_HEALTH_ALERT; final file/license.

## Stage 5 — Authority map

```
Producers (chat reminder / scheduler morning / digest / medication / gadget DRVS / I9 / coaching / caregiver workers / …)
  → I10 adapter + enqueue_i10_notification
  → HealthSubject + recipient scope + grants/consent
  → i10_notification_decisions (canonical policy)
  → notifications persist (PostgreSQL SoT)
  → Gate4 delivery prefs/resolver + DeliveryService
  → FCM/APNs carrier
  → bundled mobile sedi_alarm (when present)
  → OS presentation
  → A3 Smart Notifications inbox (server-backed)
  → interaction_recorder → feedback/events → domain handlers where authorized
```

Responsibility classification:
- **I10** = notification intelligence authority
- **PostgreSQL** = notification history SoT
- **Gate4** = lower delivery/prefs/resolver under I10 (LOWER_LEVEL_REUSED)
- **FCM/APNs** = carrier
- **Mobile OS** = presentation
- **A3** = inbox + user interaction
- **Frontend** = presentation only; no clinical authority

OTHER / managed subject / caregiver: attribution remains via `health_subject_id` + `recipient_kind` + grants — frontend must not guess (CONFIRMED design; inbox API currently under-exposes these fields).

## Stage 6 — Duplicate / legacy / bypass inventory

| Component | Class |
|-----------|--------|
| `enqueue_i10_notification` + I10 adapters/producers | CANONICAL |
| `NotificationBuilder.persist` when called from I10 | LOWER_LEVEL_REUSED |
| Gate4 policy/prefs/delivery/FCM adapter | LOWER_LEVEL_REUSED |
| A3 `NotificationInboxPage` / `NotificationsService` | CANONICAL (presentation) |
| `admin_test_push` | ADMIN_TEST_ONLY |
| `create_insight_notification` → direct persist | LEGACY_BUT_LIVE (ai_core/medical/data/device + save_notification helper) |
| `evaluate_health_data` → direct persist | LEGACY_BUT_LIVE (health router) |
| `knowledge._maybe_send_kc_notification` direct ORM | LEGACY_BUT_LIVE |
| `ml_care_bridge` direct ORM (flag-gated) | LEGACY_BUT_LIVE |
| `NotificationSync` pull→local toast | LEGACY_BUT_LIVE (not history SoT) |
| `save_notification` (scheduler helper) | DEAD_CANDIDATE (no callers) |
| `build_notification_from_template` | DEAD_CANDIDATE (no callers) |
| `create_condition_reminder` | DEAD_CANDIDATE (no callers) |
| section10 caregiver intents | COMPATIBILITY_WRAPPER / parallel intent table (flags often suppress) |

```
PROVEN_I10_BYPASSES=5 (create_insight_notification; evaluate_health_data; kc_notification; ml_care_bridge; admin_test_push[admin])
LEGACY_LIVE_PATHS=5 (insight; evaluate_health; kc; ml_bridge; NotificationSync)
DEAD_CANDIDATES=3 (save_notification; build_notification_from_template; create_condition_reminder)
```
No remediation in G0.

## Approved decisions recorded (LOCKED)

1. Do not create a second notification system.
2. I10 remains Smart Notification decision authority.
3. PostgreSQL/backend remains canonical Notification history.
4. Gate4 remains reusable lower-level delivery/prefs/resolver under I10.
5. A3 Smart Notifications is a server-backed interactive Inbox.
6. Frontend does not invent clinical interpretation/thresholds.
7. HealthSubject/recipient identity must stay explicit end-to-end.
8. Sedi notification audio binary belongs in Android/iOS app bundle.
9. Backend selects semantic/channel; does not store/stream signature audio per push.
10. Runtime sound downloading on notification arrival is prohibited for canonical V1.
11. Actual sound file is not downloaded/added during G0.
12. No runtime/code/schema mutation in G0.

## OPEN_DECISION (must not self-approve)

- Notification DB retention duration
- Archive vs delete policy
- Exact A3 sent-history projection
- Pagination contract / page size
- Whether failed notifications are user-visible
- One vs two Sedi signature sounds
- Final audio file/source/license
- Production I10 bypass remediation
- Any schema/API change

## Confirmed gaps

1. A3 inbox currently shows unsent/queued/failed (not sent-only history).
2. No DB retention job/policy for `notifications`.
3. Missing `sedi_alarm` binary on Android and iOS (code references only).
4. Inbox API under-exposes subject/attribution/sent_at/status.
5. Proven non-I10 writers still reachable in product/admin paths.

## Proposed next Gate

```
NEXT_RECOMMENDED_GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G1-INBOX-PROJECTION-RETENTION-SOUND-POLICY-01
NEXT_GATE_MODE=JAVAD_DECISION_THEN_BOUNDED_DOCS_OR_IMPLEMENTATION
NEXT_GATE_AUTHORIZED=NO
```

## Validation / evidence commands

```
git -C workspace rev-parse HEAD
git -C workspace rev-parse origin/feature/a3-authority-chat-stream-profile-foundation
git -C workspace fetch frontend feature/a3-authority-chat-stream-profile-foundation
git -C workspace rev-parse frontend/feature/a3-authority-chat-stream-profile-foundation
git cat-file -t <gate-expected-SHAs>  # both missing
git ls-tree -r --name-only frontend/... | findstr sedi_alarm
git status --porcelain (before/after docs)
static inspection of models/routers/services/FE notification files
```

```
RUNTIME_CODE_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CREATED=NO
SOUND_ASSET_ADDED=NO
DEPENDENCY_CHANGED=NO
DOCS_ONLY_MUTATION=YES
```

## Continuity

```
MASTER_LOG_TIP=§507
CURSOR_HANDOFF_TIP=v800
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v800_FA.md
```

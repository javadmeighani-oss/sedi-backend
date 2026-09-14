# SEDI Cursor Authoritative Handoff - v805

G0 governance closure correction — docs-only. Append-only successor after continuity reconcile from ChatGPT v804 + historical G0 Cursor v800. Do not modify v800 / v804 / §507 evidence bodies.

```
VERSION=v805
STATUS=CURRENT
LOGICAL_PREDECESSOR_CURSOR_G0_DOC=v800
CONTINUITY_BASELINE=v804
G0_REPORTED_DOC=v800
SUCCESSOR_MODE=CREATE_ONLY
MASTER_LOG=§508
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G0-GOVERNANCE-CLOSURE-CORRECTION-01
GATE_RESULT=PASS
MODE=DOCS_ONLY
APPROVED_BY=Javad
NO_RUNTIME_MUTATION=YES
SCHEMA_MUTATION=NO
MIGRATION=NO
SOUND_ASSET_ADDED=NO
COMMIT_PERFORMED=NO
PUSH_PERFORMED=NO
DEPLOY_PERFORMED=NO
NEXT_EXECUTION_GATE_AUTHORIZED=NO
G0_GOVERNANCE_CLOSURE=PASS
```

## Continuity reconciliation

```
CONTINUITY_BASELINE=v804
G0_REPORTED_DOC=v800
CONTINUITY_RECONCILIATION=G0_inspected_workspace_Cursor_tip_v799_and_created_Cursor_v800_plus_MasterLog_§507; ChatGPT_Independent_Continuity_was_already_v804_and_had_instructed_not_to_create_§507/Cursor_v800_for_Gadgets_physical_E2E; G0_audit_findings_are_VALID_and_PRESERVED_under_v800/§507_as_historical_evidence; v800_MUST_NOT_be_treated_as_latest_cross-track_authoritative_continuity; this_v805_is_the_monotonic_CURRENT_Cursor_authoritative_successor_from_CONTINUITY_BASELINE_v804_while_preserving_v800_unchanged
v800_STATUS_FOR_CONTINUITY=HISTORICAL_G0_EVIDENCE_NOT_CURRENT_TIP
v804_STATUS=CHATGPT_INDEPENDENT_CONTINUITY_BASELINE_ENTERING_THIS_CORRECTION
```

## Heads (verified)

```
BACKEND_BRANCH=feature/a3-authority-chat-stream-profile-foundation
BACKEND_HEAD=7610c9da67c83e7d620b180a57647c37e8e88e83
FRONTEND_BRANCH=feature/a3-authority-chat-stream-profile-foundation
FRONTEND_HEAD=2ff9c72d1e62e4582f29514e7edfb00a9e7e5b0a
```

## This section reconciles (explicit)

1. Continuity numbering (v804 baseline → v805 CURRENT; v800 preserved)
2. I10 bypass taxonomy
3. Gadget OTHER semantics
4. Newly approved A3 Smart Notification / retention / sound / authority policies for G1

Original G0 findings in v800 / §507 remain evidence. No historical deletion.

---

## 1) I10 bypass taxonomy correction

G0 reported `PROVEN_I10_BYPASSES=5` including `admin_test_push`.

### Corrected classification

**PRODUCT_RUNTIME_BYPASS_CANDIDATES** (each = `BYPASS_CANDIDATE_REQUIRES_REACHABILITY_HARDENING`; not auto-declared production defect without further hardening proof):

1. `create_insight_notification` — direct `NotificationBuilder.persist` / reachable from product routers
2. `evaluate_health_data` — direct persist / reachable from health path
3. `kc_notification` (`knowledge._maybe_send_kc_notification`) — direct ORM enqueue
4. `ml_care_bridge` — direct ORM enqueue (flag-gated ops path)

**ADMIN_TEST_ONLY:**

- `admin_test_push` — diagnostic/admin path only  
  **NOT** a proven production runtime notification-authority defect.

```
ADMIN_TEST_DIAGNOSTIC_PATH_NE_PRODUCTION_AUTHORITY_DEFECT=YES
PRODUCT_RUNTIME_BYPASS_CANDIDATES_COUNT=4
ADMIN_TEST_ONLY_PATHS_COUNT=1
```

No code mutation in this Gate.

---

## 2) Gadget OTHER semantics — LOCKED correction

```
GADGET_OTHER_HEALTH_SUBJECT_EQUIVALENCE=PROHIBITED
```

### GADGET IDENTITY AXIS (LOCKED)

- **SELF** = the user's own/main gadget
- **OTHER** = another gadget connected to the **SAME** user's Sedi platform/account context
- OTHER may have a user-editable display name

**OTHER in Gadgets MUST NOT mean:**

- MANAGED_SUBJECT
- caregiver
- another person
- HealthSubject under care

### Keep separate (LOCKED)

**A) Gadget identity/provenance**

- SELF / OTHER
- gadget_id
- gadget display name

**B) I10 recipient/subject authority**

- SELF
- MANAGED_SUBJECT
- CAREGIVER
- health_subject_id
- access / grants / consent

If a Gadget OTHER is later associated with a HealthSubject:

- association must be backend-governed and explicit
- frontend must not infer it
- `OTHER` itself does **not** imply HealthSubject identity

### G0 wording correction

v800 Stage 5 line that read essentially “OTHER / managed subject / caregiver attribution via health_subject_id / recipient_kind / grants” is **CORRECTED**: that sentence improperly conflated Gadget OTHER with I10 subject/recipient axes. I10 subject/recipient attribution remains via `health_subject_id` / `recipient_kind` / grants for **I10 authority only** — not as a definition of Gadget OTHER.

---

## 3) APPROVED / LOCKED — A3 Smart Notification decisions (Javad)

```
A3_INBOX_SOURCE=PostgreSQL/backend canonical Notification history

A3_HISTORY_PROJECTION=only successfully sent notifications eligible for normal user Inbox history
ELIGIBILITY_CONCEPTUAL=is_sent=true AND sent_at IS NOT NULL
QUEUED_FUTURE_UNSENT_IN_NORMAL_INBOX=NO
FAILED_ONLY_IN_NORMAL_USER_INBOX=NO
FAILED_OBSERVABILITY=backend/admin/operational surfaces only

ORDER=sent_at DESC then id DESC deterministic tie-break

PAGINATION_INITIAL_PAGE_SIZE=20
PAGINATION_STYLE=cursor-based preferred
PAGINATION_MAX_PAGE_REQUEST=50

USER_VISIBLE_HISTORY_DAYS=180
FULL_NOTIFICATION_CONTENT_RETENTION_DAYS=180
I10_DECISION_AUDIT_RETENTION_DAYS=365
I10_LEDGER_RETENTION_CONSTRAINT=policy/evidence-reference/governance metadata only; must not become unnecessary raw health/chat storage
CLEANUP_ACTIVATION_PREREQUISITE=validate FK/linkage deletion behavior before any prune/archive job is activated

SCHEDULED_REMINDERS=remain backend scheduler/outbox until successfully sent; NOT in A3 Smart Notifications until sent
UPCOMING_REMINDERS_SURFACE=NOT_IN_CURRENT_A3_SMART_NOTIFICATIONS_SCOPE
```

Status: **APPROVED / LOCKED** — implementation remains G1+ (not this Gate).

---

## 4) APPROVED / LOCKED — Sound policy V1 (Javad)

```
SOUND_POLICY_V1=ONE canonical Sedi signature sound asset for V1
SOUND_MAY_BE_SELECTIVE_BY_CHANNEL_POLICY=YES
NOT_EVERY_NOTIFICATION_MUST_PLAY_SOUND=YES

HEALTH_ALERT_DIFFERENTIATION=higher importance + heads-up where supported + vibration + SAME canonical Sedi auditory identity for V1
MORNING_LOW_PRIORITY=may remain silent per channel/policy

SOUND_STORAGE=Android/iOS app bundle binary
BACKEND_ROLE=semantic/channel/policy selection only
RUNTIME_SOUND_DOWNLOAD=PROHIBITED for canonical V1 notification delivery

CURRENT_GAP=Android references sedi_alarm; iOS references sedi_alarm.wav; both binary assets MISSING
FINAL_AUDIO_SOURCE=must later be original, CC0, or clearly redistributable/licensed
G0_CORRECTION_SOUND_DOWNLOAD_OR_ADD=NO
```

---

## 5) LOCKED — Authority map

```
Chat / Reminder / Daily Intelligence / Gadget / I9 / governed producers
→ I10 adapter / intent
→ identity + recipient + subject authorization
→ canonical I10 policy
→ PostgreSQL Notification persistence
→ Gate4 delivery/prefs/resolver
→ FCM/APNs
→ bundled Sedi mobile sound
→ OS notification
→ A3 Smart Notifications Inbox
→ user interaction
→ I10/domain interaction recorder/handler
```

Authorities:

| Layer | Role |
|-------|------|
| I10 | notification intelligence/decision authority |
| PostgreSQL | notification persistence/history source of truth |
| Gate4 | lower-level delivery/prefs/resolver infrastructure |
| FCM/APNs | transport carrier |
| Android/iOS | OS presentation |
| A3 | Inbox/history + interaction |
| Flutter frontend | presentation; no clinical decision authority |

```
SECOND_NOTIFICATION_ARCHITECTURE=PROHIBITED
```

---

## 6) Preserved G0 audit facts (unchanged substance)

From historical v800 / §507 (still valid evidence):

- `notifications` is both outbox and history table today
- Current GET inbox shows unsent/queued/failed (pre-G1 projection)
- No DB retention job confirmed (`NONE_CONFIRMED` at G0; retention now **policy-locked** above, not implemented)
- Sound code references exist; binaries missing
- I10 canonical intake exists; Gate4 is lower-level reused
- Mobile inbox uses server API; OS tray is not SoT

---

## 7) Next Gate (record only — NOT authorized)

```
NEXT_GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G1-INBOX-PROJECTION-RETENTION-SOUND-POLICY-01
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Continuity tips

```
MASTER_LOG_TIP=§508
CURSOR_HANDOFF_TIP=v805
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v805_FA.md
CHATGPT_CONTINUITY_BASELINE=v804
G0_HISTORICAL_DOC=v800
```

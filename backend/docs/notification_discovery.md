# Notification System – Key Files & Discovery

**Purpose:** Single reference for anyone adding or changing notification-related behavior.  
**Contract:** `notification_contract.md` Version 1.0.0 is the source of truth. All changes must keep backward compatibility.  
**V1 product spec:** [NOTIFICATIONS_V1_SPEC.md](NOTIFICATIONS_V1_SPEC.md) (channels, sending rules, tone, feedback, UI).

---

## 1. Key Files (paths) – notification-related

### Backend (FastAPI)

| Path | Role |
|------|------|
| `backend/app/routers/notifications.py` | All notification HTTP endpoints |
| `backend/app/schemas/notification.py` | Pydantic: NotificationBase, NotificationCreate, NotificationResponse, NotificationPayload, NotificationFeedbackRequest, PushRegisterRequest, PushFeedbackActionRequest, TestPushRequest |
| `backend/app/schemas/__init__.py` | Exports NotificationBase, NotificationCreate, NotificationResponse |
| `backend/app/models.py` | DB: Notification, PushDevice, NotificationFeedback |
| `backend/app/services/notification_engine.py` | Notification creation / scheduling |
| `backend/app/services/notifications/delivery_service.py` | FCM delivery, deliver_pending |
| `backend/app/services/notifications/adaptive_policy_v1.py` | Companion adaptive policy: compute_adaptive_state, is_companion_send_allowed |
| `backend/app/services/notifications/send_guard_v1.py` | Send Guard V1: can_send_v1 (pause, quiet_hours, dedup, cap) — single entry for all send paths |
| `backend/app/services/notifications/fcm_client.py` | FCM HTTP client |
| `backend/app/services/notification_runtime/renderer.py` | Renders notification content (supports optional template.texts) |
| `backend/app/services/notification_runtime/i18n_resolver.py` | Multi-language text resolution: `resolve_text_by_user_language` |
| `backend/app/services/notification_runtime/templates_v1.py` | V1 templates registry: `get_template_v1`, `list_templates_v1`, `validate_templates_v1` |
| `backend/app/services/notification_runtime/quiet_hours.py` | Quiet hours / policy |
| `backend/docs/notification_contract.md` | Contract 1.0.0 – do not break |

### Frontend (Flutter)

| Path | Role |
|------|------|
| `frontend/lib/data/models/notification.dart` | Contract Section 1: Notification, NotificationType, NotificationPriority, NotificationAction, NotificationMetadata; parses `body` or `message` |
| `frontend/lib/data/models/notification_feedback.dart` | Contract Section 5: NotificationFeedback, FeedbackReaction; toJson (contract) and toBackendJson (B2) |
| `frontend/lib/features/notification/data/notification_service.dart` | GET /notifications, GET /notifications/unread, mark-read, feedback |
| `frontend/lib/features/notification/presentation/pages/notifications_inbox_page.dart` | Inbox UI; uses NotificationService, Notification.fromJson |
| `frontend/lib/features/notification/presentation/widgets/notification_card.dart` | Single notification card |
| `frontend/lib/features/notification/logic/notification_handler.dart` | Handles incoming notifications |
| `frontend/lib/features/notification/logic/notification_sync.dart` | Sync with backend |
| `frontend/lib/features/notification/utils/notification_ui_mapping.dart` | UI mapping for types |
| `frontend/lib/features/chat/presentation/pages/chat_page.dart` | Contains _NotificationSettingsSheet (notification settings bottom sheet) |

---

## 2. Existing notification endpoints (backend)

| Method + Path | Purpose |
|---------------|---------|
| GET `/notifications` or `/notifications/` | List notifications for user_id. Returns `data.notifications`, `data.total` (full count before limit), `data.unread_count` (full unread count). Contract Section 7. |
| GET `/notifications/unread` | Unread list; query: user_id, limit, type. Returns `data.notifications`, `data.count` (returned list size), `data.total`, `data.unread_count` (full unread count before limit). |
| POST `/notifications/{id}/mark-read` | Mark read (query: user_id). Alias: `.../read`. |
| POST `/notifications/{id}/feedback` | V1: Contract (reaction, timestamp, action_id when reaction=interact, feedback_text?, reason?) and legacy (feedback/action) accepted. Stored event_type: like/dislike/open/dismiss. 422 if reaction=interact and action_id missing. Response: `{ feedback_received: true, message: "Feedback recorded" }`. |
| GET `/notifications/admin/feedback_stats` | Admin: query user_id?, days=7. Returns counts_by_event_type, counts_by_reason, last_events (max 20). |
| GET `/notifications/admin/adaptive_state` | Admin: query user_id, days=7. Returns paused_until, companion_cap_override, counts, reasons_count, computed_at (debug for adaptive policy V1). |
| POST `/notifications/push/register` | Register FCM token (body: user_id, platform, fcm_token, device_id?, app_version?). |
| POST `/notifications/push/unregister` | Deactivate token (query: fcm_token, user_id). |
| POST `/notifications/deliver_pending` | Admin/delivery: deliver pending pushes. |
| GET `/notifications/admin/push_devices` | Admin: list push devices for user_id. |
| POST `/notifications/admin/test_push` | Admin: enqueue test push (body: user_id, channel, title?, body?, priority?, ttl_seconds?; query: deliver?). |
| POST `/notifications/admin/notif/send_now` | Admin: send one push now (query: user_id, channel, force?, template_key?). When `template_key` is set, Send Guard V1 runs; if blocked, returns 200 with `blocked: true` and no FCM send. |
| GET `/notifications/admin/health` | Admin: delivery health stats. |
| GET `/notifications/admin/templates/list` | Admin: list V1 template keys and basic fields. |
| GET `/notifications/admin/templates/preview` | Admin: preview template render (query: template_key, user_id?, lang=fa). |

**send_now blocked response (optional additive fields):** When the Send Guard blocks the send (e.g. paused, quiet_hours, dedup, cap), the response is still **200 OK** with `data.sent_success=0`, `data.sent_fail=0`, and these optional fields: `blocked` (true), `reasons` (list of strings, e.g. `["paused"]`, `["quiet_hours"]`, `["dedup"]`, `["cap"]`), `paused_until` (ISO string when reason is paused), `dedupe_key` (canonical key when applicable). Clients may ignore these; they are additive and do not break the contract.

---

## 3. Backend response shape vs contract

- **Contract Section 1:** Notification object has `message` (required). Backend DB and `NotificationResponse` use `body`. Frontend `Notification.fromJson` accepts both `body` and `message` → safe.
- **Contract Section 7 – GET /notifications:** Backend returns `data.notifications`, `data.total`, and `data.unread_count`. `total` and `unread_count` are **full counts** (from base query before any limit/pagination), not the size of the returned list. GET /notifications/unread returns `data.notifications`, `data.count` (returned list length), `data.total`, `data.unread_count` (full unread count before limit). Frontend treats `total`/`unread_count` as optional.
- **Types:** Contract 1.0.0: info, alert, reminder, check_in, achievement. Backend also uses morning_brief, connection_ping, health_alert, device_disconnected. Frontend enum supports both; unknown → info.
- **Priority:** Contract: low, normal, high, urgent. Backend sometimes uses `critical`; frontend maps critical → urgent.

### Multi-language text resolution

- **Module:** `backend/app/services/notification_runtime/i18n_resolver.py` — `resolve_text_by_user_language(texts, user_language, default="fa")`.
- **Renderer:** When a notification template includes a `texts` dict, the renderer (`renderer.py`) resolves it by user language and uses the result for `title` and `body` (contract `message` ↔ backend `body`); otherwise channel-based rendering is used.
- **Expected template structure (multilingual):**
  ```json
  {
    "texts": {
      "fa": { "title": "...", "message": "..." },
      "en": { "title": "...", "message": "..." },
      "fa-IR": { "title": "...", "message": "..." }
    }
  }
  ```
  Keys can be locale codes (`fa`, `fa-IR`, `en-US`); resolution uses **prefix match** (e.g. `fa-IR` → `fa`) then fallback.
- **Fallback order:** `user_language` (exact or prefix) → `default` (e.g. `"fa"`) → `"fa"` → `"en"` → first available key.
- **Flat structure:** If `texts` is already a single block `{"title": "...", "message": "..."}` (no nested lang keys), it is returned as-is. `None` or invalid input returns `{}`.

---

## 4. Naming and conflicts

- **Notification (model):** Used in backend (ORM + Pydantic) and frontend (Dart model). No conflict; frontend uses `data/models/notification.dart` and alias `sedi` in inbox.
- **Feedback:** Contract Section 5 uses `reaction` (seen, interact, dismiss, like, dislike). Backend B2 uses `feedback` (positive/negative/neutral) + reason/action; Stage 16.6 stores `action` (like, dislike, open_chat, dismissed). Backend accepts both; frontend sends `toBackendJson()` (B2). No naming conflict for new fields if they are optional and documented in contract as MINOR add-ons.
- **New fields:** Any new field in API or contract must be optional (or defaulted) so existing frontends can ignore it. Prefer adding to `metadata` or as optional top-level fields documented in `backend/docs/`.

---

## 5. Frontend inbox and “settings”

- **Inbox:** `NotificationsInboxPage` – loads via `NotificationService.getNotifications`, displays list, mark-read on tap, like/dislike via `NotificationFeedback` and `submitFeedback`.
- **Settings:** No dedicated app-level “notification settings” page. There is a bottom sheet `_NotificationSettingsSheet` in `chat_page.dart` (notification settings quick actions). New notification preferences (e.g. quiet hours, toggles) would likely extend this sheet or a new optional screen; backend can add optional endpoints/settings fields without breaking contract.

---

## 6. Verification commands (reference)

After any change:

```bash
# Backend (from repo root; set DATABASE_URL if needed)
cd backend && python -m pytest backend/tests/ -q -v --tb=short
# Or minimal: python -c "from backend.app.routers import notifications; print('ok')"

# Frontend
cd frontend && flutter analyze

# Curl examples (replace BASE and USER_ID)
BASE=http://91.107.168.130:8000
USER_ID=1
curl -s "$BASE/notifications?user_id=$USER_ID"
curl -s "$BASE/notifications/unread?user_id=$USER_ID&limit=5"
```

---

**Feedback (V1):** Request example: `POST /notifications/{id}/feedback?user_id=1` body `{ "reaction": "like", "timestamp": "2025-02-13T12:00:00Z", "reason": "too_frequent" }`. For `reaction: "interact"`, `action_id` is required (422 if missing). Response: `{ "ok": true, "data": { "feedback_received": true, "message": "Feedback recorded" } }`. Admin stats: `GET /notifications/admin/feedback_stats?user_id=1&days=7` returns `counts_by_event_type`, `counts_by_reason`, `last_events` (max 20). **Adaptive policy (V1):** `GET /notifications/admin/adaptive_state?user_id=1&days=7` returns `paused_until`, `companion_cap_override`, `counts`, `reasons_count`, `computed_at`. Companion sends (template or channel) are blocked when paused; cap override (1/day when dislike ≥ 2) is enforced in engine and send_now.

**See also:** [NOTIFICATIONS_V1_SPEC.md](NOTIFICATIONS_V1_SPEC.md) — V1 channels, sending rules, tone, feedback normalization, and UI requirements.

**Last updated:** 2025-02-13 (discovery run).

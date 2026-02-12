# Notification V1 — E2E Test Runbook (Real Server + Device)

This runbook describes how to test push notifications end-to-end with a real APK on a device and the backend on the server. No new tools; use existing APIs and logs.

---

## 1) Pre-check

- **App:** Install the Sedi APK (e.g. from GitHub Actions build) on a real Android device.
- **User:** Log in (complete onboarding or user verification) so that a `userId` exists and the profile is saved.
- **Backend:** Server is running and reachable; `FCM_PROJECT_ID` and `FCM_SERVICE_ACCOUNT_JSON` are set if you expect real FCM delivery.
- **Token:** Ensure the app has registered an FCM token with the backend (see step 2). Placeholder or invalid tokens are rejected with HTTP 400.

---

## 2) Token

- **On device:** After opening the app (and if logged in), check logs for a masked FCM token, e.g.:
  - `FCM token: xxxxxx...yyyy`
  - `FCM register => status: 200`
- **Backend:** Confirm register returned 200. You can also call `GET /notifications/admin/push_devices?user_id=<id>` (with admin auth if required) to see masked tokens for that user.
- **Invalid token:** Sending a placeholder or too-short token to `POST /notifications/push/register` must return **400** with detail like: `Invalid FCM token (placeholder/too short/whitespace).`

---

## 3) Test the four notification types (and three channels)

Use the admin endpoint to send one push per channel. Types and channel mapping:

| Type                | Channel     | Notes |
|---------------------|------------|--------|
| morning_brief       | morning    | |
| connection_ping     | engagement | |
| health_alert        | health_alert | |
| device_disconnected| engagement | Default when channel is missing (Stage 19). |

**Endpoint:** `POST /notifications/admin/notif/send_now?user_id=<id>&channel=<channel>&force=true`  
(Use `force=true` to bypass quiet hours for testing.)

- `channel=morning`   → type morning_brief / channel morning  
- `channel=engagement` → type connection_ping or device_disconnected / channel engagement  
- `channel=health_alert` → type health_alert / channel health_alert  

For each call, expect **200** and in the response body check `sent_success` (and optionally `sent_fail`, `reasons`, `fcm_errors`).  
Server logs should show: `event=send_now channel=... user_id=...` and then for each FCM send: `event=fcm_send ... result=success` or `result=failure` with `error_code=...`.

---

## 4) Test app in three states

For at least one of the channels above, verify the notification is received and shown:

1. **Foreground:** App in foreground → notification should appear via in-app/local notification handling.
2. **Background:** App in background → notification should appear in the system tray; tapping it should open the app (and optionally navigate to chat).
3. **Terminated:** App killed → same as background; tap should open app and optionally deep link to chat.

Use the same `send_now` (or a test notification created via the API) for each state.

---

## 5) Feedback

- Trigger a notification, then from the app perform one of: **like**, **dislike**, **open_chat**, **dismissed**.
- Call: `POST /notifications/{notification_id}/feedback` with body containing the chosen `action` (and optional `client_ts`, `meta`).
- Expect **200** and confirm in backend that the feedback was stored (e.g. check logs or DB).

---

## 6) Server logs (what to expect)

- **On send_now:**  
  `event=send_now channel=<channel> user_id=<id>`
- **On each FCM send attempt:**  
  `event=fcm_send notification_id=... channel=... type=... token_hash=... result=attempt`
- **On success:**  
  `event=fcm_send ... result=success`
- **On failure:**  
  `event=fcm_send ... result=failure error_code=<code>`  
  No raw FCM token should appear in logs; only `token_hash` (mask).

If the FCM response indicates an invalid/unregistered token (`UNREGISTERED` / `NOT_FOUND`), the backend should deactivate that token (e.g. `PushDevice.is_active = False`) and log it; subsequent sends will not use that token.

---

## 7) Quick checklist

- [ ] App installed, user logged in.
- [ ] FCM token registered (masked token and `FCM register => status: 200` in logs).
- [ ] Placeholder/invalid token rejected with 400.
- [ ] send_now for `morning`, `engagement`, `health_alert` returns 200 and log shows `event=fcm_send ... result=success` (or expected failure with `error_code`).
- [ ] device_disconnected type uses channel `engagement` when channel is not set.
- [ ] Notification received in foreground, background, and terminated.
- [ ] At least one feedback action (e.g. open_chat or dismissed) returns 200.

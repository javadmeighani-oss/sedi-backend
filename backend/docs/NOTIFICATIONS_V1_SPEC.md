# Notifications V1 – Product & Behaviour Spec

**Status:** Spec (doc only). Implementation reference: `notification_discovery.md`, `notification_contract.md` v1.0.0.  
**Endpoints:** `backend/app/routers/notifications.py` · **Rendering:** `backend/app/services/notification_runtime/renderer.py` · **Quiet hours:** `backend/app/services/notification_runtime/quiet_hours.py`

---

## 1) V1 Channels

| Channel        | Description              | Contract `type` (unchanged) | Default priority | DB/channel mapping note |
|----------------|--------------------------|-----------------------------|------------------|--------------------------|
| **companion**  | Engagement, check-in     | `check_in` or `info`        | normal           | Map to existing engagement/morning-style logic. |
| **health_alert** | Vital/condition alerts | `alert`                     | high / urgent    | Already present; map to `health_alert`. |
| **medication** | Reminders (meds, habits) | `reminder`                  | normal           | Map to reminder-style; template_key for dedup. |
| **appointment**| Visits, follow-ups       | `reminder`                  | normal           | Same as reminder; distinct template_key. |
| **system**     | App/config, account     | `info`                      | low              | Non-promotional; minimal frequency. |

**Mapping rules:** Do not change contract enums (Section 2–3 of `notification_contract.md`). Backend chooses `type`/`priority` per row above. Store channel (or equivalent) in DB for routing and dedup; API continues to expose contract `type` and `priority`.

---

## 2) Sending rules

- **Companion cap:** Max 2 companion notifications per user per calendar day (configurable default).
- **Quiet hours default:** 22:30–07:30 user-local. No non-urgent push during this window; health_alert with priority `urgent` may bypass. Implementation uses `quiet_hours.py` and UserMemoryFact `quiet_hours` + `timezone`.
- **Dedup key (canonical):** `{channel}:{template_key}:{user_id}:{YYYY-MM-DD}`. Example: `companion:companion_daily_checkin_v1:126:2026-02-13`. One notification per key per day; duplicate key → skip or update, do not create a second row. Companion cap counting accepts both this format and the legacy format `companion_*` (template_key starting with `companion_`) for backward compatibility.
- **Backoff from feedback:**  
  - 2× dislike (or equivalent negative) for same channel → reduce frequency (e.g. halve) for that channel.  
  - 3× dismiss (ignore) → pause that channel for 48h for that user.  
  Store feedback via existing `notification_feedback` and/or memory facts; apply rules in scheduler/engine before send.
- **V1 ignore definition:** In V1, **ignore** = stored event type **dismiss**. Open events do not count as ignore and do not trigger pause or cap.
- **Adaptive policy precedence (V1):** 1) **Pause** (dismiss ≥ 3) > 2) **Cap** (dislike ≥ 2 → companion_cap_override = 1/day) > 3) **Like boost** (like ≥ 2 → cap remains 2/day). When both like and dislike thresholds are met, cap reduction wins (dislike ≥ 2 → cap = 1).

### Send Guard V1 (single entry for all send paths)

All sends (engine `build_notification_from_template` and router `POST /notifications/admin/notif/send_now` when `template_key` is present) use **Send Guard V1** (`backend/app/services/notifications/send_guard_v1.py`). Checks run in order; all applicable reasons are collected; send is allowed only when no reason applies.

**Precedence (order of checks):**

1. **A) Adaptive pause (companion only)** — `is_companion_send_allowed()`. If paused → reason `paused`; result includes `paused_until` (ISO).
2. **B) Quiet hours** — Default 22:00–08:00 user-local (implementation in `quiet_hours.py`). If within quiet → reason `quiet_hours`. **Exception:** `health_alert` with priority `critical` does not add `quiet_hours`. Admin `send_now` with `force=true` bypasses quiet hours.
3. **C) Dedup** — When `template_key` is present, canonical key `{channel}:{template_key}:{user_id}:{YYYY-MM-DD}`. If a notification already exists for that user with that `dedupe_key` → reason `dedup`.
4. **D) Cap (companion only)** — `compute_adaptive_state` gives cap override (default 2). Count companion notifications today (canonical + legacy prefixes). If count ≥ cap → reason `cap`.

**Reasons list:** `paused` | `quiet_hours` | `dedup` | `cap`. Guard return shape: `allowed` (bool), `reasons` (list of str), `dedupe_key` (str | None), `cap` (int | None), `paused_until` (str | None).

---

## 3) Tone / Voice V1

- **Principles:** Short, human, caring, non-alarming. Avoid medical jargon; use clear, actionable wording.
- **Examples:**

| Context   | EN | FA |
|-----------|----|-----|
| Check-in  | Just checking in — how are you feeling today? | یک لحظه سراغت اومدم؛ امروز حالت چطوره؟ |
| Reminder  | Time for your medicine. Stay on track. | وقت داروت رسیده. سر موقع بخور. |
| Health    | Your heart rate was a bit high during rest. Want to log it or chat? | ضربان قلبت موقع استراحت کمی بالا بود. می‌خوای ثبت کنیم یا بگیم؟ |

---

## 4) Interaction & feedback

- **Actions:** like, dislike, open (e.g. open chat/screen), dismiss. Align with contract Section 4 and existing `action` (like/dislike/open_chat/dismissed) and feedback endpoints.
- **Optional reason** (e.g. in feedback payload or metadata): `too_frequent` | `irrelevant` | `unclear`. Used for analytics and backoff; not required for contract compliance.
- **V1 normalization (backend):** Stored event types are normalized to: `like`, `dislike`, `open`, `dismiss`. Contract/legacy values are mapped as follows (acceptance unchanged):
  - `seen` → stored as `open`
  - `interact` → stored as `open` (and **action_id required** when reaction is `interact`; 422 if missing)
  - `like` / `dislike` / `dismiss` → stored as-is
  - Legacy `open_chat` → `open`, `dismissed` → `dismiss`; B2 `feedback` positive/negative/neutral → like/dislike/open.
- **Validation:** If `reaction === "interact"`, request must include `action_id` (422 otherwise).
- **Response:** `{ ok: true, data: { feedback_received: true, message: "Feedback recorded" }, error: null }`.

---

## 5) UI requirements

- **Inbox:** Tabs (e.g. All / Unread), unread badge (use `data.unread_count` from API), mark-as-read (existing endpoint), deep links (e.g. `sedi://chat?from=notif&id=…`) for open action.
- **Settings:** Toggles per channel (or “engagement” toggle), quiet hours time range, engagement frequency (e.g. companion cap override), sound selection. Persist via existing preferences/memory or new optional endpoints; do not break contract.

---

---

## 6) V1 Templates (code-controlled)

Templates are **versioned and code-controlled** in `backend/app/services/notification_runtime/templates_v1.py`. They are not user-editable; changes require a code deploy.

**Template keys included in V1:**

| Key | Channel | Description |
|-----|---------|-------------|
| `companion_daily_checkin_v1` | companion | Daily check-in (FA + EN) |
| `companion_encourage_move_v1` | companion | Encourage movement |
| `companion_breathing_break_v1` | companion | Breathing break reminder |
| `health_alert_generic_v1` | health_alert | Generic health alert |

**Helpers:** `get_template_v1(key)`, `list_templates_v1()`, `validate_templates_v1()`.  
**Admin endpoints:** `GET /notifications/admin/templates/list`, `GET /notifications/admin/templates/preview?template_key=...&lang=fa`, and `POST /notifications/admin/notif/send_now` accepts optional `template_key` for template-rendered title/body.

---

**See also:** `notification_contract.md` (API contract), `notification_discovery.md` (key files and endpoints).

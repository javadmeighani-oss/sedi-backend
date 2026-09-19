# SUPERSEDED — Notifications v1 Android

> **SUPERSEDED for product routing / Firebase physical-build policy.**  
> Canonical index: [`FRONTEND_AUTHORITY_INDEX.md`](./FRONTEND_AUTHORITY_INDEX.md)

Corrections vs older Stage 16 notes:

- Production Smart Notifications UI is **`NotificationInboxPage`** (plural `features/notifications/`), not legacy `ChatPage` inbox chrome.
- Notification tap must resolve session then `AppGateRouter.goToHeart` — never legacy `ChatPage`.
- Physical APK builds must use real `GOOGLE_SERVICES_JSON` (`project_id=sedi-b0f08`, package `com.sedi.app`). Placeholder/CI stub is **not** acceptable for physical APK authority.
- Channel names and local setup details may still be useful as history; they are not product-graph authority.

Canonical notification modules: `lib/features/notifications/`, `lib/services/notifications/`, `lib/core/notifications/`, `lib/services/push/`.

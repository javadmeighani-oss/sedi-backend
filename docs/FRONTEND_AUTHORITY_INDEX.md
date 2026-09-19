# Frontend Authority Index (Canonical)

**Status:** CURRENT  
**Repo:** `javadmeighani-oss/sedi-frontend`  
**Canonical product graph:** IntroPage → OtpLoginPage → Gate3InteractivePage  

```
ARCHITECTURE_AUTHORITY=SEDI-V1-ARCH-BASELINE-001@v1
ARCHITECTURE_FILE=references/authoritative/architecture/Sedi_V1_Canonical_Architecture_Baseline_v1_FA.md
CERTIFIED_FRONTEND_HEAD=75f1b40097aefe6109078b1935b9a382c8643cde
```

See also: `docs/ARCHITECTURE_AUTHORITY.md`

## Product gates

| Gate | Authority | Entry |
|------|-----------|--------|
| A1 | Intro / Startup / Session | `lib/features/intro/.../intro_page.dart` + `SessionGateResolver` |
| A2 | Language / Registration / Login / OTP / Profile | `lib/features/auth_otp/.../otp_login_page.dart` |
| A3 | Sedi Heart / primary interaction | `lib/features/gate3_interactive/.../gate3_interactive_page.dart` |
| A4 | Outside-app Smart Notifications continuity | `NotificationBootstrap` + FCM → `AppGateRouter.goToHeart` |

A3 top icons (exact): **Profile | Lifestyle | Gadgets | Smart Notifications**  
Health = Lifestyle child (`LifestyleHealthPage`). Intelligence is not a V1 standalone page/icon.

## Notification authority (canonical)

- `lib/features/notifications/`
- `lib/services/notifications/`
- `lib/data/dto/notifications/`
- `lib/data/models/notification_item.dart`
- `lib/core/notifications/`
- `lib/services/push/`

Production inbox page: **`NotificationInboxPage` only**.  
Tap path: notification → session resolve → `AppGateRouter.goToHeart(notificationId)` → `Gate3InteractivePage` → `ChatController.sourceNotificationId` → `POST /interact/chat`.

## Chat runtime (canonical)

- `lib/features/chat/state/chat_controller.dart`
- `lib/features/chat/presentation/widgets/message_bubble.dart`
- `lib/services/chat/chat_service.dart`
- `lib/services/chat/chat_stream_client.dart`

Legacy ChatPage / OnboardingPage / VitalsPage / singular `features/notification/` wrappers are **ABSENT**.

## API / Android

- Production API base: `https://api.sedi-ai.com` (`AppConfig.baseUrl`)
- Android package / applicationId: `com.sedi.app`
- Physical APK Firebase: repository secret `GOOGLE_SERVICES_JSON` for project `sedi-b0f08` (placeholder not allowed for physical builds)
- Network security: production cleartext disabled; legacy direct-IP `91.107.168.130` / `network_security_config.xml` **ABSENT**

## Docs

- Historical stage reports: `docs/archive/frontend_legacy/` (SUPERSEDED)
- Stale operational notes below are SUPERSEDED stubs pointing here.
- Full cross-stack architecture baseline: **NEXT_GATE** (after independent ChatGPT review).

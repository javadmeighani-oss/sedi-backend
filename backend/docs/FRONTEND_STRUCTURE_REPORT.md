# گزارش آخرین تغییرات و ساختار فرانت‌اند

**اپ:** Sedi Intelligent Health Assistant  
**فریمورک:** Flutter (SDK >=3.0.0 <4.0.0)  
**نسخه:** 1.0.0+1  
**مسیر در ریپو:** `backend/frontend` و همچنین `frontend` (در ریشهٔ Demo)

---

## ۱) نمای کلی

فرانت‌اند یک اپ **Flutter** چندپلتفرمه (Android، iOS، Web، Windows، Linux، macOS) است. نقطهٔ ورود اصلی **Intro** است؛ از آنجا به **Onboarding**، **User Verification** و **Chat** می‌رود. تنظیمات بک‌اند در `AppConfig` (baseUrl و useLocalMode) انجام می‌شود.

---

## ۲) ساختار دایرکتوری (lib)

```
lib/
├── main.dart                 # نقطه ورود → SediApp
├── app.dart                  # MaterialApp، تم، home: IntroPage
├── core/
│   ├── config/
│   │   └── app_config.dart   # baseUrl، useLocalMode
│   ├── auth/
│   │   ├── auth_helper.dart
│   │   └── auth_service.dart
│   ├── network/
│   │   └── api_client.dart
│   ├── theme/
│   │   └── app_theme.dart
│   └── utils/
│       ├── language_detector.dart
│       ├── messages.dart
│       ├── user_preferences.dart
│       └── user_profile_manager.dart
├── data/
│   ├── dto/
│   │   ├── interact_request.dart
│   │   └── interact_response.dart
│   ├── models/
│   │   ├── chat_message.dart
│   │   ├── notification.dart
│   │   ├── notification_feedback.dart
│   │   └── user_profile.dart
│   └── repositories/
│       └── chat_repository.dart
├── features/
│   ├── intro/
│   │   └── presentation/pages/intro_page.dart
│   ├── onboarding/
│   │   └── presentation/pages/onboarding_page.dart
│   ├── user_verification/
│   │   └── presentation/pages/user_verification_page.dart
│   ├── chat/
│   │   ├── chat_service.dart
│   │   ├── state/chat_controller.dart
│   │   └── presentation/
│   │       ├── pages/
│   │       │   ├── chat_page.dart
│   │       │   └── chat_history_page.dart
│   │       └── widgets/
│   │           ├── input_bar.dart
│   │           ├── message_bubble.dart
│   │           ├── sedi_header.dart
│   │           ├── sedi_ring_anim.dart
│   │           └── language_selection_dialog.dart
│   └── notification/
│       ├── data/models/sedi_notification.dart
│       ├── notification_service.dart
│       ├── logic/
│       │   ├── notification_handler.dart
│       │   ├── notification_test.dart
│       │   └── frontend_contract_test.dart
│       └── presentation/widgets/notification_card.dart
└── utils/
    └── time_utils.dart
```

---

## ۳) وابستگی‌ها (pubspec.yaml)

| پکیج | کاربرد |
|------|--------|
| flutter | SDK |
| cupertino_icons | آیکون‌ها |
| http | درخواست به بک‌اند |
| shared_preferences | ذخیرهٔ محلی |
| provider | مدیریت وضعیت |
| intl | تاریخ/زبان |

---

## ۴) جریان اپ و صفحات

- **IntroPage** → صفحهٔ اول (خوش‌آمد، ورود به اپ).
- **OnboardingPage** → ثبت نام/روش‌اندازی اولیه.
- **UserVerificationPage** → تأیید کاربر (مثلاً با secret_key).
- **ChatPage** / **ChatHistoryPage** → چت با صدی، تاریخچه، انتخاب زبان، ویجت‌های ورودی و حباب پیام.

تم از **AppTheme** (پس‌زمینه سفید، متن اصلی، آیکون غیرفعال، اپ‌بار بدون elevation) به‌صورت متمرکز تنظیم می‌شود.

---

## ۵) اتصال به بک‌اند

- **آدرس پیش‌فرض:** `http://91.107.168.130:8000` در `AppConfig.baseUrl`.
- **حالت لوکال:** با `useLocalMode = true` می‌توان بدون بک‌اند با پاسخ‌های mock اجرا کرد؛ برای اتصال واقعی `useLocalMode = false`.

---

## ۶) پلتفرم‌ها و CI

- **پوشه‌ها:** `android/`, `ios/`, `web/`, `windows/`, `linux/`, `macos/`.
- **GitHub Actions:** `.github/workflows/build-android.yml` — بیلد APK روی push به main/master/develop و workflow_dispatch؛ Flutter 3.24، Java 17.

---

## ۷) دارایی‌ها و مستندات

- **assets/images/** — لوگوها (sedi_logo، cosmic_sunrise_background و غیره).
- **docs/** — `lib_structure.txt`, `natural_conversation_flow.md`, `notification_contract.md`.
- **docs/FRONTEND_BACKEND_ALIGNMENT.md** — سند مرجع **هم‌راستایی فرانت با بک‌اند** (APIها، اسکیماها، وضعیت فعلی فرانت و پیشنهاد ساختار برای توسعه). برای بازنویسی و توسعهٔ فرانت بر اساس تغییرات بک‌اند از این سند استفاده شود.

---

## ۸) مرحلهٔ بعد: هم‌راستایی با بک‌اند

ساختار فرانت باید با توجه به تغییرات بک‌اند (نسخه ۲.۰.۱، روت‌های نهایی، اسکیماهای Pydantic) بازنویسی و توسعه داده شود. برای ادامهٔ کار با پرامپت‌های بعدی:

1. **سند مرجع:** `frontend/docs/FRONTEND_BACKEND_ALIGNMENT.md` — شامل تمام endpointهای فعال، Request/Response هر API، و مشخص کردن اینکه فرانت چه دارد و چه نیاز دارد (Health، Lifestyle، Conditions، Device/Devices، Notifications و غیره).
2. **پیشنهاد ساختار:** در همان سند، پیشنهاد شده برای هر دامنه DTO، repository/service و در صورت نیاز feature با data/logic/presentation اضافه شود و از یک ApiClient واحد با پشتیبانی توکن استفاده شود.

پرامپت‌های بعدی می‌توانند صریحاً به این سند ارجاع دهند (مثلاً «طبق FRONTEND_BACKEND_ALIGNMENT صفحهٔ سلامت را اضافه کن» یا «سرویس devices را هم‌راستا با بک‌اند پیاده کن»).

---

## ۹) خلاصه

| مورد | مقدار |
|------|--------|
| فریمورک | Flutter |
| ورود اولیه | IntroPage |
| صفحات اصلی | Intro، Onboarding، UserVerification، Chat |
| تم | AppTheme (Material، سفید/مشکی، سبز پسته‌ای) |
| بک‌اند | AppConfig.baseUrl، api_client |
| Build Android | `flutter build apk/appbundle`، workflow build-android.yml |

این سند ساختار فعلی و آخرین تغییرات مرتبط با معماری فرانت‌اند را خلاصه می‌کند. برای توسعهٔ بعدی و هم‌راستایی با بک‌اند، **frontend/docs/FRONTEND_BACKEND_ALIGNMENT.md** به‌عنوان سند اصلی استفاده شود.

# ساختار و ارتباطات صفحه Onboarding (پنجره یوزر نیم)

**تاریخ:** 2024-12-30  
**فایل اصلی:** `frontend/lib/features/onboarding/presentation/pages/onboarding_page.dart`

---

## 📁 فایل اصلی

### مسیر کامل:
```
frontend/lib/features/onboarding/presentation/pages/onboarding_page.dart
```

### کلاس اصلی:
- **`OnboardingPage`** - StatefulWidget
- **`_OnboardingPageState`** - State class

---

## 🔗 فایل‌های Import شده (وابستگی‌ها)

### 1. Flutter Core
```dart
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'dart:ui' as ui;
```
**استفاده:**
- `material.dart`: Widgets, Scaffold, Container, TextFormField, etc.
- `services.dart`: FilteringTextInputFormatter
- `dart:ui`: PlatformDispatcher برای تشخیص زبان سیستم

---

### 2. Core Theme
```dart
import '../../../../core/theme/app_theme.dart';
```
**فایل:** `frontend/lib/core/theme/app_theme.dart`

**استفاده:**
- `AppTheme.backgroundWhite` - رنگ پس‌زمینه سفید
- `AppTheme.metalGrey` - رنگ خاکستری (برای دکمه غیرفعال)
- `AppTheme.primaryBlack` - رنگ مشکی (برای دکمه فعال)
- `AppTheme.textPrimary` - رنگ متن اصلی
- `AppTheme.pistachioGreen` - رنگ سبز (برای آیکن تایید رمز)
- `AppTheme.radiusMedium` - شعاع گوشه‌ها (14px)

---

### 3. Core Utils
```dart
import '../../../../core/utils/user_profile_manager.dart';
```
**فایل:** `frontend/lib/core/utils/user_profile_manager.dart`

**استفاده:**
- `UserProfileManager.saveProfile(profile)` - ذخیره پروفایل کاربر
- `UserProfileManager.loadProfile()` - بارگذاری پروفایل کاربر

**عملکرد:**
- ذخیره/بارگذاری پروفایل از SharedPreferences
- مدیریت اطلاعات کاربر

---

### 4. Data Models
```dart
import '../../../../data/models/user_profile.dart';
```
**فایل:** `frontend/lib/data/models/user_profile.dart`

**استفاده:**
- `UserProfile` - مدل داده پروفایل کاربر
- فیلدها: name, securityPassword, userId, preferredLanguage, etc.

---

### 5. Core Config
```dart
import '../../../../core/config/app_config.dart';
```
**فایل:** `frontend/lib/core/config/app_config.dart`

**استفاده:**
- `AppConfig.useLocalMode` - بررسی حالت local/backend

---

### 6. Chat Service
```dart
import '../../../chat/chat_service.dart';
```
**فایل:** `frontend/lib/features/chat/chat_service.dart`

**استفاده:**
- `ChatService()` - سرویس ارتباط با backend
- `chatService.setupOnboarding(name, password, language)` - ثبت اطلاعات کاربر در backend

**عملکرد:**
- ارسال درخواست به backend برای ثبت اطلاعات
- دریافت user_id و پیام خوش‌آمدگویی

---

### 7. Chat Page
```dart
import '../../../chat/presentation/pages/chat_page.dart';
```
**فایل:** `frontend/lib/features/chat/presentation/pages/chat_page.dart`

**استفاده:**
- `ChatPage(initialMessage: ...)` - صفحه چت بعد از onboarding
- Navigation به این صفحه بعد از ثبت اطلاعات

---

### 8. Chat Widgets
```dart
import '../../../chat/presentation/widgets/sedi_header.dart';
```
**فایل:** `frontend/lib/features/chat/presentation/widgets/sedi_header.dart`

**استفاده:**
- `SediHeader(isThinking: false, isAlert: false, size: 134.4)` - لوگوی Sedi در بالای صفحه

---

## 📤 فایل‌هایی که از OnboardingPage استفاده می‌کنند

### 1. IntroPage
**فایل:** `frontend/lib/features/intro/presentation/pages/intro_page.dart`

**استفاده:**
```dart
import '../../../onboarding/presentation/pages/onboarding_page.dart';

// Navigation به OnboardingPage
Navigator.of(context).pushReplacement(
  _createCubeTransitionRouteToOnboarding(),
);

PageRouteBuilder _createCubeTransitionRouteToOnboarding() {
  return PageRouteBuilder(
    pageBuilder: (context, animation, secondaryAnimation) {
      return const OnboardingPage(); // ← استفاده از OnboardingPage
    },
    // ... transition animation
  );
}
```

**شرایط:**
- اگر کاربر onboarding را کامل نکرده باشد، از IntroPage به OnboardingPage می‌رود
- با transition animation (cube transition)

---

## 🔄 Flow Diagram

```
┌─────────────────┐
│   IntroPage     │
│  (صفحه اولیه)   │
└────────┬────────┘
         │
         │ Check: Has completed onboarding?
         │
    ┌────┴────┐
    │         │
   NO        YES
    │         │
    ▼         ▼
┌──────────────┐    ┌──────────────┐
│ OnboardingPage│    │  ChatPage    │
│ (یوزر نیم)    │    │  (صفحه چت)   │
└──────┬───────┘    └──────────────┘
       │
       │ User fills form
       │ (Name + Password)
       │
       │ Submit button tapped
       │
       ▼
┌─────────────────┐
│  ChatService    │
│  setupOnboarding│
└────────┬────────┘
         │
         │ Backend API Call
         │
         ▼
┌─────────────────┐
│ UserProfile     │
│ Manager.save()  │
└────────┬────────┘
         │
         │ Save to SharedPreferences
         │
         ▼
┌─────────────────┐
│ Navigator       │
│ pushReplacement │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   ChatPage      │
│ (with initial   │
│  message)       │
└─────────────────┘
```

---

## 📊 ساختار فایل OnboardingPage

### متغیرهای State:
```dart
final _formKey = GlobalKey<FormState>();
final _nameController = TextEditingController();
final _passwordController = TextEditingController();

bool _isPasswordValid = false;
bool _isFormValid = false;
bool _isSubmitting = false;
```

### متدهای اصلی:
1. **`_getSystemLanguage()`** - تشخیص زبان سیستم
2. **`_validatePassword()`** - اعتبارسنجی رمز (حداقل 6 کاراکتر)
3. **`_validateForm()`** - اعتبارسنجی فرم (نام + رمز)
4. **`_submitForm()`** - ارسال فرم و navigation
5. **`_buildNameSection()`** - ساخت بخش نام
6. **`_buildPasswordSection()`** - ساخت بخش رمز
7. **`_buildSubmitButton()`** - ساخت دکمه تایید

---

## 🗂️ ساختار دایرکتوری

```
frontend/lib/
├── features/
│   ├── onboarding/
│   │   └── presentation/
│   │       └── pages/
│   │           └── onboarding_page.dart  ← فایل اصلی
│   │
│   ├── intro/
│   │   └── presentation/
│   │       └── pages/
│   │           └── intro_page.dart  ← استفاده از OnboardingPage
│   │
│   └── chat/
│       ├── chat_service.dart  ← استفاده در OnboardingPage
│       └── presentation/
│           ├── pages/
│           │   └── chat_page.dart  ← Navigation به این صفحه
│           └── widgets/
│               └── sedi_header.dart  ← استفاده در OnboardingPage
│
├── core/
│   ├── theme/
│   │   └── app_theme.dart  ← استفاده در OnboardingPage
│   ├── utils/
│   │   └── user_profile_manager.dart  ← استفاده در OnboardingPage
│   └── config/
│       └── app_config.dart  ← استفاده در OnboardingPage
│
└── data/
    └── models/
        └── user_profile.dart  ← استفاده در OnboardingPage
```

---

## 🔌 ارتباطات Backend

### API Endpoint:
- **Method:** POST
- **URL:** `/api/interact/setup-onboarding` (از طریق ChatService)
- **Request Body:**
  ```json
  {
    "name": "javad",
    "security_password": "password123",
    "language": "fa"
  }
  ```
- **Response:**
  ```json
  {
    "user_id": 123,
    "name": "javad",
    "language": "fa",
    "message": "خوش آمدید..."
  }
  ```

---

## 💾 ذخیره‌سازی Local

### SharedPreferences:
- **Key:** `'user_profile'`
- **Format:** JSON
- **Data:** UserProfile object serialized

---

## 📝 خلاصه ارتباطات

### فایل‌های Import شده (8 فایل):
1. ✅ `app_theme.dart` - رنگ‌ها و استایل
2. ✅ `user_profile_manager.dart` - ذخیره/بارگذاری پروفایل
3. ✅ `user_profile.dart` - مدل داده
4. ✅ `app_config.dart` - تنظیمات
5. ✅ `chat_service.dart` - ارتباط با backend
6. ✅ `chat_page.dart` - صفحه بعدی
7. ✅ `sedi_header.dart` - لوگو
8. ✅ Flutter packages (material, services, ui)

### فایل‌های استفاده‌کننده (1 فایل):
1. ✅ `intro_page.dart` - Navigation به OnboardingPage

### ارتباطات Backend:
1. ✅ `ChatService.setupOnboarding()` - ثبت اطلاعات

### ارتباطات Local Storage:
1. ✅ `UserProfileManager.saveProfile()` - ذخیره پروفایل

---

## 🎯 نتیجه

**فایل اصلی:** `frontend/lib/features/onboarding/presentation/pages/onboarding_page.dart`

**وابستگی‌ها:** 8 فایل import شده

**استفاده‌کنندگان:** 1 فایل (IntroPage)

**ارتباطات:** Backend API + Local Storage

**Navigation:** IntroPage → OnboardingPage → ChatPage


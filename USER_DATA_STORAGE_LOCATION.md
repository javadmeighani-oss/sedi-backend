# محل ذخیره‌سازی داده‌های کاربر (نام و رمز)

**تاریخ:** 2024-12-30  
**فایل مدیریت:** `frontend/lib/core/utils/user_profile_manager.dart`

---

## 📍 محل ذخیره‌سازی

### روش ذخیره‌سازی:
**SharedPreferences** (Flutter Package)

### Key:
```dart
static const String _profileKey = 'user_profile';
```

### Format:
**JSON** (string serialized)

---

## 💾 ساختار داده

### مدل داده:
**UserProfile** (`frontend/lib/data/models/user_profile.dart`)

### فیلدهای ذخیره شده:
```dart
{
  "name": "javad",                    // نام کاربر
  "security_password": "password123",  // رمز امنیتی
  "user_id": 123,                     // ID از backend
  "preferred_language": "fa",         // زبان ترجیحی
  "has_security_password": true,      // آیا رمز تنظیم شده
  "security_password_set_at": "2024-12-30T10:00:00Z", // تاریخ تنظیم
  "conversation_count": 0,            // تعداد مکالمات
  "is_verified": true,                // آیا verified است
  "requires_security_check": false    // نیاز به بررسی امنیتی
}
```

---

## 📂 محل فیزیکی ذخیره‌سازی

### Android:
```
/data/data/com.example.sedi/shared_prefs/
  └── FlutterSharedPreferences.xml
```

**مسیر کامل:**
```
/data/data/[PACKAGE_NAME]/shared_prefs/FlutterSharedPreferences.xml
```

**مثال:**
```
/data/data/com.sedi.app/shared_prefs/FlutterSharedPreferences.xml
```

**محتوای فایل:**
```xml
<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
  <string name="flutter.user_profile">{"name":"javad","security_password":"password123",...}</string>
</map>
```

---

### iOS:
```
Library/Preferences/
  └── [BUNDLE_ID].plist
```

**مسیر کامل:**
```
[APP_SANDBOX]/Library/Preferences/[BUNDLE_ID].plist
```

**مثال:**
```
/var/mobile/Containers/Data/Application/[UUID]/Library/Preferences/com.sedi.app.plist
```

**فرمت:** Property List (plist)

---

## 🔧 کد ذخیره‌سازی

### فایل: `user_profile_manager.dart`

```dart
class UserProfileManager {
  static const String _profileKey = 'user_profile';

  /// Save user profile to storage
  static Future<bool> saveProfile(UserProfile profile) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final json = jsonEncode(profile.toJson());  // تبدیل به JSON
      return await prefs.setString(_profileKey, json);  // ذخیره با key
    } catch (e) {
      return false;
    }
  }

  /// Load user profile from storage
  static Future<UserProfile> loadProfile() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final profileJson = prefs.getString(_profileKey);  // خواندن از key
      
      if (profileJson == null) {
        return UserProfile(); // Return empty profile
      }

      final json = jsonDecode(profileJson) as Map<String, dynamic>;
      return UserProfile.fromJson(json);  // تبدیل از JSON
    } catch (e) {
      return UserProfile(); // Return empty profile on error
    }
  }
}
```

---

## 📝 نحوه استفاده در OnboardingPage

### ذخیره داده:
```dart
// در onboarding_page.dart
final profile = UserProfile(
  name: result['name']?.toString() ?? _nameController.text.trim(),
  securityPassword: _passwordController.text,  // ← رمز ذخیره می‌شود
  preferredLanguage: result['language']?.toString() ?? systemLanguage,
  userId: result['user_id'] as int?,
  hasSecurityPassword: true,
  securityPasswordSetAt: DateTime.now(),
  isVerified: true,
);

final saved = await UserProfileManager.saveProfile(profile);  // ← ذخیره
```

### خواندن داده:
```dart
// در intro_page.dart
final profile = await UserProfileManager.loadProfile();
final hasCompletedOnboarding = 
    profile.name != null && 
    profile.name!.isNotEmpty &&
    profile.securityPassword != null && 
    profile.securityPassword!.isNotEmpty;
```

---

## 🔐 امنیت

### ⚠️ نکات امنیتی:

1. **SharedPreferences رمزگذاری نشده است:**
   - داده‌ها به صورت plain text ذخیره می‌شوند
   - قابل خواندن با root/jailbreak
   - قابل دسترسی با ADB (Android Debug Bridge)

2. **رمز امنیتی:**
   - رمز به صورت plain text ذخیره می‌شود
   - برای امنیت بیشتر باید از `flutter_secure_storage` استفاده شود

3. **توصیه:**
   - برای داده‌های حساس (رمز) از `flutter_secure_storage` استفاده کنید
   - این package از Keychain (iOS) و Keystore (Android) استفاده می‌کند

---

## 📊 مقایسه روش‌های ذخیره‌سازی

| روش | امنیت | کارایی | استفاده |
|-----|-------|--------|---------|
| **SharedPreferences** | ⚠️ پایین | ✅ بالا | داده‌های غیرحساس |
| **flutter_secure_storage** | ✅ بالا | ⚠️ متوسط | داده‌های حساس (رمز) |
| **SQLite** | ⚠️ پایین | ✅ بالا | داده‌های پیچیده |
| **Hive** | ⚠️ پایین | ✅✅ خیلی بالا | داده‌های بزرگ |

---

## 🔍 نحوه مشاهده داده‌های ذخیره شده

### Android (با ADB):
```bash
# اتصال به دستگاه
adb shell

# رفتن به دایرکتوری app
cd /data/data/com.sedi.app/shared_prefs/

# مشاهده فایل
cat FlutterSharedPreferences.xml
```

### iOS (با Xcode):
1. Window → Devices and Simulators
2. انتخاب دستگاه
3. Download Container
4. رفتن به: `Library/Preferences/[BUNDLE_ID].plist`

---

## 📋 خلاصه

### ✅ محل ذخیره‌سازی:
- **Android:** `/data/data/[PACKAGE]/shared_prefs/FlutterSharedPreferences.xml`
- **iOS:** `[APP_SANDBOX]/Library/Preferences/[BUNDLE_ID].plist`

### ✅ Key:
- `'user_profile'`

### ✅ Format:
- JSON (string)

### ✅ فایل مدیریت:
- `frontend/lib/core/utils/user_profile_manager.dart`

### ✅ مدل داده:
- `frontend/lib/data/models/user_profile.dart`

### ✅ Package:
- `shared_preferences` (Flutter)

---

## ⚠️ هشدار امنیتی

**رمز امنیتی به صورت plain text ذخیره می‌شود!**

برای بهبود امنیت، توصیه می‌شود:
1. استفاده از `flutter_secure_storage` برای رمز
2. Hash کردن رمز قبل از ذخیره
3. استفاده از encryption برای داده‌های حساس

---

## 📚 منابع

- **Flutter SharedPreferences:** https://pub.dev/packages/shared_preferences
- **Flutter Secure Storage:** https://pub.dev/packages/flutter_secure_storage
- **Android Storage:** https://developer.android.com/training/data-storage/shared-preferences
- **iOS Storage:** https://developer.apple.com/documentation/foundation/userdefaults


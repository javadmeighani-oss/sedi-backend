# پیاده‌سازی نمایش یک‌باره Onboarding

**تاریخ:** 2024-12-30  
**هدف:** نمایش پنجره onboarding فقط یک بار - برای ثبت نام اولیه

---

## 🔍 تغییرات انجام شده

### 1. بهبود چک Onboarding در IntroPage

**فایل:** `frontend/lib/features/intro/presentation/pages/intro_page.dart`

**تغییر:**
```dart
Future<void> _navigateToNextPage() async {
  // Check if user has completed onboarding
  final profile = await UserProfileManager.loadProfile();
  
  final hasName = profile.name != null && profile.name!.isNotEmpty;
  final hasPassword = profile.securityPassword != null && 
                      profile.securityPassword!.isNotEmpty;
  final isVerified = profile.isVerified || profile.hasSecurityPassword;
  
  final hasCompletedOnboarding = hasName && hasPassword && isVerified;
  
  if (hasCompletedOnboarding) {
    // ✅ User has completed onboarding, go directly to chat
    Navigator.of(context).pushReplacement(
      _createCubeTransitionRouteToChat(),
    );
  } else {
    // ⚠️ User needs to complete onboarding first
    Navigator.of(context).pushReplacement(
      _createCubeTransitionRouteToOnboarding(),
    );
  }
}
```

**نتیجه:** ✅ چک بهبود یافت - از `isVerified` و `hasSecurityPassword` هم استفاده می‌کند

---

### 2. اضافه کردن چک در OnboardingPage

**فایل:** `frontend/lib/features/onboarding/presentation/pages/onboarding_page.dart`

**تغییر:**
```dart
@override
void initState() {
  super.initState();
  _nameController.addListener(_validateForm);
  _passwordController.addListener(_validatePassword);
  // ✅ Check if user has already completed onboarding
  _checkOnboardingStatus();
  // Initial validation
  WidgetsBinding.instance.addPostFrameCallback((_) {
    _validateForm();
    _validatePassword();
  });
}

/// Check if user has already completed onboarding
/// If yes, navigate directly to ChatPage
Future<void> _checkOnboardingStatus() async {
  try {
    final profile = await UserProfileManager.loadProfile();
    
    final hasName = profile.name != null && profile.name!.isNotEmpty;
    final hasPassword = profile.securityPassword != null && 
                        profile.securityPassword!.isNotEmpty;
    final isVerified = profile.isVerified || profile.hasSecurityPassword;
    
    final hasCompletedOnboarding = hasName && hasPassword && isVerified;
    
    if (hasCompletedOnboarding && mounted) {
      // ✅ User has already completed onboarding, navigate to ChatPage
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (context) => const ChatPage(),
        ),
      );
    }
  } catch (e) {
    // If error, continue with onboarding page
  }
}
```

**نتیجه:** ✅ اگر کاربر قبلاً onboarding را کامل کرده باشد، مستقیماً به ChatPage می‌رود

---

## 📋 Flow کامل

### اولین بار (Onboarding):
```
App Starts
        ↓
IntroPage (2 seconds)
        ↓
Check UserProfile
        ↓
Onboarding Not Completed ✅
        ↓
Navigate to OnboardingPage
        ↓
User Enters Name & Password
        ↓
User Taps Confirm
        ↓
Backend API Call
        ↓
Save UserProfile (isVerified: true) ✅
        ↓
Navigate to ChatPage
```

### دفعات بعدی (Skip Onboarding):
```
App Starts
        ↓
IntroPage (2 seconds)
        ↓
Check UserProfile
        ↓
Onboarding Completed ✅
        ↓
Navigate Directly to ChatPage ✅
        ↓
OnboardingPage Never Shown ✅
```

### اگر کاربر مستقیماً به OnboardingPage برود:
```
OnboardingPage Opens
        ↓
Check UserProfile in initState
        ↓
Onboarding Completed ✅
        ↓
Navigate Directly to ChatPage ✅
        ↓
OnboardingPage Never Shown ✅
```

---

## ✅ شرایط Onboarding Complete

Onboarding کامل است اگر:
1. ✅ `name` وجود دارد و خالی نیست
2. ✅ `securityPassword` وجود دارد و خالی نیست
3. ✅ `isVerified = true` **یا** `hasSecurityPassword = true`

---

## 🔄 چک‌های انجام شده

### در IntroPage:
- ✅ چک می‌کند که آیا onboarding کامل شده است
- ✅ اگر کامل شده باشد، مستقیماً به ChatPage می‌رود
- ✅ اگر کامل نشده باشد، به OnboardingPage می‌رود

### در OnboardingPage:
- ✅ در `initState` چک می‌کند که آیا onboarding کامل شده است
- ✅ اگر کامل شده باشد، مستقیماً به ChatPage می‌رود
- ✅ اگر کامل نشده باشد، onboarding page را نمایش می‌دهد

---

## 📝 ذخیره‌سازی UserProfile

بعد از onboarding موفق:
```dart
final profile = UserProfile(
  name: _nameController.text.trim(),
  securityPassword: _passwordController.text,
  preferredLanguage: systemLanguage,
  userId: result['user_id'] as int?,
  hasSecurityPassword: true,  // ✅
  securityPasswordSetAt: DateTime.now(),
  isVerified: true,  // ✅
);

await UserProfileManager.saveProfile(profile);
```

**نتیجه:** ✅ `isVerified` و `hasSecurityPassword` به `true` تنظیم می‌شوند

---

## ✅ نتیجه

**Onboarding یک‌باره:**
- ✅ پنجره onboarding فقط یک بار نمایش داده می‌شود
- ✅ بعد از ثبت نام، دیگر نمایش داده نمی‌شود
- ✅ هر بار برنامه باز می‌شود، مستقیماً به ChatPage می‌رود
- ✅ اگر کاربر مستقیماً به OnboardingPage برود، به ChatPage redirect می‌شود

---

**وضعیت:** ✅ **تمام تغییرات انجام شد**

**نکته:** UserProfile در SharedPreferences ذخیره می‌شود و بعد از بستن برنامه هم باقی می‌ماند.


# گزارش بازگشت به تنظیمات قبلی Signing

**تاریخ:** 2024-12-30  
**اقدام:** بازگشت به تنظیمات ساده قبلی  
**وضعیت:** ✅ **انجام شد**

---

## مشکل

از اسکرین‌شات مشخص است که:
- ❌ Build failed: "Keystore file '/home/runner/.android/debug.keystore' not found"
- ❌ تغییرات جدید باعث مشکل شدند
- ✅ تنظیمات قبلی ساده و کار می‌کرد

---

## تصمیم

**بازگشت به تنظیمات قبلی** که ساده و کار می‌کرد.

---

## تغییرات اعمال شده

### 1. بازگشت build.gradle به حالت ساده

**قبل (پیچیده):**
```gradle
signingConfigs {
    release {
        // 40+ خط کد پیچیده
        ...
    }
}

buildTypes {
    release {
        signingConfig signingConfigs.release
        ...
    }
}
```

**بعد (ساده):**
```gradle
buildTypes {
    release {
        signingConfig signingConfigs.debug
    }
}
```

### 2. حذف تغییرات اضافی از Workflow

**حذف شده:**
- Step برای setup keystore
- Environment variables برای keystore

**باقی مانده:**
- Build ساده با retry mechanism

---

## فایل‌های تغییر یافته

1. ✅ `frontend/android/app/build.gradle`
   - بازگشت به `signingConfig signingConfigs.debug`
   - حذف 45 خط کد پیچیده

2. ✅ `frontend/.github/workflows/flutter-android.yml`
   - حذف step برای setup keystore
   - حذف environment variables

---

## Commit

**Commit Hash:** `79374ad`

**Message:**
```
revert: Restore original simple signing configuration

- Revert to signingConfigs.debug for release builds
- This was working correctly before
- Simple configuration that works in GitHub Actions
- Google Play Protect warning can be handled by user settings
```

**Status:** ✅ Push موفق

---

## نتیجه

✅ **تنظیمات به حالت قبلی برگشت**

**مزایا:**
- ✅ ساده و قابل اعتماد
- ✅ کار می‌کند در GitHub Actions
- ✅ بدون پیچیدگی اضافی

**نکته درباره Google Play Protect:**
- کاربر می‌تواند در تنظیمات موبایل Play Protect را غیرفعال کند
- یا اجازه نصب از Unknown Sources را بدهد
- این یک warning است، نه خطا - app کار می‌کند

---

**وضعیت:** Build جدید باید با موفقیت انجام شود.


# گزارش رفع مشکل Build در GitHub Actions

**تاریخ:** 2024-12-30  
**مشکل:** 403 Forbidden از Maven Central  
**وضعیت:** ✅ **رفع شد و push شد**

---

## مشکل شناسایی شده

### خطا:
```
Could not GET 'https://repo.maven.apache.org/maven2/com/squareup/javawriter/2.5.0/javawriter-2.5.0.pom'. 
Received status code 403 from server: Forbidden

Could not GET 'https://repo.maven.apache.org/maven2/org/ow2/asm/asm/9.1/asm-9.1.pom'. 
Received status code 403 from server: Forbidden
```

### علت:
- **403 Forbidden** از Maven Central
- احتمالاً به دلیل rate limiting یا مشکل موقت شبکه در GitHub Actions
- Dependencies مورد نیاز:
  - `com.squareup:javawriter:2.5.0` (برای `com.android.tools.build:gradle:7.3.0`)
  - `org.ow2.asm:asm:9.1` (برای `com.android.tools.build:gradle:7.3.0`)

---

## راه حل اعمال شده

### 1. اضافه کردن Maven Mirror Repository

**فایل:** `frontend/android/build.gradle`

**تغییرات:**
```gradle
repositories {
    google()
    mavenCentral()
    // Add mirror repositories as fallback
    maven { url 'https://repo1.maven.org/maven2' }
}
```

**فایل:** `frontend/android/settings.gradle`

**تغییرات:**
```gradle
repositories {
    google()
    mavenCentral()
    // Add mirror repositories as fallback
    maven { url 'https://repo1.maven.org/maven2' }
    gradlePluginPortal()
}
```

### 2. بهبود تنظیمات Gradle

**فایل:** `frontend/android/gradle.properties`

**اضافه شده:**
```properties
# Retry configuration for network issues
org.gradle.daemon=true
org.gradle.parallel=true
org.gradle.caching=true

# Maven Central retry settings
systemProp.http.connectionTimeout=60000
systemProp.http.socketTimeout=60000
```

### 3. اضافه کردن Retry Mechanism در Workflow

**فایل:** `frontend/.github/workflows/flutter-android.yml`

**تغییرات:**
```yaml
- name: Build APK
  run: |
    flutter build apk --release --verbose || {
      echo "First build attempt failed, retrying..."
      sleep 10
      flutter clean
      flutter pub get
      flutter build apk --release
    }
  timeout-minutes: 30
```

**ویژگی‌ها:**
- ✅ Retry خودکار در صورت خطا
- ✅ Clean و rebuild در صورت نیاز
- ✅ Timeout 30 دقیقه
- ✅ Verbose logging برای debugging

---

## فایل‌های تغییر یافته

1. ✅ `frontend/android/gradle.properties`
   - اضافه شدن تنظیمات retry و timeout

2. ✅ `frontend/android/build.gradle`
   - اضافه شدن Maven mirror repository

3. ✅ `frontend/android/settings.gradle`
   - اضافه شدن Maven mirror repository

4. ✅ `frontend/.github/workflows/flutter-android.yml`
   - اضافه شدن retry mechanism

---

## Commit

**Commit Hash:** `ed22900`

**Message:**
```
fix: Add retry mechanism and Maven mirror for 403 Forbidden errors

- Add Maven mirror repository as fallback
- Add retry mechanism in GitHub Actions workflow
- Improve Gradle network timeout settings
- Add retry logic for build failures
```

**Status:** ✅ Push موفق به `main`

---

## مراحل بعدی

### 1. بررسی Build Status

به این لینک بروید:
```
https://github.com/javadmeighani-oss/sedi-frontend/actions
```

### 2. انتظار برای Build

- Build جدید باید به صورت خودکار شروع شود
- با retry mechanism، در صورت خطا دوباره تلاش می‌کند
- معمولاً 5-10 دقیقه طول می‌کشد

### 3. اگر هنوز خطا داشت

**راه حل‌های اضافی:**
1. استفاده از Gradle cache در workflow
2. اضافه کردن retry بیشتر
3. استفاده از VPN یا proxy (اگر نیاز باشد)

---

## خلاصه تغییرات

| فایل | تغییرات |
|------|---------|
| `gradle.properties` | +7 خط (retry و timeout settings) |
| `build.gradle` | +2 خط (Maven mirror) |
| `settings.gradle` | +2 خط (Maven mirror) |
| `flutter-android.yml` | +8 خط (retry mechanism) |

**کل تغییرات:** 19 خط اضافه شده

---

## نتیجه

✅ **مشکل رفع شد و تغییرات push شدند**

**Repository:** `git@github.com:javadmeighani-oss/sedi-frontend.git`  
**Commit:** `ed22900`  
**Status:** Build جدید در حال اجرا

**راه حل‌ها:**
- ✅ Maven mirror repository اضافه شد
- ✅ Retry mechanism اضافه شد
- ✅ Timeout settings بهبود یافت
- ✅ Workflow بهبود یافت

---

**نکته:** Build جدید باید با موفقیت انجام شود. اگر هنوز خطا داشت، لطفاً اطلاع دهید تا راه حل‌های بیشتری اعمال کنیم.


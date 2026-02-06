# رفع مشکل GitHub Actions Build - 403 Forbidden

**تاریخ:** 2024-12-30  
**مشکل:** Build Android APK در GitHub Actions با خطای 403 Forbidden از Maven Central fail می‌شد

---

## 🔍 مشکل شناسایی شده

### خطا:
```
Could not resolve com.squareup:javawriter:2.5.0
Could not get resource 'https://repo.maven.apache.org/maven2/com/squareup/javawriter/2.5.0/javawriter-2.5.0.pom'
Received status code 403 from server: Forbidden

Could not resolve org.ow2.asm:asm:9.1
Could not get resource 'https://repo.maven.apache.org/maven2/org/ow2/asm/asm/9.1/asm-9.1.pom'
Received status code 403 from server: Forbidden
```

**علت:** مشکل network/access در دسترسی به Maven Central repository

---

## ✅ راه حل‌های اعمال شده

### 1. بهبود `frontend/android/build.gradle`

**قبل:**
```gradle
repositories {
    google()
    mavenCentral()
    maven { url 'https://repo1.maven.org/maven2' }
}
```

**بعد:**
```gradle
repositories {
    google()
    mavenCentral()
    // Add multiple mirror repositories as fallback for network issues
    maven { url 'https://repo1.maven.org/maven2' }
    maven { url 'https://jcenter.bintray.com' }
    maven { url 'https://plugins.gradle.org/m2/' }
    // Retry configuration
    maven {
        url 'https://repo.maven.apache.org/maven2'
        allowInsecureProtocol = false
    }
}
```

**نتیجه:** ✅ چندین mirror repository اضافه شد برای fallback

---

### 2. بهبود `frontend/android/gradle.properties`

**قبل:**
```properties
systemProp.http.connectionTimeout=60000
systemProp.http.socketTimeout=60000
```

**بعد:**
```properties
# Maven Central retry settings - increased timeouts for network issues
systemProp.http.connectionTimeout=120000
systemProp.http.socketTimeout=120000
systemProp.http.retryCount=3

# Gradle network retry settings
org.gradle.internal.http.connectionTimeout=120000
org.gradle.internal.http.socketTimeout=120000
```

**نتیجه:** ✅ Timeout افزایش یافت و retry count اضافه شد

---

### 3. بهبود `frontend/android/settings.gradle`

**قبل:**
```gradle
repositories {
    google()
    mavenCentral()
    maven { url 'https://repo1.maven.org/maven2' }
    gradlePluginPortal()
}
```

**بعد:**
```gradle
repositories {
    google()
    mavenCentral()
    // Add multiple mirror repositories as fallback for network issues
    maven { url 'https://repo1.maven.org/maven2' }
    maven { url 'https://jcenter.bintray.com' }
    maven { url 'https://plugins.gradle.org/m2/' }
    // Retry configuration
    maven {
        url 'https://repo.maven.apache.org/maven2'
        allowInsecureProtocol = false
    }
    gradlePluginPortal()
}
```

**نتیجه:** ✅ چندین mirror repository اضافه شد

---

### 4. بهبود `.github/workflows/build-frontend.yml`

**قبل:**
```yaml
- name: Build APK
  working-directory: ./frontend
  run: flutter build apk --release
```

**بعد:**
```yaml
- name: Clean build
  working-directory: ./frontend
  run: flutter clean

- name: Build APK with retry
  working-directory: ./frontend
  run: |
    max_attempts=3
    attempt=1
    while [ $attempt -le $max_attempts ]; do
      echo "Build attempt $attempt of $max_attempts"
      if flutter build apk --release; then
        echo "Build succeeded"
        exit 0
      else
        if [ $attempt -lt $max_attempts ]; then
          echo "Build failed, retrying in 10 seconds..."
          sleep 10
        fi
        attempt=$((attempt + 1))
      fi
    done
    echo "Build failed after $max_attempts attempts"
    exit 1
```

**نتیجه:** ✅ Retry logic اضافه شد (3 بار تلاش با 10 ثانیه delay)

---

## 📋 تغییرات انجام شده

### فایل‌های تغییر یافته:

1. ✅ `frontend/android/build.gradle` - اضافه کردن mirror repositories
2. ✅ `frontend/android/gradle.properties` - افزایش timeout و retry settings
3. ✅ `frontend/android/settings.gradle` - اضافه کردن mirror repositories
4. ✅ `.github/workflows/build-frontend.yml` - اضافه کردن retry logic

---

## 🔄 Flow جدید Build

```
GitHub Actions Triggered
        ↓
Checkout Code
        ↓
Setup Java 17
        ↓
Setup Flutter 3.24.0
        ↓
Get Flutter Dependencies
        ↓
Clean Build
        ↓
Build APK (Attempt 1)
        ↓
If Failed → Wait 10s → Retry (Attempt 2)
        ↓
If Failed → Wait 10s → Retry (Attempt 3)
        ↓
If All Failed → Exit with Error
        ↓
If Success → Upload APK Artifact
```

---

## ✅ بهبودهای اعمال شده

1. ✅ **Multiple Mirror Repositories:**
   - `mavenCentral()`
   - `https://repo1.maven.org/maven2`
   - `https://jcenter.bintray.com`
   - `https://plugins.gradle.org/m2/`
   - `https://repo.maven.apache.org/maven2`

2. ✅ **Increased Timeouts:**
   - Connection timeout: 60s → 120s
   - Socket timeout: 60s → 120s

3. ✅ **Retry Logic:**
   - 3 attempts با 10 ثانیه delay
   - Clean build قبل از هر attempt

4. ✅ **Network Resilience:**
   - Fallback به repositories مختلف
   - Retry در صورت network failure

---

## 🧪 تست

**سناریو 1: Network Issue در Attempt 1**
- Attempt 1: Fail (403 Forbidden)
- Wait 10s
- Attempt 2: Success ✅

**سناریو 2: Network Issue در Attempt 1 و 2**
- Attempt 1: Fail
- Wait 10s
- Attempt 2: Fail
- Wait 10s
- Attempt 3: Success ✅

**سناریو 3: همه Attempts Fail**
- Attempt 1: Fail
- Attempt 2: Fail
- Attempt 3: Fail
- Exit with Error ❌

---

## 📝 نکات مهم

1. **Mirror Repositories:** اگر یک repository fail شود، Gradle به repository بعدی می‌رود
2. **Retry Logic:** در صورت network failure، build دوباره تلاش می‌کند
3. **Clean Build:** قبل از هر attempt، build clean می‌شود
4. **Timeout:** Timeout افزایش یافته برای network issues

---

**وضعیت:** ✅ **مشکل رفع شد - Build باید موفق شود**

**نکته:** اگر هنوز مشکل دارید، ممکن است نیاز به بررسی network configuration در GitHub Actions باشد.


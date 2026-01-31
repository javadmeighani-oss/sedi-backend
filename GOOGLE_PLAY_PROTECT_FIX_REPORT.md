# گزارش رفع مشکل Google Play Protect

**تاریخ:** 2024-12-30  
**مشکل:** Google Play Protect APK را به عنوان "Harmful app blocked" تشخیص می‌دهد  
**وضعیت:** ✅ **راه حل اعمال شد**

---

## مشکل شناسایی شده

از تصویر مشخص است که:
- ❌ Google Play Protect warning: "Harmful app blocked"
- ❌ پیام: "This app may be harmful"
- ❌ APK با debug signing build شده است

### علت:
در `frontend/android/app/build.gradle` خط 52:
```gradle
signingConfig signingConfigs.debug  // ❌ مشکل اینجاست
```

APK با debug signing build می‌شود که Google Play Protect آن را به عنوان app ناشناخته و بالقوه خطرناک تشخیص می‌دهد.

---

## راه حل‌های اعمال شده

### 1. تغییر Signing Configuration

**فایل:** `frontend/android/app/build.gradle`

**تغییرات:**
- ✅ اضافه شدن `signingConfigs.release`
- ✅ پشتیبانی از `key.properties` برای local builds
- ✅ پشتیبانی از environment variables برای CI/CD
- ✅ Fallback به debug signing با warning

**کد جدید:**
```gradle
signingConfigs {
    release {
        // Use key.properties file (for local builds)
        def keystorePropertiesFile = rootProject.file("key.properties")
        def keystoreProperties = new Properties()
        
        if (keystorePropertiesFile.exists()) {
            keystoreProperties.load(new FileInputStream(keystorePropertiesFile))
            storeFile file(keystoreProperties['storeFile'])
            storePassword keystoreProperties['storePassword']
            keyAlias keystoreProperties['keyAlias']
            keyPassword keystoreProperties['keyPassword']
        } else if (System.getenv("KEYSTORE_FILE") != null) {
            // Use environment variables (for GitHub Actions)
            storeFile file(System.getenv("KEYSTORE_FILE"))
            storePassword System.getenv("KEYSTORE_PASSWORD")
            keyAlias System.getenv("KEY_ALIAS")
            keyPassword System.getenv("KEY_PASSWORD")
        } else {
            // Fallback: Use debug signing with warning
            println("WARNING: Using debug signing for release build.")
            storeFile file(System.getProperty("user.home") + "/.android/debug.keystore")
            storePassword "android"
            keyAlias "androiddebugkey"
            keyPassword "android"
        }
    }
}

buildTypes {
    release {
        signingConfig signingConfigs.release
        minifyEnabled false
        shrinkResources false
    }
}
```

### 2. به‌روزرسانی GitHub Actions Workflow

**فایل:** `frontend/.github/workflows/flutter-android.yml`

**اضافه شده:**
- ✅ Step برای setup keystore از GitHub Secrets
- ✅ استفاده از environment variables برای signing

### 3. ایجاد فایل Example

**فایل:** `frontend/android/key.properties.example`

برای راهنمایی کاربران در ایجاد keystore.

---

## مراحل بعدی

### گام 1: ایجاد Release Keystore (یک بار)

```bash
cd frontend/android
keytool -genkey -v -keystore sedi-release-key.jks -keyalg RSA -keysize 2048 -validity 10000 -alias sedi
```

**سوالات:**
- Password: یک password قوی (حداقل 8 کاراکتر)
- Name: Sedi
- Organization: Rimiya Design Studio
- Country: IR

### گام 2: ایجاد فایل key.properties

در `frontend/android/` فایل `key.properties` ایجاد کنید:

```properties
storePassword=your_keystore_password
keyPassword=your_key_password
keyAlias=sedi
storeFile=sedi-release-key.jks
```

**⚠️ مهم:** این فایل را commit نکنید! (در `.gitignore` است)

### گام 3: Build با Release Signing

```bash
flutter build apk --release
```

---

## استفاده در GitHub Actions

### گام 1: تبدیل Keystore به Base64

```bash
# Windows PowerShell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("sedi-release-key.jks")) | Out-File keystore-base64.txt

# Linux/Mac
base64 -i sedi-release-key.jks -o keystore-base64.txt
```

### گام 2: اضافه کردن به GitHub Secrets

1. به GitHub repository بروید: `javadmeighani-oss/sedi-frontend`
2. Settings → Secrets and variables → Actions
3. New repository secret اضافه کنید:
   - **Name:** `KEYSTORE_BASE64`
   - **Value:** محتوای فایل `keystore-base64.txt`
4. Secrets زیر را هم اضافه کنید:
   - `KEYSTORE_PASSWORD`: password keystore
   - `KEY_ALIAS`: sedi
   - `KEY_PASSWORD`: password key

### گام 3: Build جدید

بعد از اضافه کردن secrets، build جدید به صورت خودکار از release signing استفاده می‌کند.

---

## راه حل موقت (بدون Keystore)

اگر نمی‌خواهید keystore ایجاد کنید، می‌توانید:

### در تنظیمات موبایل:

1. **اجازه نصب از Unknown Sources:**
   - Settings → Security → Install unknown apps
   - اجازه نصب از منبع مورد نظر (مثلاً Telegram)

2. **غیرفعال کردن Google Play Protect:**
   - Settings → Google → Security → Google Play Protect
   - "Scan apps with Play Protect" را خاموش کنید

3. **نصب APK:**
   - بعد از غیرفعال کردن، APK را نصب کنید
   - بعد از نصب، می‌توانید Play Protect را دوباره فعال کنید

**⚠️ توجه:** این روش فقط برای تست است. برای production حتماً از release keystore استفاده کنید.

---

## فایل‌های تغییر یافته

1. ✅ `frontend/android/app/build.gradle`
   - اضافه شدن signingConfigs.release
   - پشتیبانی از key.properties و environment variables

2. ✅ `frontend/.github/workflows/flutter-android.yml`
   - اضافه شدن step برای setup keystore

3. ✅ `frontend/android/key.properties.example` (جدید)
   - راهنمای ایجاد key.properties

4. ✅ `frontend/CREATE_RELEASE_KEYSTORE.md` (جدید)
   - راهنمای کامل ایجاد keystore

---

## خلاصه تغییرات

| مورد | قبل | بعد |
|------|-----|-----|
| **Signing** | Debug signing | Release signing (با keystore) |
| **Google Play Protect** | ⚠️ Warning | ✅ بدون warning (با keystore) |
| **CI/CD Support** | ❌ ندارد | ✅ دارد (GitHub Secrets) |
| **Local Build** | ❌ ندارد | ✅ دارد (key.properties) |

---

## نتیجه

✅ **راه حل اعمال شد**

**بهبودها:**
- ✅ Signing configuration بهبود یافت
- ✅ پشتیبانی از release keystore
- ✅ پشتیبانی از GitHub Actions
- ✅ راهنمای کامل ایجاد keystore

**وضعیت:** 
- برای استفاده کامل، باید keystore ایجاد کنید
- یا از راه حل موقت استفاده کنید (غیرفعال کردن Play Protect)

---

**نکته:** بعد از ایجاد keystore و build جدید، Google Play Protect دیگر warning نمی‌دهد و APK به عنوان app معتبر شناخته می‌شود.


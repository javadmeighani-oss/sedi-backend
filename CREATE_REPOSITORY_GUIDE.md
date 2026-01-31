# راهنمای ایجاد Repository در GitHub

## ⚠️ Repository در GitHub وجود ندارد

برای push کردن کد، ابتدا باید repository را در GitHub ایجاد کنید.

## روش 1: ایجاد Repository از طریق وب GitHub

### مراحل:

1. **ورود به GitHub:**
   - به https://github.com بروید
   - وارد حساب کاربری `javadmeighani-oss` شوید

2. **ایجاد Repository جدید:**
   - روی دکمه **"+"** در بالای صفحه کلیک کنید
   - **"New repository"** را انتخاب کنید

3. **تنظیمات Repository:**
   - **Repository name:** `sedi` (یا هر نام دیگری که می‌خواهید)
   - **Description:** "Sedi - AI-based Health Assistant"
   - **Visibility:** Private یا Public (طبق نیاز)
   - **⚠️ مهم:** **DO NOT** initialize with README, .gitignore, or license
   - روی **"Create repository"** کلیک کنید

4. **کپی کردن URL:**
   - بعد از ایجاد، GitHub یک URL به شما می‌دهد
   - URL را کپی کنید (مثلاً: `https://github.com/javadmeighani-oss/sedi.git`)

5. **اجرای دستورات:**
   ```powershell
   cd "d:\Rimiya Design Studio\Sedi\software\Demo"
   git remote add origin https://github.com/javadmeighani-oss/sedi.git
   git branch -M main
   git push -u origin main
   ```

## روش 2: استفاده از GitHub CLI (اگر نصب دارید)

```powershell
# نصب GitHub CLI (اگر ندارید)
# winget install GitHub.cli

# ورود به GitHub
gh auth login

# ایجاد repository
gh repo create sedi --public --source=. --remote=origin --push
```

## روش 3: استفاده از Script

بعد از ایجاد repository در GitHub، این script را اجرا کنید:

```powershell
.\push-to-github.ps1 -RepoUrl "https://github.com/javadmeighani-oss/sedi.git"
```

---

## بعد از ایجاد Repository

بعد از اینکه repository را ایجاد کردید و URL را گرفتید، به من بگویید تا push را انجام دهم.

یا می‌توانید خودتان این دستورات را اجرا کنید:

```powershell
cd "d:\Rimiya Design Studio\Sedi\software\Demo"
git remote add origin YOUR_REPO_URL
git branch -M main
git push -u origin main
```

---

## نکات مهم

1. **Repository name:** می‌تواند `sedi`، `sedi-app`، `sedi-monorepo` یا هر نام دیگری باشد
2. **Organization:** اگر در organization هستید، می‌توانید repository را در organization ایجاد کنید
3. **Private vs Public:** برای پروژه‌های خصوصی، Private را انتخاب کنید

---

## بعد از Push موفق

1. ✅ کد در GitHub خواهد بود
2. ✅ GitHub Actions workflow به صورت خودکار اجرا می‌شود
3. ✅ APK از Actions tab قابل دانلود است


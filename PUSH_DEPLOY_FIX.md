# رفع خطای "An unexpected error occurred on our servers" و اطمینان از پوش و دیپلوی

## این خطا از کجا می‌آید؟

پیام **"An unexpected error occurred on our servers. Please try again, or contact support if the issue persists."** معمولاً از یکی از این موارد است:

| منبع | دلیل | راه‌حل |
|------|------|--------|
| **GitHub** | سرویس موقتاً down یا محدودیت درخواست | [status.github.com](https://www.githubstatus.com/) را چک کنید؛ چند دقیقه بعد دوباره push کنید. |
| **Git (محلی)** | فایل قفل `.git/index.lock` مانع عملیات گیت شده | قفل را حذف کنید (پایین همین بخش). |
| **احراز هویت** | SSH یا token منقضی/اشتباه | کلید SSH یا Personal Access Token را درست کنید و دوباره تست کنید. |
| **Cursor / IDE** | خطای داخلی هنگام اجرای دستور گیت | از ترمینال خارجی (PowerShell یا Git Bash) push کنید. |

---

## مرحله ۱: حذف قفل گیت (اگر push خطا می‌دهد)

اگر با `Unable to create index.lock` یا `Another git process seems to be running` مواجه شدید:

1. **Cursor، VS Code، و هر ترمینال باز در این پروژه را ببندید.**
2. یکی از این کارها را انجام دهید:

**روش A – PowerShell (Run as Administrator اگر دسترسی رد شد):**
```powershell
$lockPath = "D:\Rimiya Design Studio\Sedi\software\Demo\.git\index.lock"
if (Test-Path $lockPath) {
  Remove-Item -Force $lockPath
  Write-Host "index.lock removed."
} else {
  Write-Host "No index.lock found."
}
```

**روش B – دستی:**  
برو به پوشه `Demo\.git` و فایل `index.lock` را پاک کن.

3. دوباره دستورات پوش را اجرا کنید.

---

## مرحله ۲: پوش از ترمینال (بدون وابستگی به Cursor)

همه دستورات را از **روت پروژه** اجرا کنید:

```powershell
cd "D:\Rimiya Design Studio\Sedi\software\Demo"

# اختیاری: فقط بک‌اند و workflow
git add backend/
git add .github/
git add app/
git add requirements.txt
git add deployment/

# یا همه تغییرات
# git add -A

git status
git commit -m "Backend and deploy updates"
git push origin main
```

اگر باز هم خطا گرفتید، خروجی دقیق خطا را بفرستید (مثلاً `fatal: ...` یا پیام GitHub).

---

## مرحله ۳: تنظیمات گیت و اتصال به GitHub

- **بررسی remote:**
  ```powershell
  git remote -v
  ```
  باید چیزی شبیه `origin  git@github.com:javadmeighani-oss/sedi-backend.git` ببینید.

- **تست اتصال SSH به GitHub:**
  ```powershell
  ssh -T git@github.com
  ```
  اگر "Permission denied" یا "Could not resolve host" دیدید، کلید SSH یا شبکه را درست کنید.

- **در صورت استفاده از HTTPS و خطای احراز هویت:**  
  از [GitHub → Settings → Developer settings → Personal access tokens](https://github.com/settings/tokens) یک token بسازید و به‌جای پسورد استفاده کنید.

---

## مرحله ۴: دیپلوی بعد از پوش

- با **push به شاخه `main`**، workflow **"Deploy Sedi Backend to Cloud Server"** در تب **Actions** همان ریپو اجرا می‌شود.
- اگر push موفق بود ولی دیپلوی اجرا نشد، در **Actions** روی همان workflow برو و **Run workflow** (دستی) را بزن.
- در GitHub حتماً **Secret** با نام `SEDI_DEPLOY_KEY` (کلید SSH سرور) تنظیم شده باشد؛ وگرنه مرحله SSH در workflow با خطا مواجه می‌شود.

---

## تغییراتی که برای اطمینان از پوش و دیپلوی اعمال شده

1. **Workflow دیپلوی (`.github/workflows/deploy-backend.yml`):**
   - به `paths` مقدار `backend/**` اضافه شده تا با هر تغییر در `backend/` هم دیپلوی اجرا شود.
   - روی سرور، اگر پوش شما داخل پوشه `backend/` باشد، اسکریپت دیپلوی داخل همان `backend/` کار می‌کند (برای هر دو ساختار روت و زیرپوشه).

2. **این راهنما و اسکریپت:**  
   برای رفع قفل و انجام پوش از ترمینال تا حد ممکن پوش و دیپلوی قابل انجام باشند.

اگر بعد از این مراحل هنوز "An unexpected error" می‌بینید، بگویید دقیقاً در چه مرحله‌ای (پوش از Cursor، پوش از ترمینال، یا باز کردن GitHub) ظاهر می‌شود تا همان بخش را دقیق‌تر بررسی کنیم.

---

## اگر خطای `Invalid argument` یا `failed to insert into database` گرفتید

این معمولاً به خاطر قفل شدن پوشه `.git` است (آنتی‌ویروس، OneDrive، یا برنامهٔ دیگر):

1. **Cursor و هر ترمینال باز را ببندید.**
2. **PowerShell را Run as Administrator باز کنید** و اجرا کنید:
   ```powershell
   cd "D:\Rimiya Design Studio\Sedi\software\Demo"
   Remove-Item -Force .git\index.lock -ErrorAction SilentlyContinue
   Remove-Item -Force .git\objects\d4\tmp_obj_* -ErrorAction SilentlyContinue
   git add backend/ .github/ app/ requirements.txt deployment/ PUSH_DEPLOY_FIX.md scripts/
   git commit -m "Backend and deploy updates"
   git push origin main
   ```
3. اگر آنتی‌ویروس دارید، پوشه پروژه را موقتاً از اسکن واقع‌زمانی خارج کنید و دوباره امتحان کنید.

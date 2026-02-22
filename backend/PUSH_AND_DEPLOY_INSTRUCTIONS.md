# پوش و دیپلوی بک‌اند در گیتهاب

برای رفع خطای **"An unexpected error occurred on our servers"** و راهنمای کامل پوش و دیپلوی، فایل **`PUSH_DEPLOY_FIX.md`** در روت پروژه (Demo) را ببینید.

## اگر خطای `index.lock` می‌گیرید

۱. **همه برنامه‌هایی که از این پوشه گیت استفاده می‌کنند را ببندید** (Cursor، VS Code، Git GUI، ترمینالهای باز).
۲. فایل قفل را حذف کنید:
   - **PowerShell:**
     ```powershell
     Remove-Item -Force "D:\Rimiya Design Studio\Sedi\software\Demo\.git\index.lock" -ErrorAction SilentlyContinue
     ```
   - **یا از File Explorer** بروید به پوشه `.git` و فایل `index.lock` را پاک کنید.

## دستورات پوش و دیپلوی

از **روت پروژه** (پوشه Demo) اجرا کنید:

```powershell
cd "D:\Rimiya Design Studio\Sedi\software\Demo"

# فقط تغییرات بک‌اند را stage کنید
git add backend/

# کامیت
git commit -m "Release C: fix HTTP status masking (401/500), ingest logging, test script psql/rate-limit"

# پوش به گیتهاب (دیپلوی با push روی main اجرا می‌شود)
git push origin main
```

## بعد از پوش

- ریپو: **git@github.com:javadmeighani-oss/sedi-backend.git**
- با پوش روی شاخه `main`، workflow **Deploy Sedi Backend to Cloud Server** در تب **Actions** اجرا می‌شود و سرور `91.107.168.130` به‌روزرسانی می‌شود.
- در صورت نیاز می‌توانید از تب Actions همان workflow را به صورت دستی (**workflow_dispatch**) هم اجرا کنید.

## در صورت استفاده از اسکریپت آماده

```powershell
cd "D:\Rimiya Design Studio\Sedi\software\Demo\backend"
.\push-to-github.ps1 -RepoUrl "https://github.com/javadmeighani-oss/sedi-backend.git"
```

توجه: این اسکریپت فقط remote را تنظیم و `git push` می‌زند؛ قبل از آن حتماً `git add` و `git commit` را از روت پروژه انجام دهید.

---

## V1 Freeze – Device Ingestion Auth Mode

- **V1 production** should use **DB-token based** device auth: each device has a token stored in the DB (from `/devices/register`), and `POST /device/ingest` validates `X-DEVICE-TOKEN` against that store.
- **Recommended for production V1:** set **`DEVICE_AUTH_MODE=db_only`**. This ensures only registered devices can ingest events; no shared legacy token.
- **`legacy_only`** is for **legacy tests only** (e.g. shared `DEVICE_INGEST_TOKEN`). It must **not** be used in production.
- **`hybrid`** was used temporarily for transition/testing (try DB token first, then legacy if configured). For a clean V1 freeze, use **`db_only`** in production.

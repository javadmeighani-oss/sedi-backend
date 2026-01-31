# راهنمای Build فرانت در GitHub Actions

**تاریخ:** 2024-12-30  
**هدف:** Build کردن فرانت Flutter در GitHub Actions برای تست روی موبایل

---

## وضعیت فعلی

✅ **تغییرات فرانت commit شده‌اند:**
- Commit: `ab4fcd8` - "feat(frontend): Redesign chat UI with improved spacing and scroll"
- Commit: `85cc13c` - "chore: Trigger frontend build for mobile testing"

⚠️ **Remote تنظیم نشده است** - نیاز به تنظیم remote repository

---

## مراحل Build در GitHub Actions

### گام 1: تنظیم Remote Repository

ابتدا باید remote repository را تنظیم کنید:

```bash
# بررسی remote فعلی
git remote -v

# اگر remote وجود ندارد، اضافه کنید:
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git

# یا اگر از SSH استفاده می‌کنید:
git remote add origin git@github.com:YOUR_USERNAME/YOUR_REPO.git
```

### گام 2: Push تغییرات

```bash
# Push به remote
git push origin main

# یا اگر branch شما master است:
git push origin master
```

### گام 3: Trigger Workflow

**روش 1: Push خودکار (پیشنهادی)**

بعد از push کردن تغییرات در `frontend/**`، workflow به صورت خودکار trigger می‌شود.

**روش 2: Manual Trigger**

1. به GitHub repository بروید
2. به تب **Actions** بروید
3. workflow **"Build Flutter Frontend"** را انتخاب کنید
4. روی **"Run workflow"** کلیک کنید
5. branch را انتخاب کنید (معمولاً `main`)
6. روی **"Run workflow"** کلیک کنید

---

## Workflow Configuration

**فایل:** `.github/workflows/build-frontend.yml`

**Trigger Conditions:**
- ✅ Push به `main`, `master`, یا `develop`
- ✅ تغییرات در `frontend/**`
- ✅ Manual trigger با `workflow_dispatch`

**Jobs:**
1. **build-android** - Build Android APK (فعال)
2. **build-ios** - Build iOS (غیرفعال)

---

## دانلود APK

بعد از اتمام build:

1. به تب **Actions** در GitHub بروید
2. روی run اخیر کلیک کنید
3. در بخش **Artifacts**، **sedi-android-apk** را پیدا کنید
4. روی **Download** کلیک کنید
5. APK را روی موبایل Android نصب کنید

---

## دستورات سریع

```bash
# تنظیم remote (یک بار)
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git

# Push تغییرات
git push origin main

# بررسی وضعیت
git status
git log --oneline -5
```

---

## Troubleshooting

### مشکل: Remote تنظیم نشده
**راه حل:** Remote را با دستور بالا تنظیم کنید

### مشکل: Workflow trigger نمی‌شود
**راه حل:** 
- بررسی کنید که تغییرات در `frontend/**` push شده باشند
- یا از manual trigger استفاده کنید

### مشکل: Build fail می‌شود
**راه حل:**
- به تب Actions بروید و خطا را بررسی کنید
- معمولاً مشکلات dependency یا configuration است

---

## خلاصه تغییرات فرانت

### تغییرات UI:
- ✅ کاهش طول چت باکس 10%
- ✅ کوچک کردن لوگو 20%
- ✅ افزایش فضای چت‌ها 20%
- ✅ اسکرول دستی
- ✅ آیکن برگشت به آخرین چت
- ✅ بازنویسی history page

### فایل‌های تغییر یافته:
- `frontend/lib/features/chat/presentation/pages/chat_history_page.dart`
- `frontend/lib/features/chat/presentation/pages/chat_page.dart`
- `frontend/lib/features/chat/presentation/widgets/input_bar.dart`

---

**نکته:** بعد از تنظیم remote و push، GitHub Actions به صورت خودکار build را شروع می‌کند و APK را برای دانلود آماده می‌کند.


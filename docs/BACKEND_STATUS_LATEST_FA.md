# گزارش آخرین وضعیت بک‌اند

تاریخ گزارش: 2026-02-25  
مخزن: `javadmeighani-oss/sedi-backend`  
شاخه فعال: `main`

## 1) وضعیت Git و Push

- شاخه `main` با `origin/main` همگام است.
- آخرین بررسی push: `Everything up-to-date`
- نتیجه: در حال حاضر commit جدیدی برای ارسال به GitHub وجود ندارد.

## 2) وضعیت تغییرات محلی مرتبط با بک‌اند

- در مسیر `backend` تغییر tracked باز مشاهده نشد.
- یک فایل untracked در مسیر بک‌اند وجود دارد:
  - `backend/_gitlog.txt`
- سایر تغییرات باز فعلی عمدتا مربوط به `frontend` و `docs` هستند.

## 3) آخرین کامیت‌های مهم بک‌اند/CI

- `9ce8062` — `ci(backend): consolidate mandatory V1 subset step`
- `2183e2e` — `ci(backend): adjust freeze workflow checks`
- `3906965` — `ci(backend): split V1 freeze checks into explicit steps`
- `a4c26c9` — `tests(contracts): ignore framework validation schemas in snapshot`
- `6869f13` — `tests(contracts): stabilize OpenAPI snapshot ordering for CI`
- `bcf4971` — `tests(contracts): refresh OpenAPI snapshot for ops status`

## 4) وضعیت CI بک‌اند (فایل تست اجباری)

فایل: `.github/workflows/ci-backend-tests.yml`

واقعیت فعلی CI (Source of Truth):
- زیربخش Freeze در CI شامل این موارد است:
  - `backend/tests/contracts/`
  - `backend/tests/acceptance/test_release_d.py`
  - `backend/tests/acceptance/test_decision_engine_scenarios_v1.py`
  - `backend/tests/acceptance/test_kc_apply_answer_profile_answer_fallback.py`
- تست‌های اختیاری فقط در صورت وجود فایل اجرا می‌شوند:
  - `backend/tests/acceptance/test_device_ingestion_c1.py`
  - `backend/tests/acceptance/test_notification_prefs_v1.py` یا `backend/tests/acceptance/test_notifications_prefs_v1.py`
- این Workflow در وضعیت فعلی تست‌های E2E (`test_auth_e2e_v1.py` / `test_devices_e2e_v1.py`) را اجرا نمی‌کند.
- مهاجرت‌ها روی Postgres موقت (`postgres:15`) و با `TEST_DATABASE_URL` انجام می‌شوند و `DATABASE_URL` فقط در همان مرحله migration ست می‌شود.

## 5) وضعیت Deploy بک‌اند

فایل: `.github/workflows/deploy-backend.yml`

تریگرهای موجود:
- `push` روی `main` (با path filter برای مسیرهای بک‌اند)
- `workflow_dispatch` برای اجرای دستی

موانع فعلی اجرای deploy از این سشن:
- ابزار `gh` (GitHub CLI) روی این محیط در دسترس نیست.
- SSH مستقیم به سرور از این سشن با `Permission denied (publickey,password)` رد می‌شود.

## 6) جمع‌بندی اجرایی

- وضعیت کد بک‌اند روی GitHub: به‌روز و همگام.
- وضعیت CI موردنظر: Freeze subset مطابق واقعیت فعلی workflow اعمال و مستند شده است.
- وضعیت Deploy: آماده اجرا از GitHub Actions، اما نیازمند دسترسی احراز هویت GitHub/SSH در محیط اجرا.

## 7) اقدام بعدی پیشنهادی

برای اجرای نهایی deploy:
1. ورود به GitHub با اکانت دارای دسترسی به ریپو
2. اجرای دستی Workflow زیر روی شاخه `main`:
   - `Deploy Sedi Backend to Cloud Server`
3. بررسی لاگ مراحل `Test SSH connection` و `Deploy to Server`

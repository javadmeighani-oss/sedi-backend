# گزارش اصلی اجرای سکشن ۱۵ صدی (Gate 4 — بازرسی، صحت‌سنجی توپولوژی، ممیزی، و ثبت باگ‌ها)

**تاریخ:** ۲۰۲۶-۰۷-۱۴ (به‌روزشده: CI-Extend validation @ `eaf6634`)
**هدف:** این سند منبع حقیقت دائمی سکشن ۱۵ است. شامل P1، P2A، و Package 15-I0-B8 (اصلاح schema `reply`، idempotency تعاملی B8، migration بدون اجرا، ثبت الزامات حافظه و موتور دانش هفتگی) — بدون commit/push/اجرای migration/تست محلی.

**قانون به‌روزرسانی:** هر وظیفهٔ آیندهٔ Cursor در سکشن ۱۵ باید پیش از اعلام اتمام، همین فایل را به‌روز کند.

---

## ۰) Package 15-P1 — foundation تداوم backend (اجرا شده، بدون commit)

### مجوز این پکیج
- ایجاد یک worktree پاک backend و یک feature branch
- اعمال patch تأییدشده و hash-verified سیشن ۱۴-A1
- اصلاح بدهی تست B4 و پوشش تست B6/B7 در محدوده A1
- تحقیق فقط‌ایستای B8 + طرح بستن migration (بدون ایجاد/اجرای migration)
- به‌روزرسانی همین لاگ داخل worktree جدید

### غیرمجاز (و انجام‌نشده)
- commit / push / merge / rebase / cherry-pick / amend / force-push
- deploy / migration / تغییر DB / فعال‌سازی feature flag
- تغییر کد محصول frontend / پیاده‌سازی بصری Gate 4 / هوشمندی Section 14-B
- تست محلی / pytest / Python / Docker / Flutter / build / analyze / نصب وابستگی
- دست‌کاری worktree کثیف Demo یا حذف لاگ منبع در Demo

### تأیید صریح زمان‌بندی محصول
- **پیاده‌سازی بصری Gate 4 پس از پیاده‌سازی هوشمندی (Sedi intelligence) زمان‌بندی می‌شود.**
- تصمیم‌های آیندهٔ Gate 4 تأیید شده توسط جواد:
  - رنگ ریسک آرام و کنترل‌شده
  - گزینه‌های TALK_LATER برای کاربر: ۱ ساعت، ۴ ساعت، فردا، یا زمان دلخواه
  - صفحهٔ تنظیمات canonical Gate 4
  - localization کامل fa/ar/en
  - حداقل touch target برابر ۴۸dp
  - جریان‌های یادآور: عمومی، دارو، پزشک، آزمایش/بررسی

### Preflight شواهد P1
| مورد | نتیجه |
|------|--------|
| CWD اولیه | `D:\Rimiya Design Studio\Sedi\software\Demo` |
| HEAD اولیه Demo | `a78bd7e…` روی `feature/section10/backend-foundations-ci` (کثیف؛ **دست‌نخورده**) |
| `origin/main` via ls-remote | `89b79ad3fc20236a23ffae65fd868aafb60843e8` — برابر base مصوب |
| وجود SHA پایه محلی | بله |
| وجود از قبلِ مسیر worktree هدف | خیر |
| وجود از قبلِ branch هدف | خیر |
| SHA-256 patch | `b11abaa21a83f0c5d2663561886993077a6ac2c936e6132e2f5744522e0b51c6` — مطابق |

### Worktree و branch جدید
| مورد | مقدار |
|------|--------|
| مسیر | `D:\Rimiya Design Studio\Sedi\software\Demo-wt-section15-backend` |
| Branch | `feature/section15/backend-continuity-foundation` (بدون upstream) |
| Base / HEAD فعلی (بدون commit) | `89b79ad3fc20236a23ffae65fd868aafb60843e8` |
| لاگ هدف | `…\Demo-wt-section15-backend\docs\SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md` |
| لاگ منبع در Demo کثیف | **حفظ شد و حذف/ویرایش نشد** |

### نتیجهٔ اعمال patch A1
- `git apply --check`: موفق (exit 0)
- `git apply` (بدون stage/commit): موفق (exit 0)
- دامنه: فقط backend A1 (بدون frontend / بدون workflow / بدون Section 10)
- وضعیت کد پس از اصلاحات P1: **implemented but unverified pending GitHub Actions**
- تست محلی اجرا نشد؛ CI هنوز اجرا نشده

### ماتریس قابلیت A1 (پس از اعمال)
| قابلیت | وضعیت |
|--------|--------|
| JWT-only memory history | پیاده |
| رد caller-supplied `user_id` | پیاده (422) |
| timezone resolution/validation + fallback | پیاده |
| naive timestamps as UTC | پیاده |
| daily / ISO weekly / monthly / yearly + `timezone` + `current_group_key` | پیاده |
| safe `gate4_metadata` / ownership / sanitized chat context | پیاده |
| `sedi://` deeplink امن | پیاده |
| channel routing بدون دادهٔ حساس در metadata | پیاده |

### فایل‌های تغییر/جدید در P1 (uncommitted)
**از patch A1 (modified):**
`memory.py`, `notifications.py`, `schemas/memory.py`, `schemas/notification.py`, `policy_prefs_bridge.py`, `push_payload.py`, `openapi_v1_snapshot.json`, `test_gate4c_interaction_events.py`

**از patch A1 (new):**
`inbox_metadata.py`, `test_gate4_push_channel_routing_v1.py`, `test_memory_history_timezone_v1.py`, `test_notification_inbox_gate4_v1.py`

**اصلاحات اضافی P1:**
`test_notification_api_b2.py` (B4), گسترش `test_gate4_push_channel_routing_v1.py` (B6/B7), همین لاگ

### B4 — اصلاح تست‌های legacy بدون JWT
- همهٔ تماس‌های موفق اکنون Bearer JWT مالک دارند (`create_access_token` مطابق الگوی `test_notifications_auth_v1.py`)
- assertionهای ownership به **HTTP 403** تقویت شدند (هماهنگ با router؛ دیگر `200 + ok:false` ضعیف نیست)
- تست صریح unauthenticated → **401** اضافه شد
- auth ضعیف نشد؛ endpointها عمومی نشدند؛ skip/xfail/حذف assertion انجام نشد
- وضعیت: **implemented but unverified pending GitHub Actions**

### B6 — پوشش precedence کانال
رفتار مصوب از پیاده‌سازی فعلی `build_gate4_android_notification_options` (بدون تغییر سیاست خاموش):
1. `risk=critical` → `sedi_critical` (حتی با `health_status`)
2. category سلامت **یا** `risk=high` **یا** `priority`∈{high,critical} → `sedi_health`
   ⇒ reminder با priority/risk بالا → **`sedi_health` نه sedi_reminder** (مستند در تست)
3. reminder عادی → `sedi_reminder`
4. engagement عادی → `sedi_default`
وضعیت: **implemented but unverified pending GitHub Actions**

### B7 — fallback زبان نامعتبر → `en`
- پیاده‌سازی موجود (`normalize_language` / `normalize_push_language`) صحیح بود؛ تست‌های `de` و metadata/push labels انگلیسی اضافه شد
- تغییر کد سرویس لازم نبود
- وضعیت: **implemented but unverified pending GitHub Actions**

### B8 — تحقیق race dedupe + طرح بستن (بدون migration در این پکیج)
**یافته:** `create_chat_message_event` با الگوی select-then-insert؛ جدول `interaction_events` فقط index دارد؛ migration head فعلی: `049_section10_kb_embeddings_memory_governance`؛ migration مبدأ جدول: `037_gate4c_interaction_events`.

**هویت یکتایی صحیح (از منطق سرویس، حدس نیست):** برای `event_type='chat_message'` با `source_notification_id IS NOT NULL`، یکتایی معنایی =
`(user_id, source_notification_id, conversation_id)` که `conversation_id` می‌تواند NULL باشد (PostgreSQL UNIQUE ساده برای NULL کافی نیست).

**وضعیت B8:** `blocked with evidence — separate migration authorization required`

**طرح بستن پیشنهادی دقیق:**
1. **جدول/ستون‌ها:** `interaction_events(user_id, source_notification_id, conversation_id, event_type)`
2. **ایندکس‌های پیشنهادی (دو partial unique):**
   - `uq_interaction_events_chat_msg_with_conv` UNIQUE (`user_id`, `source_notification_id`, `conversation_id`) WHERE `event_type='chat_message' AND source_notification_id IS NOT NULL AND conversation_id IS NOT NULL`
   - `uq_interaction_events_chat_msg_null_conv` UNIQUE (`user_id`, `source_notification_id`) WHERE `event_type='chat_message' AND source_notification_id IS NOT NULL AND conversation_id IS NULL`
3. **Preflight duplicates:**
   `SELECT user_id, source_notification_id, conversation_id, COUNT(*) … WHERE event_type='chat_message' AND source_notification_id IS NOT NULL GROUP BY 1,2,3 HAVING COUNT(*)>1`
   و معادل برای NULL conversation.
4. **پاکسازی:** نگه‌داشتن `MIN(id)` در هر گروه تکراری؛ حذف/آرشیو بقیه پس از تأیید جواد.
5. **Upgrade:** ایجاد دو ایندکس concurrent-safe طبق استاندارد repo پس از cleanup.
6. **Downgrade:** drop دو ایندکس.
7. **Model:** `__table_args__` انعکاس ایندکس‌ها (بدون تغییر معنای سایر event_typeها).
8. **Service:** حفظ lookup؛ روی `IntegrityError`، re-select و return existing (نه crash).
9. **تست concurrency:** دو insert هم‌زمان / threaded با expect یک row.
10. **ریسک rollback / production:** نیاز backup، preflight duplicate count صفر، maintenance window، تأیید جداگانهٔ migration+deploy.

### یافته‌های امنیتی/صحت اضافی در محدوده A1
- مشکل جدیدی که در محدودهٔ A1 نیاز به fix بدون migration داشته باشد و اصلاح‌نشده بماند یافت نشد.
- fallback زبان و precedence کانال با تست پوشش داده شد.
- `user_id` داخل FCM data payload (Gate4E قدیمی) خارج از تغییر تک‌خطی A1 روی health_status است؛ تغییر آن نیاز محصول/قرارداد جدا دارد → **approval blocker ثبت‌شده، نه deferred**.

### `git diff --check`
- روی فایل‌های tracked تغییر‌یافته: **تمیز (exit 0)**

### گام بعدی پس از review جواد
1. تأیید صریح commit روی `feature/section15/backend-continuity-foundation`
2. سپس push با تأیید جدا + GitHub Actions backend
3. پکیج جدا برای B8 migration پس از تأیید
4. سپس Package 15-P2 (Frontend A2 روی base پاک) — بدون merge شاخه validation
5. پیاده‌سازی بصری Gate 4 **بعد از** intelligence

---

## ۱) قوانین الزام‌آور گردش‌کار پروژه

1. همهٔ تغییرات کد در Cursor انجام می‌شود.
2. هر پیاده‌سازی، commit، push، merge، deploy، migration، فعال‌سازی feature flag، و ساخت APK نیازمند تأیید صریح و جداگانهٔ جواد است.
3. تست محلی frontend یا backend مجاز نیست.
4. محیط رسمی تست و build: GitHub Actions است.
5. استقرار production فقط پس از سبز بودن CI و تأیید جداگانهٔ جواد.
6. هیچ باگ، شکست، هشدار، رفتار ناقص، یا لبهٔ ناامن نباید خاموش/پنهان شود.
7. هر مسئلهٔ کشف‌شده تا اصلاح یا اثبات مسدودکنندهٔ خارجی پیگیری می‌شود.
8. شاخهٔ validation نباید مستقیماً وسیلهٔ یکپارچه‌سازی feature باشد.
9. worktree کثیف برای یکپارچه‌سازی استفاده نمی‌شود.
10. موفقیت E2E production قبل از تست هم‌زمان backend و frontend ادعا نمی‌شود.

---

## ۲) SHAها و commitهای مصوب مرجع

### Backend A1
- **Base SHA مصوب:** `89b79ad3fc20236a23ffae65fd868aafb60843e8`
  پیام: `fix(ci): correct production pg_dump backup invocation (#51)`
- **Worktree پاک قبلی:** `D:\Rimiya Design Studio\Sedi\software\Demo-section14a1-clean`
- **Patch:** `section14a1-review.patch` (در همان worktree)
- **SHA-256 مورد انتظار:** `b11abaa21a83f0c5d2663561886993077a6ac2c936e6132e2f5744522e0b51c6`
- **SHA-256 اندازه‌گیری‌شده:** `b11abaa21a83f0c5d2663561886993077a6ac2c936e6132e2f5744522e0b51c6` — **مطابق**

### Frontend پایه و A2
- **Frontend approved base:** `452b3e4e160922468ecb843187e300fcc03f2436`
  پیام: `fix(frontend): redesign gate3 horizontal equalizer`
- **شاخه validation A2 (نباید مستقیم merge شود):** `feature/frontend/section14a2-validation`
- **سه commit منبع یکپارچه‌سازی (به این ترتیب):**
  1. `d69b2faee51c35d5770e31061c724a740162e336` — `feat(frontend): connect gate4 notifications to continuous chat`
  2. `9da6202f11ea196d14c32b800373b47a42e1a851` — `style(frontend): format section14a2 files`
  3. `110c533430ee81e1d572d758f436fc8216c85c82` — `fix(frontend): correct same-day history DTO import`
- **commitهای فقط-validation که نباید وارد feature شوند:**
  - `ce6da1bc37cd4f8201ddf5c80e025844983194e7`
  - `1764af604bcfa4843bd335d9bc9feb01456b902c`
  - `60573666b12e0b795b75c8a59dfd6cb12453fc1a`
  - `0e507ce54f2213b9b7c511cbd307aa639ebe6003`
  - `549764b1eba2234db6447bd76ed286db059dfc6b`

### مرجع تاریخی validation A2 (فرض سبز بودن وضعیت فعلی نیست)
- GitHub Actions run: `29308601832`
- Workflow SHA: `110c533430ee81e1d572d758f436fc8216c85c82`
- Scoped A2 tests: ۲۷ پاس
- Full frontend suite: ۳۱۹ پاس، ۲۶ شکست از پیش موجود
- رگرسیون جدید در آن نقطه: صفر
- Debug APK: موفق

---

## ۳) وضعیت فعلی مخزن / worktree (بازرسی فقط‌خواندنی)

| مورد | مقدار |
|------|--------|
| CWD | `D:\Rimiya Design Studio\Sedi\software\Demo` |
| Repository root | `D:/Rimiya Design Studio/Sedi/software/Demo` |
| Branch فعلی | `feature/section10/backend-foundations-ci` |
| HEAD | `a78bd7e13868109a8a7edc500cff0558bc661a29` — `fix(section10): correct vitals monitoring state precedence` |
| وضعیت worktree اصلی | **کثیف** — ده‌ها فایل اصلاح‌شده/untracked (شامل تغییرات A1-مانند backend، فایل‌های frontend Gate3، آیکون‌ها، اسناد، zipها، `.cursor/` و …) |
| Remotes | `origin` → `javadmeighani-oss/sedi-backend.git` ؛ `frontend` → `javadmeighani-oss/sedi-frontend.git` |

### Worktree list
| مسیر | HEAD | Branch | وضعیت |
|------|------|--------|--------|
| `Demo` | `a78bd7e` | `feature/section10/backend-foundations-ci` | **کثیف** — نامرتبط با یکپارچه‌سازی Gate4/A1/A2 |
| `Demo-section14a1-clean` | `89b79ad` (detached) | — | **کثیف**: patch A1 به‌صورت uncommitted اعمال‌شده + فایل‌های patch |
| `Demo-section14a2-clean` | `110c533` | `feature/frontend/section14a2-validation` | **کثیف جزئی**: فقط untracked شواهد CI/patch؛ درخت محصول commit‌شده تمیز |
| `Demo-wt-frontend-gate3-finalization` | `452b3e4` | `feature/frontend/gate3-finalization` | تقریباً تمیز؛ یک سند untracked |
| `Demo-wt-section10-migration-safety` | `80e8f57` | `fix/section10/pg-dump-backup-command` | تمیز از نظر status کوتاه |

### وجود اشیاء محلی
- Backend A1 base، Frontend base، سه commit A2، و پنج commit validation: **همگی به‌صورت local commit موجودند.**

### Remote HEAD (بدون fetch)
- `origin` HEAD / `main`: `89b79ad3…` — برابر base مصوب A1؛ ref محلی `origin/main` هم‌تراز است.
- `origin` branchهای frontend در همان remote monorepo:
  - `feature/frontend/gate3-finalization` → `452b3e4…`
  - `feature/frontend/section14a2-validation` → `110c533…`
- Local branch `main` روی `a8790ee…` است و **۳ commit پشت** `origin/main` است → ref محلی `main` کهنه است.
- Remote جداگانهٔ `frontend`: `main`/`HEAD` روی `cdc37c9…` که **به‌صورت object محلی موجود نیست** → tracking محلی `frontend/main` (`4433b13…`) کهنه است. branchهای Gate3/A2 روی این remote دیده نشدند (روی `origin` هستند).

### توپولوژی / merge-base
- `origin/main` == A1 base == `89b79ad`.
- Frontend base `452b3e4` ancestorِ نوک A2 `110c533` است.
- ترتیب واقعی تاریخ: `452b3e4` → (۵ commit فقط-CI) → `d69b2fa` → `549764b`(CI) → `9da6202` → `110c533`.
- بین `452b3e4` و `0e507ce` فقط `.github/workflows/frontend_android_debug.yml` تغییر کرده (محصول frontend یکسان است).
- بین `d69b2fa` و `549764b` فقط همان workflow.
- A1 **جد نیاکان** HEAD فعلی بخش ۱۰ نیست (شاخه‌ها واگرا هستند: `HEAD...origin/main` ≈ ۵ در برابر ۳).
- Merge-base فعلی `HEAD` و `origin/main`: `a8790ee`.

**نتیجه preflight:** worktree اصلی برای یکپارچه‌سازی **ناامن** است. یکپارچه‌سازی آینده باید روی worktreeهای پاک جدید از `origin/main` (backend) و `452b3e4` (frontend) با cherry-pick سه commit محصولی انجام شود.

---

## ۴) وضعیت Backend A1

| بررسی | نتیجه |
|--------|--------|
| وجود patch | بله — در `Demo-section14a1-clean\section14a1-review.patch` (۳۱۷۲۷ بایت) |
| تطابق SHA-256 | بله |
| `git apply --check` روی WT فعلی | جلو: شکست (چون تغییر قبلاً اعمال شده)؛ معکوس (`-R`): **موفق** → محتوای WT با patch نسبت به HEAD هم‌خوان است |
| اعمال روی base تمیز | با شواهد reverse-check و هم‌ترازی HEAD=`89b79ad`، patch برای اعمال روی base تمیز سازگار است؛ در این وظیفه اعمال نشد |
| فایل‌های نامرتبط در patch | خیر — فقط مسیرهای backend Gate4/memory/notifications/tests/OpenAPI |

### فایل‌های patch
**تغییر یافته:**
- `backend/app/routers/memory.py`
- `backend/app/routers/notifications.py`
- `backend/app/schemas/memory.py`
- `backend/app/schemas/notification.py`
- `backend/app/services/gate4/policy_prefs_bridge.py`
- `backend/app/services/gate4/push_payload.py`
- `backend/tests/contracts/snapshots/openapi_v1_snapshot.json`
- `backend/tests/test_gate4c_interaction_events.py`

**جدید:**
- `backend/app/services/gate4/inbox_metadata.py`
- `backend/tests/test_gate4_push_channel_routing_v1.py`
- `backend/tests/test_memory_history_timezone_v1.py`
- `backend/tests/test_notification_inbox_gate4_v1.py`

### پوشش قابلیت‌ها (از محتوای patch / WT A1)
| قابلیت | وضعیت در A1 |
|--------|-------------|
| JWT-only memory history | پیاده‌سازی‌شده (`_reject_legacy_user_id_query`، هویت از token) |
| رد caller-supplied `user_id` | پیاده‌سازی‌شده |
| اعتبارسنجی timezone + fallback | پیاده‌سازی‌شده (`resolve_validated_user_timezone`) |
| گروه‌بندی daily/weekly/monthly/yearly | پیاده‌سازی‌شده |
| `current_group_key` | پیاده‌سازی‌شده |
| ISO week-year | پیاده‌سازی‌شده (`isocalendar`) |
| `gate4_metadata` امن برای inbox | پیاده‌سازی‌شده (`inbox_metadata.py` — بدون body/context_json) |
| اعتبارسنجی مالکیت notification | پوشش در inbox isolation + assertهای موجود |
| chat context امن | metadata inbox بدون تزریق body/context |
| مسیریابی کانال notification | `push_payload` + تست‌های channel routing جدید |

**Drift:** محتوای A1 روی `origin/main`/`89b79ad` به‌عنوان commit موجود نیست؛ فقط به‌صورت dirty در worktree A1 (و نسخه‌های مشابه dirty در worktree اصلی Demo) دیده می‌شود. روی شاخهٔ بخش ۱۰ واگرایی تاریخچه وجود دارد.

**وضعیت بسته:** آماده برای پیاده‌سازی/commit پس از تأیید جواد — هنوز commit/push نشده.

---

## ۵) وضعیت Frontend A2

### دامنهٔ هر commit
1. **d69b2fa** — ۲۷ مسیر محصولی (router، FCM، قرارداد Gate4، launch context/store، DTOها، chat_controller، inbox، main، تست `section14a2_continuity_test.dart` و …). والد: `0e507ce` (validation).
2. **9da6202** — فقط format روی فایل‌های A2. والد: `549764b` (validation فقط-workflow).
3. **110c533** — یک فایل: `same_day_history_mapper.dart` (اصلاح import DTO).

Validation commits فقط `.github/workflows/frontend_android_debug.yml` را لمس می‌کنند و باید از یکپارچه‌سازی feature حذف شوند.

### `git apply --check` روی base `452b3e4` (worktree gate3-finalization)
- Patch commit1 به‌تنهایی: **موفق (exit 0)**
- Commit2/3 به‌تنهایی: شکست مورد انتظار (وابسته به commit1)
- چون بین base و والدهای validation فقط workflow فرق دارد، مسیر امن: cherry-pick ترتیبی سه commit محصولی روی `452b3e4` پاک (نه merge شاخه validation)

### پوشش قابلیت‌های A2 (در نوک `110c533`)
| قابلیت | وضعیت |
|--------|--------|
| بازیابی تاریخ همان‌روز | بله (`_restoreSameDayHistory` + mapper) |
| درخواست history بدون `user_id` | بله (`fetchHistory` JWT-only) |
| مصرف timezone/`current_group_key` | بله (DTO + تست) |
| dedupe + ترتیب زمانی | بله (inbox و history mapper) |
| سرکوب intro وقتی history همان‌روز هست | بله |
| عدم POST هنگام restore | بله (فقط GET history) |
| `NotificationLaunchContext` امن | بله (بدون title/body) |
| TTL ۲۴ساعته pending | بله |
| تداوم Gate1→2→3 context | مسیر router/OTP/intro/main wired |
| lifecycle `source_notification_id` نوبت اول | بله |
| حفظ pending برای timeout/5xx | بله |
| پاک‌سازی روی success/403/404 | بله |
| اکشن‌های متعارف Gate4 | بله |
| جلوگیری duplicate local در foreground/background | بله (`osWillDisplayRemoteNotification`) |
| سازگاری کانال legacy | بله |

**باقی‌مانده داخل A2:** `_userId` در `chat_history_page.dart` هنوز ست می‌شود ولی به `fetchHistory` پاس داده نمی‌شود → هشدار analyzer محتمل. Inbox همچنان `user_id` query را برای list/mark-read/feedback می‌فرستد. مسیر legacy like/dislike در DTO/service باقی است.

---

## ۶) ماتریس ممیزی محصولی Frontend Gate 4

مرجع ممیزی: وضعیت نوک A2 (`110c533`) به‌علاوهٔ شکاف‌های محصولی کلی نسبت به نیاز کامل Gate4. وضعیت «جاری روی worktree اصلی Demo» عقب‌تر است و فایل‌های launch context A2 را ندارد.

| # | قابلیت | وضعیت | مالکیت بستن | قرارداد backend موجود؟ |
|---|--------|--------|-------------|-------------------------|
| 1 | Inbox Gate4 | پیاده‌سازی جزئی — `NotificationInboxPage` + wrapper legacy؛ placeholder Gate4 فقط redirect | Frontend | بله (list/unread) |
| 2 | کارت اعلان | پیاده‌سازی جزئی — کارت‌های bordered/shadow؛ نه همسو با زبان بصری Gate3 pale olive | Frontend | بله |
| 3 | read/unread | پیاده‌سازی‌شده (optimistic mark-read) | Frontend+Backend | بله |
| 4 | loading/empty/error/retry | پیاده‌سازی جزئی — loading/empty/error+retry هست؛ offline اختصاصی ضعیف | Frontend | — |
| 5 | detail state | جزئی — bottom sheet؛ صفحهٔ جزئیات جدا نیست | Frontend | — |
| 6 | ACK_THANKS / NOT_NOW / TALK_LATER / OPEN_CHAT | پیاده‌سازی‌شده در inbox + local actions + قرارداد | FE+BE | بله (feedback) |
| 7 | ناوبری امن Gate4→Gate3 | پیاده‌سازی‌شده (pending store + goToHeart) | Frontend | chat continuity BE لازم |
| 8 | تنظیمات اعلان | جزئی — sheet محلی در `chat_page`؛ صفحهٔ Gate4 settings مستقل نیست | FE؛ همگام‌سازی prefs BE ناقص/نامشخص در UI Gate4 | prefs/quiet hours در BE وجود دارد |
| 9 | درخواست مجوز OS + بازیابی deny | جزئی — `requestPermission` در main؛ UI بازیابی deny اختصاصی Gate4 نیست | Frontend + device | — |
| 10 | enable/disable دسته | جزئی — channel toggles محلی؛ نه کنترل category کامل محصولی Gate4 | FE+BE | prefs/policy |
| 11 | quiet hours | جزئی — محلی در تنظیمات چت؛ یکپارچگی UI Gate4 ناقص | FE+BE | بله (policy bridge) |
| 12 | timezone کاربر | جزئی در history/A1؛ UI تنظیم timezone داخل Gate4 نیست | FE+BE | memory/prefs |
| 13 | زمان ترجیحی اعلان | backend دارد؛ UI Gate4 کامل نیست | FE+BE | daily_notification_time |
| 14 | ساخت reminder | ناپیاده در Gate4؛ یادآور دارو در Gate3 health_care | FE+BE | نیاز قرارداد واضح creation |
| 15 | medication reminder | جزئی در Gate3 health؛ تحویل push سمت BE/scheduler | FE Gate3 + BE | medication schedules |
| 16 | doctor appointment reminder | **ناپیاده / بدون قرارداد UI واضح** | FE+BE (قرارداد لازم) | نامشخص — اختراع endpoint ممنوع |
| 17 | examination/test reminder | **ناپیاده / بدون قرارداد UI واضح** | FE+BE | نامشخص |
| 18 | صداهای متمایز کانال | جزئی — local service sound keys؛ assetهای کامل تأیید نشدند | FE+device | channel options BE |
| 19 | رفتار foreground | پیاده‌سازی‌شده (local mirror + dedupe) | Frontend | — |
| 20 | رفتار background | جزئی + محدودیت شناخته‌شده notification+data | FE+BE delivery mode | data-only توصیه |
| 21 | terminated | مسیر launch parser/pending؛ نیاز تأیید فیزیکی | FE+device | — |
| 22 | جلوگیری duplicate local | پیاده‌سازی‌شده | Frontend | — |
| 23 | کانال‌های Android چهارگانه | پیاده‌سازی‌شده + legacy map | Frontend | BE routing در A1 |
| 24 | RTL/LTR fa/ar/en | جزئی — برچسب اکشن‌ها localized؛ UI inbox هنوز رشته‌های انگلیسی hardcode | Frontend | language در metadata |
| 25 | کامل بودن localization | ناقص برای inbox/settings strings | Frontend | — |
| 26 | دسترس‌پذیری / touch target | **باگ/ریسک** — action chips با `shrinkWrap`/`minimumSize: zero` | Frontend | — |
| 27 | افشای دادهٔ حساس | خوب در launch context؛ عنوان/بدنه در UI inbox نمایش داده می‌شود (انتظار محصولی)؛ logs FCM باید مراقبت شوند | FE+BE | safe metadata |
| 28 | feature flag | flags سمت BE؛ FE flag gating اختصاصی Gate4 دیده نشد | BE+FE | feature_flags.py |
| 29 | placeholder / مسیر مرده / duplicate | `Gate4NotificationsPlaceholderPage`؛ دو مسیر inbox (`notifications` و wrapper `notification`)؛ تنظیمات در chat_page؛ like/dislike legacy | Frontend | — |
| 30 | مالکیت capabilityهای گم‌شده | scheduler/push = Backend؛ نمایش/بازخورد/مجوز/prefs UI/باز کردن chat = Frontend؛ ساخت reminderهای تخصصی بدون قرارداد = مسدود تا تعریف API توسط backend موجود | — | اختراع endpoint ممنوع |

---

## ۷) ماتریس بستن باگ‌ها و بدهی تست

وضعیت‌های مجاز فقط: `not started` | `ready for implementation` | `blocked with evidence` | `fixed but unverified` | `verified`

| ID | موضوع | طبقه‌بندی | شواهد | فایل‌های متأثر | اثر کاربر | شدت | اصلاح پیشنهادی | تست لازم | مالک | وضعیت |
|----|--------|-----------|--------|----------------|-----------|------|----------------|-----------|------|--------|
| B1 | هشدار unused `_userId` در `chat_history_page.dart` | confirmed bug (static/analyzer) | فیلد set می‌شود؛ به `fetchHistory` پاس نمی‌شود (A2 tip) | `chat_history_page.dart` | نویز analyzer؛ گیجی مالکیت هویت | Low | حذف فیلد یا استفادهٔ معتبر فقط برای gate auth UI | تست ویجت/analyze CI | Frontend | ready for implementation |
| B2 | `user_id` query در list/mark-read/feedback inbox | confirmed bug / integration risk | `notifications_service.dart` هنوز `user_id` می‌فرستد | `notifications_service.dart`, repository | وابستگی به query ناسازگار با hardening JWT | High | حذف query؛ تکیه بر Bearer؛ هم‌تراز A1 auth | تست قرارداد API + FE unit | FE (+BE اگر API عوض شود) | ready for implementation |
| B3 | مسیرهای Like/Dislike باقی‌مانده | confirmed missing cleanup | `legacyLiked`, `sendLegacyFeedback`, map like→ACK | feedback DTO/service، contract | دوگانگی UI/قرارداد؛ سردرگمی | Med | حذف UI/مسیرهای زنده legacy؛ نگه داشتن فقط normalize ورودی قدیمی | تست نرمال‌سازی + نبود ویجت like | Frontend | ready for implementation |
| B4 | حدود ۱۰ تست API اعلان بدون Bearer | test debt | در P1 اصلاح شد: JWT مالک + تست 401 + ownership→403 | `test_notification_api_b2.py` | شکست CI یا پوشش دروغین | High | انجام‌شده در P1 (منتظر Actions) | CI backend | Backend/CI | implemented but unverified pending GitHub Actions |
| B5 | ۲۶ شکست تاریخی frontend suite | test debt | گزارش run `29308601832`؛ فهرست دقیق تست‌ها در این بازرسی بازیابی نشد | وابسته به suite | پنهان‌کننده رگرسیون | High | فهرست دقیق از Actions → بستن تک‌به‌تک | CI frontend | Frontend/CI | blocked with evidence (نیاز بازیابی فهرست از Actions؛ بدون fetch/اجرای تست محلی) |
| B6 | تست precedence کانال | test debt | در P1 پوشش بحرانی/reminder+high/health/reminder/default افزوده شد | `test_gate4_push_channel_routing_v1.py`, `push_payload.py` | رگرسیون مسیریابی کانال | Med | انجام‌شده در P1 (منتظر Actions) | backend unit | Backend/CI | implemented but unverified pending GitHub Actions |
| B7 | تست fallback زبان نامعتبر → English | test debt | پیاده‌سازی صحیح بود؛ تست `de`→`en` + labels انگلیسی در P1 افزوده شد | `push_payload.py`, channel/i18n tests | برچسب/زبان اشتباه | Med | انجام‌شده در P1 (منتظر Actions) | backend unit | Backend/CI | implemented but unverified pending GitHub Actions |
| B8 | race پنجره dedupe interaction event بدون unique DB | confirmed bug / security-ish integrity | در I0-B8: partial unique `(user_id, source_notification_id)` + savepoint + fail-closed preflight؛ migration ایجاد شد اجرا نشد | `interaction_event_service.py`, `050_…idempotency.py`, model | رویداد تکراری timeline | Med | اجرا پس از backup+SQL preflight+تأیید | concurrency + migration tests | Backend | implemented but unverified pending GitHub Actions / migration execution blocked pending approval |
| B9 | TALK_LATER ثابت ۴ ساعت | confirmed product constraint | جواد گزینه‌های ۱س/۴س/فردا/دلخواه را تأیید کرد؛ پیاده‌سازی API/UI هنوز نیاز مجوز جدا | `notification_contract.py`, feedback_policy | تعویق کوتاه/غیروابسته به ترجیح کاربر | Med | طراحی قرارداد prefs/defer قابل انتخاب کاربر پس از تأیید پیاده‌سازی | feedback_policy + FE settings | Backend+Frontend | blocked with evidence (نیاز مجوز پیاده‌سازی/احتمالاً migration prefs) |
| B10 | محدودیت native action روی FCM notification+data | environment-dependent verification | کامنت صریح در `fcm_setup.dart` background handler | `fcm_setup.dart`, delivery BE | دکمه‌های اکشن در پس‌زمینه ممکن است کار نکنند | High | تحویل data-only + تأیید فیزیکی | E2E دستگاه | BE delivery + FE + device | blocked with evidence (نیاز تأیید حالت payload + دستگاه) |
| B11 | touch-target کوچک اکشن‌های inbox | confirmed bug (a11y) | `minimumSize: Size.zero`, `shrinkWrap` | `notification_inbox_page.dart` | سختی لمس | Med | حداقل ۴۸dp؛ همسو Gate3 | widget/a11y test | Frontend | ready for implementation |
| B12 | Inbox UI سفید نه pale olive + hardcode انگلیسی | confirmed missing implementation | Scaffold `backgroundWhite`؛ رشته‌های EN | inbox page | ناهمخوانی برند/RTL | Med | همسوسازی با پیشنهاد طراحی سکشن ۱۵ پس از تأیید جواد |golden/l10n | Frontend | ready for implementation |
| B13 | باگ‌های ناشی از drift main کثیف vs bases | integration risk | Demo اصلی dirty و روی section10؛ A1/A2 commit‌نشده یا mergeنشده | worktree Demo | یکپارچه‌سازی روی درخت اشتباه | Critical | کار فقط روی worktree پاک جدید | — | Process | ready for implementation (فرآیندی) |
| B14 | Local `main` / `frontend/main` کهنه | environment-dependent | `main` ۳ پشت origin؛ object `cdc37c9` محلی نیست | refs | تصمیم اشتباه توپولوژی | Med | قبل از کار آینده ls-remote؛ fetch فقط با تأیید جواد | — | Process | not started |
| B15 | A1/A2 هنوز در production/main ادغام نشده‌اند | integration risk | origin/main بدون A1؛ FE base بدون سه commit | — | ویژگی‌ها به کاربر نمی‌رسند | High | پکیج‌های جدا پس از تأیید | Actions gates | FE+BE | not started |

هیچ موردی «deferred» علامت نخورده است.

---

## ۸) ریسک‌های امنیت / حریم خصوصی

1. ارسال ادامهٔ `user_id` در queryهای inbox در کنار JWT — سطح حملهٔ اشتباه هویت / ناسازگاری hardening.
2. نبود uniqueness در DB برای dedupe interaction events — یکپارچگی timeline.
3. نمایش title/body در UI inbox مورد انتظار است؛ اما `NotificationLaunchContext` درستاً از ذخیرهٔ body خودداری می‌کند — حفظ شود.
4. لاگ‌های FCM/debug نباید payload حساس بنویسند (بازرسی نقطه‌ای لازم در پیاده‌سازی بعدی).
5. metadata inbox A1 عمداً context_json را حذف می‌کند — حفظ قرارداد.

---

## ۹) تصمیم‌های تأیید‌شده توسط جواد (تا این وظیفه)

- قوانین گردش‌کار سکشن ۱۵ و منابع SHA/A2 به‌عنوان مرجع مصوب وظیفه.
- ممنوعیت merge مستقیم شاخه validation.
- Package 15-P1: worktree/branch پاک، اعمال A1، اصلاح B4/B6/B7، تحقیق B8 — بدون commit/push.
- زمان‌بندی: پیاده‌سازی بصری Gate 4 **پس از** intelligence.
- تصمیم‌های آینده Gate 4: رنگ ریسک آرام؛ TALK_LATER ∈ {1h, 4h, tomorrow, custom}؛ settings page canonical؛ l10n کامل fa/ar/en؛ touch≥48dp؛ reminderهای general/medication/doctor/examination.

---

## ۱۰) تغییرات انجام‌شده در Package 15-P1

- ایجاد worktree/branch پاک از `89b79ad`.
- کپی لاگ به worktree جدید (منبع Demo حفظ شد).
- اعمال hash-verified A1 patch (uncommitted).
- اصلاح B4 در `test_notification_api_b2.py`.
- گسترش تست‌های channel/language (B6/B7).
- طرح بستن B8 بدون migration.
- به‌روزرسانی همین لاگ.

## ۱۱) تغییرات انجام‌نشده / ممنوع باقی‌مانده

- هیچ commit/push/merge/deploy/migration/feature flag
- هیچ تست محلی / CI
- هیچ frontend / UI Gate 4
- پیاده‌سازی TALK_LATER چندگزینه‌ای و B8 schema

---

## ۱۲) مسدودکننده‌های فعلی با شواهد

1. **Worktree اصلی کثیف و روی شاخه نامرتبط** — برای یکپارچه‌سازی ممنوع.
2. **A1 فقط به‌صورت patch/dirty** — نیاز تأیید جواد برای commit روی base پاک از `89b79ad`/`origin/main`.
3. **A2 روی شاخه validation با commitهای CI آمیخته** — باید cherry-pick سه‌تایی؛ merge شاخه ممنوع.
4. **Remote `frontend/main` object محلی نیست** — ref کهنه؛ تصمیم توپولوژی با احتیاط.
5. **فهرست دقیق ۲۶ شکست frontend** — بدون بازیابی از Actions مسدود برای بستن موردی.
6. **TALK_LATER ۴ساعته و reminderهای تخصص بدون قرارداد UI** — نیاز تصمیم/قرارداد جواد/backend موجود.
7. **E2E فیزیکی notification+data** — محدودیت محیطی.

---

## ۱۳) دروازه‌های لازم GitHub Actions

1. Backend: suite پس از commit A1 روی base پاک (شامل تست‌های جدید timezone/inbox/channel + اصلاح تست‌های JWT).
2. Frontend: suite کامل + scoped A2 پس از cherry-pick سه commit روی `452b3e4` (بدون workflow validation مگر تأیید جداگانه).
3. Android debug APK workflow روی شاخهٔ integration تمیز.
4. هیچ تضعیف analyzer/test مجاز نیست.
5. مقایسهٔ رگرسیون با مبنای تاریخی run `29308601832` فقط به‌عنوان مرجع؛ سبز بودن مجدد باید اثبات شود.

---

## ۱۴) سناریوهای E2E لازم (پس از تأیید؛ نه در این وظیفه)

1. ورود OTP → بازیابی same-day history بدون intro تکراری.
2. دریافت push → باز کردن OPEN_CHAT → اولین پیام با `source_notification_id` → پاک شدن pending پس از موفقیت.
3. 403/404 مالکیت → پاک شدن pending؛ timeout/5xx → حفظ برای retry.
4. Inbox: فیلتر unread، mark-read، چهار اکشن canonical.
5. Foreground و background بدون duplicate local.
6. کانال‌های Android چهارگانه.
7. فارسی/عربی RTL و انگلیسی LTR.
8. تنظیمات quiet hours/timezone در برابر رفتار scheduler (پس از همگام‌سازی prefs).

---

## ۱۵) چک‌لیست اعتبارسنجی دستگاه فیزیکی

- [ ] مجوز اعلان granted
- [ ] مسیر denied + بازیابی به تنظیمات سیستم
- [ ] terminated cold start از نوتیفیکیشن
- [ ] background با data-only در برابر notification+data
- [ ] اکشن‌های native در صورت پشتیبانی پلتفرم
- [ ] صدای کانال‌های health/critical در صورت وجود asset
- [ ] عدم نشت دادهٔ تشخیصی در UI launch

---

## ۱۶) تاریخچه عملیات این وظیفه

1. Preflight: branch/HEAD/status/remotes/worktrees.
2. تأیید وجود SHAهای مصوب و validation.
3. `git ls-remote` برای origin و frontend (بدون fetch).
4. محاسبه merge-base و توپولوژی A2/validation.
5. تأیید hash و `git apply --check`/`-R` برای patch A1 (بدون apply).
6. `git show`/`diff`/`grep` برای A2 و ممیزی Gate4.
7. ساخت این سند.

---

## ۱۷) تأیید صریح ممنوعیت‌ها

در این وظیفه **هیچ‌کدام** انجام نشد: تغییر کد محصول، commit، amend، push، force-push، fetch تغییردهندهٔ ref، merge، rebase، cherry-pick، apply patch، ساخت worktree/branch، checkout/switch، stash/clean/reset/restore، build، نصب وابستگی، Flutter/Dart/Python/pytest/Docker/Gradle، deploy، migrate، فعال‌سازی feature flag، تضعیف تست/CI.

تنها نوشتن مجاز: همین فایل `docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md`.

---

## ۱۸) پکیج پیاده‌سازی بعدی توصیه‌شده (پس از تأیید جواد)

**Package 15-P1 — Clean Backend A1 landing**
1. Worktree پاک جدید از `origin/main` (`89b79ad`).
2. اعمال `section14a1-review.patch` (hash تأییدشده).
3. Commit اتمی A1 + درخواست اجرای Actions backend.
4. اصلاح تست‌های legacy بدون JWT در پکیج هم‌زمان یا فوری بعدی.

**Package 15-P2 — Clean Frontend A2 landing**
1. Worktree پاک جدید از `452b3e4` (نه merge validation).
2. Cherry-pick ترتیبی: `d69b2fa` → `9da6202` → `110c533`.
3. حذف/عدم شمول ۵ commit CI validation مگر تأیید جدا.
4. اصلاح فوری B1 (`_userId`) و شروع B2 (حذف `user_id` query) در همان یا پکیج بعدی با تأیید.
5. Actions frontend + APK.

**ممنوع:** استفاده از `Demo` کثیف فعلی؛ merge مستقیم `feature/frontend/section14a2-validation`.

---

## ۱۹) پیشنهاد طراحی Gate 4 (بدون پیاده‌سازی کد)

همسو با نظام بصری Gate3 مصوب:
- پس‌زمینه pale olive `gate3PaleOliveBackground` (`#F3F5EE`)
- دکمه‌های فعال olive (`gate2ButtonOlive` / معادل)
- متن فعال سیاه
- لحن آرام، سلامت‌محور، حرفه‌ای، بدون آلارم غیرضروری
- بدون تعارض با orb/composer Gate3

پوشش: سلسله‌مراتب Inbox؛ گروه‌بندی؛ درمان ریسک/category آرام؛ read/unread؛ جای اکشن‌ها؛ Settings؛ جریان reminder؛ UI deny مجوز؛ empty/loading/error؛ گذار به chat.

**تصمیم‌هایی که قبل از پیاده‌سازی نیازمند تأیید جواد هستند:** شدت رنگ ریسک، محل Settings (Gate4 مستقل در برابر sheet چت)، مدل grouping زمانی، کپی fa/ar/en، رفتار TALK_LATER، و دامنهٔ reminderهای تخصص در V1.

---

## ۲۰) Package 15-P2A — ممیزی و طراحی معماری هوشمندی صدی

### ۲۰.۱ مجوز و محدودیت‌ها
- **مجاز:** خواندن کد backend/frontend؛ تاریخچه فقط‌خواندنی؛ بازرسی A1 uncommitted؛ به‌روزرسانی **فقط** همین لاگ در worktree سکشن ۱۵.
- **غیرمجاز و انجام‌نشده:** هر تغییر کد محصول؛ commit/push؛ branch/worktree جدید یا switch؛ merge/rebase/cherry-pick/patch؛ تست محلی؛ Python/Flutter/Docker/build؛ migration؛ feature-flag؛ CI؛ deploy؛ Gate 4 بصری؛ دست‌کاری Demo کثیف.
- تمایز صریح: «موجود» در برابر «پیشنهادی».

### ۲۰.۲ Worktreeها و SHAهای بازرسی‌شده
| مسیر | Branch | HEAD | وضعیت شواهد |
|------|--------|------|-------------|
| `Demo-wt-section15-backend` | `feature/section15/backend-continuity-foundation` | `89b79ad…` + تغییرات uncommitted P1/A1 | شواهد backend + A1 |
| `Demo-wt-frontend-gate3-finalization` | `feature/frontend/gate3-finalization` | `452b3e4…` | Gate3 UX (بدون تداوم نوتیف A2) |
| `Demo-section14a2-clean` | `feature/frontend/section14a2-validation` | `110c533…` | مسیر چت/تداوم Gate4→Gate3 |
| Demo کثیف | استفادهٔ شواهد پیاده‌سازی **نشد** | — | drift |

**Drift:** FE `452b3e4` فاقد `source_notification_id` روی send است؛ شواهد تداوم از `110c533` گرفته شد.

### ۲۰.۳ خط لوله فعلی چت (موجود — end-to-end)
```
Gate3Composer._send
  → ChatController.sendUserMessage
  → services/chat/chat_service POST /interact/chat (+ JWT; در A2: source_notification_id)
  → interact.chat (get_current_user)
  → [اختیاری] create_user_chat_reminder  ★باگ reply= در برابر message
  → [اگر نوتیف] verify ownership + build_safe_chat_context + create_chat_message_event
  → [اختیاری] chat_commands settings short-circuit
  → ConversationBrain.process_message
       · UserContext + USER_PROFILE + RAG_CONTEXT (+ LocalRAG اگر flag)
       · CARE_CONTEXT + keyword KB فقط اگر medical intent
       · NOTIFICATION_CONTEXT در صورت وجود
       · ۱۰ نوبت Memory
       · emergency/high → قالب ثابت؛ وگرنه gpt-4o-mini
       · post-validator رگکس
       · save Memory + KC extract
  → InteractionResponse.message → UI thinking/speaking
```

| مرحله | طبقه‌بندی |
|--------|-----------|
| Composer → Controller → V1 `/interact/chat` | implemented and connected |
| JWT identity | implemented and connected |
| Same-day history GET `/memory/history` | implemented and connected (گروه‌بندی؛ نه خلاصه معنایی) |
| Continuity نوتیف (A2) | implemented and connected |
| Intent NLU کامل | missing (فقط keyword medical) |
| `unified_context_builder` / `assemble_prompt_blocks` / hybrid KB | implemented but disconnected (عمدتاً تست) |
| `ConversationPrompts.generate_response` | legacy duplicate / disconnected |
| Keyword KB در پیام پزشکی | partial |
| Vector/hybrid KB در چت | implemented but disconnected |
| Safety emergency/high + post-filter | implemented and connected (ناقص برای medium) |
| Missing-info engine | missing |
| Reminder clarification path | unsafe (`InteractionResponse(reply=…)`) |
| InteractionEvent برای همهٔ چت‌ها | partial (فقط نوتیف) |
| Frontend missing-info UX / cancel / offline queue | missing |
| Dual ChatService / ChatPage | legacy duplicate |

### ۲۰.۴ ماتریس قابلیت هوشمندی موجود در برابر هدف
| قابلیت | موجود؟ | مصرف واقعی در چت؟ |
|--------|--------|-------------------|
| هویت احرازشده | بله | بله |
| تاریخ همان‌روز / Memory turns | بله | بله (۱۰ نوبت) |
| پروفایل / UserFact / UserMemoryFact | بله | بله (ناقص) |
| سبک زندگی Gate2 | بله ذخیره‌شده | جزئی در RAG_CONTEXT |
| دارو/بیماری | بله | بله در RAG_CONTEXT |
| علائم حیاتی دستگاه | بله API | **خیر** در GPT context |
| مراقب/اضطراری | بله | خیر در چت |
| KB curated keyword | بله | فقط medical intent |
| KB hybrid/vector | پرچم OFF / قطع از brain | خیر |
| سیاست ایمنی کامل روی LLM متوسط | ناقص | جزئی |
| تشخیص کمبود اطلاعات هدفمند | خیر | — |
| برنامه پاسخ ساخت‌یافته | خیر | — |
| کاندید نوتیف از هوش | جدا از brain | policy/scheduler جدا |
| خلاصه معنایی روزانه/هفتگی | DailyMemorySummary با API جدا | خواندن بله؛ تولید از چت ضعیف؛ A1 فقط grouping |

### ۲۰.۵ موجودی منابع داده (خلاصه)
**مصرف‌شده توسط ConversationBrain:** User، UserProfileKnowledge، UserProfileCore، UserFact، UserMemoryFact، Memory، DailyMemorySummary، Gate2 goals/habits/restrictions/doctors/events، UserCondition/Medication، KB snippets (medical)، notification safe context.

**ذخیره‌شده ولی تقریباً مصرف‌نشده در تولید پاسخ:** caregivers، NotificationPrefs، InteractionEvent، Device/Hub/raw signals، vitals جزئی در GPT، KcUserFact، consents (**مدل consent وجود ندارد**).

| منبع | حساسیت | provenance/freshness | ریسک نشت/تعارض |
|------|--------|----------------------|----------------|
| Memory turns | بالا | created_at | ownership JWT خوب |
| UserMemoryFact | بالا | source/valid_*/fact_status | منابع موازی UserFact |
| notifications body | بالا | — | به brain تزریق نمی‌شود (صحیح) |
| FCM data user_id | متوسط-بالا (PII) | — | به کلاینت push می‌رود؛ FE parse نمی‌کند |

### ۲۰.۶ یافته‌های حافظه
1. A1 = **گروه‌بندی زمانی UI** نه summarization معنایی — نباید خلاصه معنایی نامیده شود.
2. منابع حقیقت موازی: `UserFact` vs `UserMemoryFact` vs `UserProfileKnowledge` vs KC tables.
3. DailyMemorySummary وجود دارد اما pipeline چت آن را به‌صورت خودکار کامل تولید/به‌روز نمی‌کند.
4. حذف کاربر/تصحیح contradiction سیستماتیک در brain نیست.
5. Retention صریح محصولی ناقص؛ Isolation توسط JWT/filter روی user_id عموماً موجود است.
6. B8 فقط برای chat_message نوتیف‌محور؛ چت عادی InteractionEvent ندارد.

### ۲۰.۷ یافته‌های KB/RAG
- پاسخ فعلی از ترکیب کنترل‌نشدهٔ: قالب‌های ایمنی + حقایق کاربر (RAG_CONTEXT) + keyword KB (گاهی) + دانش عمومی gpt-4o-mini.
- Hybrid/vector و `prompt_assembler` به production chat وصل نیستند.
- `/health/questions` مسیر موازی آموزشی است، نه `/interact/chat`.
- استناد داخلی پایدار در پاسخ کاربر به‌صورت قرارداد ساخت‌یافته نیست.

### ۲۰.۸ یافته‌های ایمنی
- short-circuit emergency/high + validator پس از LLM: موجود.
- medium-risk هنوز به LLM خلاق می‌رود.
- تشخیص تشخیص/دوز مبتنی بر رگکس — پوشش ناقص fa/ar/en.
- pregnancy/child در classifier به‌عنوان high.
- escalation مراقب جدا از مسیر چت.
- لاگ حساس و نسخه‌بندی safety policy محدود.
- باگ `reply=` در clarification یادآور: می‌تواند باعث ValidationError/شکست مسیر شود (**confirmed bug → Package 15-P1b یا 15-I0**).

### ۲۰.۹ کمبود اطلاعات (موجود vs لازم)
**موجود نیست** به‌صورت registry/intent profile. Clarification فقط در مسیر reminder و به‌صورت شکسته. FE هیچ UX ساخت‌یافتهٔ سؤال پیگیری ندارد.

### ۲۰.۱۰ معماری هدفی هوشمندی (پیشنهادی — هنوز پیاده نیست)
مراحل قطعی بیرون از LLM:
1. Authenticate 2. locale/timezone 3. normalize message 4. continuity 5. intent/domain 6. risk route 7. data-requirement profile 8. load authorized context 9. freshness/provenance/contradictions 10. missing-info decision (answer / one Q / short group / partial / refuse / escalate) 11. retrieve approved KB 12. structured response plan 13. generate NL 14. validate vs facts+evidence+safety+tone 15. persist conversation 16. persist facts با classification/consent 17. summary jobs 18. emit notification candidate (بدون PHI در push) 19. return message + safe internal metadata.

LLM فقط زبان تولید می‌کند؛ حق invent برای دادهٔ گم‌شده، تشخیص، دوز، اندازه‌گیری، منبع دانش، یا urgency نوتیف را ندارد.

### ۲۰.۱۱ قرارداد context نسخه‌دار (پیشنهادی)
بخش‌ها: `request`, `auth_user`, `conversation`, `intent`, `risk`, `profile`, `lifestyle`, `health`, `memory`, `kb`, `missing`, `consent`, `locale_tz`, `notification_origin`, `freshness`, `provenance`, `contradictions`, `safety_constraints`.

برای هر فیلد در پیاده‌سازی بعدی باید تعریف شود: source، type، required، sensitivity، max size، freshness rule، precedence، logging rule، `may_send_to_llm`، `may_store`.
ممنوع: دادهٔ خام حساس در URL/log/push/prompt بی‌کران.

### ۲۰.۱۲ موتور کمبود اطلاعات (پیشنهادی) — پروفایل intents
برای هر intent: required/optional/disqualifying، freshness، max questions/turn، partial answer؟، referral، storage class.

Intentهای حداقلی: general health، symptom، nutrition، meal plan، sleep، activity، medication، health-data interpretation، lifestyle plan، reminder، notification follow-up، general non-health.

**Meal plan / nutrition** باید صریحاً ارزیابی کند: goal، age، height، weight، gender در صورت لازم، activity، sleep، stress، allergies، conditions، pregnancy، meds/supplements، مذهبی/فرهنگی، بودجه/دسترسی غذا، preferences، وعده‌ها، هشدارهای سلامت مرتبط — و اگر پاسخ معتبر موجود است سؤال را تکرار نکند.

### ۲۰.۱۳ سیاست نوشتن حافظه (پیشنهادی)
1. خودکار فقط کلاس‌های کم‌ریسک/صریح کاربر
2. حساس نیاز consent صریح
3. موقت vs پایدار + انقضا
4. correction جایگزین با provenance
5. contradiction ثبت می‌شود نه silent overwrite
6. UI مشاهده/ویرایش/حذف
7. جلوگیری نشت بین کاربران
8. summaries مشتق از raw با job جدا
9. dedupe retry هماهنگی با B8

### ۲۰.۱۴ کاندید نوتیف هوشمندی (بدون UI Gate4)
لایه‌های جدا: (1) candidate از intelligence (2) policy (quiet hours/volume/feedback) (3) schedule (4) push provider (5) Gate4 presentation (6) Gate3 continuation.
metadata push فقط شناسه‌های امن + deeplink `sedi://`؛ بدون diagnosis/dosage/body.

### ۲۰.۱۵ بازسنجی B8
- هویت یکتا برای `chat_message` نوتیف‌محور درست است: `(user_id, source_notification_id, conversation_id)` با دو partial unique برای NULL/NOT NULL conversation.
- مانع پیام‌های قانونی بعدی **نمی‌شود** اگر event_type یا فقدان source_notification_id مسیر عادی چت را پوشش دهد؛ چت‌های چندنوبتهٔ قانونی در همان conversation باید بتواند رخ دهد بدون duplicate فقط برای همان هویت dedupe.
- Idempotency-key اختیاری برای retry کلاینت (`client_message_id`) پیشنهاد می‌شود در پکیج B8.
- وضعیت: همچنان `blocked with evidence — separate migration authorization required`.

### ۲۰.۱۶ ارزیابی FCM `user_id`
- **Producer:** `push_payload.build_gate4_push_data_payload` / `enrich_notification_fcm_data` ← `delivery_service` با `notification.user_id`.
- **Consumer backend:** ندارد (outbound).
- **Consumer frontend A2 (parse launch/FCM):** شواهدی از مصرف `user_id` در `fcm_setup` / `notification_launch_parser` یافت نشد؛ هویت از JWT است.
- **پیشنهاد:** حذف تدریجی از data payload یا جایگزینی با شناسهٔ غیرحساس سمت سرور در صورت نیاز سازگاری؛ severity: **privacy/PII in push channel — Medium-High**.
- **وضعیت:** approval blocker؛ در این وظیفه پیاده نشد.

### ۲۰.۱۷ پکیج‌های پیاده‌سازی دقیق (هر باگ به یک پکیج)
| پکیج | هدف | وابستگی | نیازمند تأیید جواد |
|------|-----|---------|-------------------|
| **15-P1 Commit** | commit/push A1+B4/B6/B7 روی branch فعلی | review | بله |
| **15-I0 Hotfix** | اصلاح `InteractionResponse(reply=)` → `message=` + تست | می‌تواند داخل P1 باشد | بله اگر جدا |
| **15-P2B FE A2** | cherry-pick سه commit روی `452b3e4` + B1/B2 | پس از/موازی P1 | بله |
| **15-I1 Context/Orchestrator** | قرارداد context + orchestration قطعی بیرون LLM؛ سیم‌کشی به‌جای unified مرده | P1 | بله |
| **15-I2 Data adapters** | آداپترهای خواندن پروفایل/سبک/سلامت/حافظه با freshness/provenance | I1 | بله |
| **15-I3 Missing-info engine** | registry intents + max Q + FE clarifier UX حداقلی | I1–I2 | بله |
| **15-I4 Safety/risk routing** | medium-risk policy، fa/ar/en tests، audit reason codes | I1 | بله |
| **15-I5 Response plan** | قرارداد برنامه‌پاسخ + validate پس از generate | I1–I4 | بله |
| **15-I6 Memory write policy** | consent/classification/correction/expiry + API | I2؛ موازی B8 | بله |
| **15-I7 Semantic summaries** | job خلاصه معنایی (جدا از A1 grouping) | I6 | بله |
| **15-I8 Nutrition/meal intelligence** | پروفایل تغذیه کامل + نه تشخیص/دوز | I3–I5 | بله |
| **15-I9 Notif candidates** | candidate بدون PHI + اتصال policy | I5؛ قبل از Gate4 UI | بله |
| **15-B8 Migration** | partial unique + IntegrityError + concurrency test | مجوز migration جدا | بله |
| **15-FCM Harden** | حذف/جایگزینی user_id در push data | سازگاری کلاینت | بله |
| **15-FE Intel UX** | نمایش clarifier، عدم تکرار سؤال، uncertainty copy | I3–I5، A2 | بله |
| **15-G4 Visual** | UI Gate4 پس از intelligence | I9 + تصمیمات بصری | بله |
| **15-T Legacy cleanup** | B5 ۲۶ شکست FE + باقی تست‌های JWT | CI | بله |

**تخصیص باگ‌های شناخته‌شده:**
B1/B2→15-P2B؛ B3→15-G4/15-P2B؛ B4/B6/B7→P1 (انجام، unverified CI)؛ B5→15-T؛ B8→15-B8؛ B9→15-I9+G4 settings؛ B10→15-FCM+device؛ B11/B12→15-G4؛ reminder `reply=`→15-I0؛ FCM user_id→15-FCM Harden؛ disconnected hybrid/unified→15-I1؛ missing-info→15-I3.

### ۲۰.۱۸ تصمیم‌های محصولی لازم از جواد (قبل از کد)
1. اولویت ترتیب پکیج‌های I1…I9 پس از P1 commit.
2. آیا hybrid KB در V1 intelligence روشن شود یا فقط keyword+facts.
3. مدل consent برای ذخیرهٔ حقایق سلامت (مدل فعلی غایب).
4. حداکثر تعداد سؤال follow-up در هر نوبت.
5. آیا خلاصه معنایی V1 فقط روزانه است یا هفتگی هم.
6. تأیید حذف FCM `user_id`.
7. تأیید migration B8 و استراتژی cleanup تکراری‌ها.
8. دامنهٔ meal-plan V1 (کشور/بودجه/فرهنگ).
9. حفظ زمان‌بندی: Gate4 visual بعد از intelligence.

### ۲۰.۱۹ تأیید ممنوعیت‌های P2A
هیچ تغییر کد محصول، migration، commit، push، تست، build، deploy، branch، worktree، یا feature-flag در این پکیج رخ نداد. تنها تغییر فایل: همین لاگ.

---

## ۲۱) Package 15-I0-B8 — اصلاح schema چت یادآور + idempotency DB

### ۲۱.۱ مجوز
- اصلاح باگ `InteractionResponse(reply=)`؛ migration B8 بدون اجرا؛ هم‌ترازی مدل/سرویس؛ تست‌های رگرسیون بدون اجرای محلی؛ به‌روزرسانی لاگ.
- ممنوع: اجرای migration، commit/push، تست محلی، frontend، حذف FCM user_id، Gate4 بصری، feature-flag، CI، deploy.

### ۲۱.۲ Preflight
| مورد | نتیجه |
|------|--------|
| Branch | `feature/section15/backend-continuity-foundation` |
| HEAD | `89b79ad…` (بدون commit جدید) |
| Alembic head ایستا | تک‌head: `049_section10_kb_embeddings_memory_governance` |
| revision پیشنهادی | `050_gate4_event_idem` (پس از audit pre-commit؛ قبلاً `050_gate4_interaction_event_idempotency`) |
| تغییرات P1 از پیش | حفظ شدند |

### ۲۱.۳ I0 — ریشه و اصلاح
- **ریشه:** `interact.py` برای clarification یادآور `InteractionResponse(reply=…)` می‌ساخت در حالی که schema فقط `message` دارد (و `language`/`timestamp` اجباری‌اند).
- **اصلاح:** `message=clarification` + `language=resolve_request_lang(...)` + `timestamp=datetime.utcnow()`.
- جستجوی backend: تنها همان محل `reply=` بود.
- تست: `test_section15_i0_interaction_response.py` — اثبات عدم فراخوانی LLM، وجود `message`، حفظ متن، mismatch JWT→403.
- وضعیت: **implemented but unverified pending GitHub Actions**

### ۲۱.۴ B8 — چرخه حیات و تصمیم یکتایی
شواهد محصول: FE پس از موفقیت اولین نوبت launch را پاک می‌کند و نوبت‌های بعدی `source_notification_id` نمی‌فرستند. هویت از JWT+ownership است.

**تصمیم نهایی (تأیید شده در این پکیج):**
یک partial unique index روی `(user_id, source_notification_id)` با شرط:
`event_type = 'chat_message' AND source_notification_id IS NOT NULL`

**چرا conversation_id داخل unique نیست:**
- در PostgreSQL NULLها در UNIQUE متمایزند → جفت NULL/non-NULL می‌تواند مصرف دوم بسازد.
- تغییر conversation_id نباید مصرف مجدد بسازد.
- تست قدیمی «دو conversation → دو event» با این invariant جایگزین شد.

نام ایندکس: `uq_interaction_events_notif_chat_once`

### ۲۱.۵ Migration
- فایل: `backend/alembic/versions/050_gate4_interaction_event_idempotency.py` (نام فایل توصیفی؛ revision کوتاه)
- `revision`: `050_gate4_event_idem` (۲۰ کاراکتر؛ ≤32)
- `down_revision`: `049_section10_kb_embeddings_memory_governance`
- قبل از CREATE: query تکراری و **RuntimeError fail-closed**؛ هیچ DELETE خودكار نیست.
- CREATE فقط روی dialect=postgresql (الگوی migration 040).
- Downgrade: فقط DROP همین ایندکس.
- **اجرا نشد.**

### ۲۱.۶ مدل و سرویس
- `InteractionEvent.__table_args__`: Index با `postgresql_where` **و** `sqlite_where` (همان predicate) برای سازگاری `create_all` در SQLite.
- `find_existing_*` بدون فیلتر conversation_id.
- `create_chat_message_event`: select-before-insert + `begin_nested` + catch فقط IntegrityError مرتبط با این constraint + بازیابی event موجود؛ لاگ بدون محتوای سلامت.

### ۲۱.۷ Preflight SQL تولید (فقط‌خواندنی، قبل از اجرای آینده)
```sql
SELECT user_id,
       source_notification_id,
       COUNT(*) AS duplicate_count,
       MIN(id) AS earliest_event_id,
       MAX(id) AS latest_event_id
FROM interaction_events
WHERE event_type = 'chat_message'
  AND source_notification_id IS NOT NULL
GROUP BY user_id, source_notification_id
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, user_id ASC, source_notification_id ASC;
```
مسیر تولید: backup → query → اگر صفر، migration پس از تأیید؛ اگر >0 توقف + گزارش شواهد + تأیید cleanup؛ هرگز حذف خاموش audit.

### ۲۱.۸ تست‌های اضافه‌شده (اجرا نشده)
- `test_section15_i0_interaction_response.py`
- `test_section15_b8_interaction_idempotency.py`
- به‌روزرسانی `test_gate4c_interaction_events.py` (invariant جدید conversation)
- تست‌های ایندکس/concurrency: فقط PostgreSQL (`pytest.skip` روی غیر-PG)

### ۲۱.۹ الزام مصوب: Weekly Knowledge Discovery and Governance Engine
پایپ‌لاین هفتگی خودکار ۲۰مرحله‌ای (scheduler → query registry → allowlist/trust → fetch → robots/license → download → dedupe URL/DOI/hash → malware/validate → extract → language → taxonomy → credibility → freshness → provenance → chunk/embed → quality/safety → quarantine → publish policy → supersede/retire → audit → metrics).

Trust: A رسمی، B peer-reviewed، C خبر/وبلاگ — **C هرگز auto-authoritative نیست**. فقط دانش published/approved به‌عنوان evidence صدی. LLM عمومی منبع approved نیست. پرچم‌های KB موجود تا ارزیابی Actions و تأیید جواد خاموش می‌مانند.

**تخصیص پکیج:** `15-I10 Weekly Knowledge Engine` (پس از I1 orchestrator؛ وابسته به KB flags/approval).

### ۲۱.۱۰ الزام مصوب: Reliable Working and Short-Term Memory
شامل: کاربر، conversation، نوبت‌های مرتبط، intent، risk، pending clarifications، پاسخ‌های موقت، notification origin، tool state، retry/idempotency، locale/tz، محدودیت اندازه، TTL، transitions، بازیابی پس از restart.

قواعد: نه فقط حافظه in-process؛ نه فقط «۱۰ پیام آخر» به‌عنوان استراتژی کامل؛ انتخاب با relevance/recency/domain/safety؛ بدون مخلوط کاربر؛ retry idempotent؛ داده موقت≠واقعیت پایدار؛ pending سؤال پایدار در reopen؛ inspectable/testable؛ بدون لاگ ناامن.

**تخصیص:** `15-I1 Context/Orchestrator` + `15-B8` (بخش idempotency) + `15-I3 Missing-info`.

### ۲۱.۱۱ الزام مصوب: Reliable Longitudinal Memory
تمایز: raw history، profile، lifestyle، health حساس، prefs، goals، temporary، superseded، daily/weekly/monthly/annual semantic summaries، trends، hypotheses غیرقطعی.

هر واقعیت پایدار: owner، type، value ساختاری، source، provenance، زمان‌ها، sensitivity، consent، confidence، freshness، active/superseded، correction link، version، deletion/audit.

قواعد: inference LLM≠confirmed fact؛ سلامت حساس با consent؛ correction با provenance؛ contradiction صریح؛ freshness-aware retrieval؛ view/edit/delete کاربر؛ حذف به derived؛ summaries قابل ردیابی؛ cross-user fail-closed؛ grouping≠semantic summary.

**تخصیص:** `15-I6 Memory write policy` + `15-I7 Semantic summaries` + `15-I2 Data adapters`.

### ۲۱.۱۲ وضعیت مسدودکننده‌های مرتبط
- B8 migration: **implemented but unverified** — اجرا نیازمند تأیید جدا + preflight SQL.
- FCM `user_id`: همچنان assigned به `15-FCM Harden`، unresolved.
- Gate4 visual: پس از intelligence.
- تست‌ها اجرا نشدند؛ CI اجرا نشد؛ commit/push نشد.

### ۲۱.۱۳ تأیید ممنوعیت‌های I0-B8
migration اجرا نشد؛ تست محلی اجرا نشد؛ commit/push/deploy/frontend/feature-flag/CI نشد. Demo کثیف دست‌نخورده.

---

## ۲۲) Package 15-I0-B8 Pre-Commit Correction Audit

### ۲۲.۱ مجوز
- بازبینی ایستا P1 + I0-B8؛ اصلاح مدل/migration/تست در صورت نیاز؛ کوتاه‌سازی revision 050؛ به‌روزرسانی لاگ؛ `git diff --check`.
- ممنوع: commit/push، اجرای migration/DB، تست محلی، Python/Alembic، frontend، تغییر migration 049.

### ۲۲.۲ Preflight (قبل از اصلاح)
| مورد | نتیجه |
|------|--------|
| Worktree | `Demo-wt-section15-backend` |
| Branch | `feature/section15/backend-continuity-foundation` |
| HEAD | `89b79ad3fc20236a23ffae65fd868aafb60843e8` |
| revision 050 (قبل) | `050_gate4_interaction_event_idempotency` (۴۰ کاراکتر) |
| revision 050 (بعد) | `050_gate4_event_idem` (۲۰ کاراکتر) |
| revision 049 | `049_section10_kb_embeddings_memory_governance` (۴۵ کاراکتر؛ بدون تغییر) |

### ۲۲.۳ ریسک SQLite partial index — تشخیص و رفع
- `conftest.py` از `Base.metadata.create_all` استفاده می‌کند؛ پیش‌فرض تست PostgreSQL است (`test_db_config.py`) اما URL می‌تواند SQLite باشد.
- Index فقط با `postgresql_where` روی SQLite به UNIQUE بدون شرط تبدیل می‌شود → مسدود شدن `notification_ack` / `notification_open_chat` با همان `source_notification_id`.
- **رفع:** predicate مشترک `_NOTIF_CHAT_ONCE_PARTIAL_IDX_WHERE` + `sqlite_where` و `postgresql_where` در `models.py`.
- تست جدید: `test_model_partial_unique_index_has_sqlite_and_postgresql_where` (compile DDL با WHERE).

### ۲۲.۴ ریسک طول revision Alembic
- `alembic.ini` سفارشی برای `version_num` ندارد؛ پیش‌فرض Alembic VARCHAR(32) فرض شد.
- migration `008_lock_dedupe_received_at` روی PostgreSQL: `ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)` — ظرفیت اثبات‌شده **۶۴** پس از 008.
- **049 (۴۵ کاراکتر):** با evidence migration 008 → **safe** (≤64)؛ child مستقیم: فقط 050؛ **Critical blocker نیست** اگر زنجیره 008 در prod اعمال شده باشد.
- **050 (قبل، ۴۰ کاراکتر):** از 32 بیشتر بود → کوتاه شد به `050_gate4_event_idem` (۲۰).
- migration 049 **تغییر نکرد** (نیاز تأیید جدا).

### ۲۲.۵ بازبینی fail-closed migration 050
- preflight: `user_id`, `source_notification_id`, `event_type='chat_message'`, non-null source؛ بدون `conversation_id`؛ بدون DELETE؛ abort قبل از CREATE.
- upgrade: فقط `uq_interaction_events_notif_chat_once`؛ downgrade: فقط DROP همان index.
- `down_revision` = `049_section10_kb_embeddings_memory_governance`؛ `revision` = `050_gate4_event_idem`.

### ۲۲.۶ بازبینی savepoint سرویس
- `begin_nested()` قبل از insert؛ IntegrityError مرتبط → rollback savepoint؛ outer session سالم؛ `diag.constraint_name == uq_interaction_events_notif_chat_once` اولویت؛ fallback متنی برای SQLite؛ IntegrityError نامرتبط re-raise؛ re-select بدون conversation_id.

### ۲۲.۷ تست‌های به‌روزشده
- assertion revision کوتاه + طول ≤32 در `test_migration_source_defines_index_and_fail_closed_preflight`
- `test_model_partial_unique_index_has_sqlite_and_postgresql_where`
- پوشش قبلی I0/B8/concurrency/PG حفظ شد.
- **تست‌ها اجرا نشدند.**

### ۲۲.۸ فایل‌های تغییر یافته در این audit
- `backend/app/models.py`
- `backend/alembic/versions/050_gate4_interaction_event_idempotency.py`
- `backend/app/services/gate4/interaction_event_service.py`
- `backend/tests/test_section15_b8_interaction_idempotency.py`
- `docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md`

### ۲۲.۹ `git diff --check`
اجرا شد — بدون خطای whitespace/conflict marker.

### ۲۲.۱۰ تأیید ممنوعیت‌ها
commit/push/migration execution/تست محلی/Python/Alembic/frontend انجام نشد.

### ۲۲.۱۱ گام بعد
- اگر بازبینی کد پذیرفته شد: **تأیید commit/push** P1 + I0-B8 → GitHub Actions.
- **اجرای migration 050** همچنان جدا: backup + SQL preflight §۲۱.۷ + تأیید صریح؛ و تأیید prod state زنجیره 008/049.

---

## ۲۳) تأیید commit — Package 15 Backend Foundation (P1 + I0-B8)

### ۲۳.۱ مجوز commit (جواد)
جواد به‌صریح **یک commit** روی شاخه `feature/section15/backend-continuity-foundation` تأیید کرد.

### ۲۳.۲ پیام commit مصوب
```
feat(backend): harden conversation continuity and notification idempotency
```

### ۲۳.۳ وضعیت قبل از commit
| مورد | مقدار |
|------|--------|
| Worktree | `Demo-wt-section15-backend` |
| Branch | `feature/section15/backend-continuity-foundation` |
| HEAD (parent) | `89b79ad3fc20236a23ffae65fd868aafb60843e8` |

### ۲۳.۴ محدوده commit
P1/A1 + اصلاحات B4/B6/B7 + I0 (`InteractionResponse.message`) + B8 (idempotency DB + migration 050 `050_gate4_event_idem` **بدون اجرا**) + لاگ master + تست‌های مرتبط (۲۰ فایل allowlist).

### ۲۳.۵ وضعیت اجرا
- تست محلی: **اجرا نشد**
- migration 050: **commit شد؛ اجرا نشد**
- push/deploy: **مجاز نیست**
- SHA نهایی commit در همین commit قابل درج نیست؛ بلافاصله پس از commit در §۲۳.۶ (ledger پس از commit، unstaged) ثبت می‌شود.

### ۲۳.۶ Ledger پس از commit backend foundation (`2a7dede`)
| مورد | مقدار |
|------|--------|
| Commit SHA | `2a7dede9b07214f0a8ccb87100fe7b020adb1ac4` |
| Subject | `feat(backend): harden conversation continuity and notification idempotency` |
| Parent SHA | `89b79ad3fc20236a23ffae65fd868aafb60843e8` |
| Branch | `feature/section15/backend-continuity-foundation` |
| Timestamp (UTC-7) | ۲۰۲۶-۰۷-۱۴ |
| فایل‌های commit‌شده | ۲۰ کل — **۸ added** + **۱۲ modified** (جزئیات §۲۳.۷–§۲۳.۸) |
| Push | **انجام نشد** |
| تست محلی | **اجرا نشد** |
| migration 050 | **commit شد؛ اجرا نشد** |
| Deploy / feature-flag | **مجاز نبود** |

### ۲۳.۷ Allowlist commit‌شده (۲۰ فایل)
1. `backend/alembic/versions/050_gate4_interaction_event_idempotency.py`
2. `backend/app/models.py`
3. `backend/app/routers/interact.py`
4. `backend/app/routers/memory.py`
5. `backend/app/routers/notifications.py`
6. `backend/app/schemas/memory.py`
7. `backend/app/schemas/notification.py`
8. `backend/app/services/gate4/inbox_metadata.py`
9. `backend/app/services/gate4/interaction_event_service.py`
10. `backend/app/services/gate4/policy_prefs_bridge.py`
11. `backend/app/services/gate4/push_payload.py`
12. `backend/tests/contracts/snapshots/openapi_v1_snapshot.json`
13. `backend/tests/test_gate4_push_channel_routing_v1.py`
14. `backend/tests/test_gate4c_interaction_events.py`
15. `backend/tests/test_memory_history_timezone_v1.py`
16. `backend/tests/test_notification_api_b2.py`
17. `backend/tests/test_notification_inbox_gate4_v1.py`
18. `backend/tests/test_section15_b8_interaction_idempotency.py`
19. `backend/tests/test_section15_i0_interaction_response.py`
20. `docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md`

### ۲۳.۸ تفکیک added / modified در commit `2a7dede`
| نوع | تعداد | جزئیات |
|-----|--------|--------|
| **Added (A)** | **۸** | ۱ migration + ۱ service + ۵ test + ۱ master log |
| **Modified (M)** | **۱۲** | models، routers، schemas، services، openapi snapshot، ۲ test موجود |
| **جمع** | **۲۰** | allowlist کامل §۲۳.۷ |

**۸ فایل added:**
1. `backend/alembic/versions/050_gate4_interaction_event_idempotency.py` (migration)
2. `backend/app/services/gate4/inbox_metadata.py` (service)
3. `backend/tests/test_gate4_push_channel_routing_v1.py` (test)
4. `backend/tests/test_memory_history_timezone_v1.py` (test)
5. `backend/tests/test_notification_inbox_gate4_v1.py` (test)
6. `backend/tests/test_section15_b8_interaction_idempotency.py` (test)
7. `backend/tests/test_section15_i0_interaction_response.py` (test)
8. `docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md` (master log)

**۱۲ فایل modified:** models، interact، memory، notifications routers؛ memory/notification schemas؛ interaction_event_service، policy_prefs_bridge، push_payload؛ openapi snapshot؛ test_gate4c_interaction_events، test_notification_api_b2.

---

## ۲۴) commit مستندسازی — reconciliation ledger §۲۳

### ۲۴.۱ مجوز (جواد)
جواد به‌صریح **یک commit مستندسازی جدا** تأیید کرد — فقط `docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md`.

### ۲۴.۲ پیام commit مصوب
```
docs: record section15 backend foundation commit
```

### ۲۴.۳ دلیل
- ثبت/persist ledger §۲۳.۶ برای commit کد `2a7dede9b07214f0a8ccb87100fe7b020adb1ac4`
- اصلاح accounting: **۸ added + ۱۲ modified = ۲۰** (§۲۳.۸)
- حذف trailing whitespace در همین فایل markdown

### ۲۴.۴ وضعیت اجرا
- تغییر کد محصول: **خیر**
- تست محلی: **اجرا نشد**
- migration: **اجرا نشد**
- push/deploy: **مجاز نیست**
- SHA نهایی این commit مستندسازی در همین commit قابل درج نیست (چرخه self-reference)؛ در به‌روزرسانی عادی بعدی master log ثبت می‌شود.

---

## ۲۵) Push + GitHub Actions CI — Section 15 Backend Foundation

### ۲۵.۱ مجوز و SHAها
- جواد push و CI validation را تأیید کرد.
- **Documentation commit SHA:** `4aea9746d45b926942b94ea474359169e104f910`
- **Backend foundation commit:** `2a7dede9b07214f0a8ccb87100fe7b020adb1ac4`
- **Base:** `89b79ad3fc20236a23ffae65fd868aafb60843e8` (`origin/main` بدون تغییر)
- **Co-authored-by Cursor:** به‌عنوان provenance غیرعملکردی ابزار پذیرفته شد؛ تأثیری بر محتوای commit ندارد.

### ۲۵.۲ Push
| مورد | مقدار |
|------|--------|
| Remote | `origin` → `git@github.com:javadmeighani-oss/sedi-backend.git` |
| Branch | `feature/section15/backend-continuity-foundation` |
| Remote SHA (verified) | `4aea9746d45b926942b94ea474359169e104f910` |
| Upstream | `origin/feature/section15/backend-continuity-foundation` |
| Timestamp (UTC) | ۲۰۲۶-۰۷-۱۴T07:38Z تقریبی |
| Force-push | **خیر** |

### ۲۵.۳ بازبینی امنیت workflow (قبل از push)
هیچ workflow خودکار برای push به `feature/section15/**` فعال نیست. workflowهای deploy/prod-migrate/SSH/image-publish فقط `workflow_dispatch` یا `main` هستند — **push ایمن**.

### ۲۵.۴ اجراهای GitHub Actions (SHA دقیق `4aea974…`)

| Workflow | Run ID | Event | Conclusion | Duration | URL |
|----------|--------|-------|------------|----------|-----|
| Backend V1 freeze tests | 29315223037 | workflow_dispatch | **success** | ~1m36s | https://github.com/javadmeighani-oss/sedi-backend/actions/runs/29315223037 |
| Gate 5 DB tests | 29315225102 | workflow_dispatch | **success** | ~59s | https://github.com/javadmeighani-oss/sedi-backend/actions/runs/29315225102 |

**Push event:** هیچ run خودکاری برای SHA `4aea974` ثبت نشد — dispatch دستی انجام شد.

### ۲۵.۵ جمع تست‌ها (pytest logs)
**Backend V1 freeze tests:** 91 + 27 + 147 + 171 + 12 + 4 = **452 passed** (0 failed)
- شامل: Section 10 subset، contracts، interact/auth stabilization، OTP/Gate1–3، acceptance subset
- **Alembic upgrade head** در ephemeral Postgres: **موفق** (شامل revision `050_gate4_event_idem`)

**Gate 5 DB tests:** 6+5+8+5+23+22+1 = **70 passed** (0 failed)
- **Alembic upgrade head:** **موفق**
- **OpenAPI snapshot:** 1 passed

**جمع کل collected:** **522 passed**, **0 failed**

### ۲۵.۶ ماتریس پوشش Section 15

| حوزه | وضعیت CI |
|------|-----------|
| **A1** JWT memory history / timezone / grouping / gate4_metadata | **workflow gap** — `test_memory_history_timezone_v1.py` و `test_notification_inbox_gate4_v1.py` در هیچ workflow نیستند |
| **A1** partial: memory auth JWT | interact stabilization (`test_memory_auth_v1.py`) **passed** |
| **B4/B6/B7** notification API/channel/language | **workflow gap** — `test_notification_api_b2.py`, `test_gate4_push_channel_routing_v1.py` جمع‌آوری نشد |
| **I0** reminder `message` / LLM bypass | **workflow gap** — `test_section15_i0_interaction_response.py` جمع‌آوری نشد |
| **B8** idempotency/concurrency/migration tests | **workflow gap** — `test_section15_b8_interaction_idempotency.py` جمع‌آوری نشد |
| **B8** partial: gate4c interaction events | **workflow gap** — `test_gate4c_interaction_events.py` جمع‌آوری نشد |
| **OpenAPI snapshot** | **verified passed** (Gate 5 + Backend contracts) |
| **Migration chain 049→050 ephemeral upgrade** | **verified passed** (هر دو workflow، upgrade head) |
| **Migration 050 production** | **blocked** — preflight SQL §۲۱.۷ + backup + تأیید جدا |
| **Production/staging DB** | **not touched** |

### ۲۵.۷ شکست‌ها
**هیچ شکست CI** — هر دو run **success**.

### ۲۵.۸ ممنوعیت‌ها
deploy، image publication، feature-flag، frontend build، prod migration، SSH، workflow modification — **انجام نشد**.

### ۲۵.۹ گام بعد
- **Package 15-CI-Extend (یا معادل):** افزودن Section 15 tests (`i0`, `b8`, `b4/b6/b7`, `memory_history_timezone`, `gate4c`) به workflow CI امن — **پیش از ادعای verified برای I0/B8/A1 کامل**
- اگر CI extension تأیید شد و سبز شد: **15-I1** Context/Orchestrator
- Production migration 050: همچنان جدا و مسدود

---

## ۲۶) Package 15-CI-Extend — جمع‌آوری تست‌های Section 15 در CI

### ۲۶.۱ دلیل
Runهای موفق قبلی (`29315223037`: 452 passed؛ `29315225102`: 70 passed) تست‌های جدید A1/B4/B6/B7/I0/B8 را **جمع‌آوری نکردند** — workflow gap.

### ۲۶.۲ فایل workflow تغییر یافته
- `.github/workflows/ci-backend-tests.yml`
- نام workflow (بدون تغییر): **`Backend V1 freeze tests`**

### ۲۶.۳ مرزهای ایمنی حفظ‌شده
| مورد | وضعیت |
|------|--------|
| Triggers (`push`/`pull_request`/`workflow_dispatch`) | **بدون تغییر** |
| Permissions / secrets / runner | **بدون تغییر** |
| PostgreSQL service ephemeral | **بدون تغییر** |
| `alembic upgrade head` | **بدون تغییر** |
| 452-test freeze selection | **بدون تغییر** |
| Deploy / SSH / image / prod migration | **اضافه نشد** |

### ۲۶.۴ شکل انتخاب‌شده
**یک step اجباری** با نام دقیق `Section 15 backend foundation tests` در انتهای job موجود `backend-acceptance` / `V1 freeze subset`.

**دلیل:** fixture `db` در `conftest.py` با rollback تراکنش کار می‌کند؛ تست‌های B8 که index سراسری را DROP/CREATE می‌کنند فقط **پس از** اتمام suite موجود 452 تستی اجرا می‌شوند تا state آلوده به freeze tests نرسد. job جدا لازم نبود.

### ۲۶.۵ هفت مسیر pytest صریح (repo root)
1. `backend/tests/test_memory_history_timezone_v1.py`
2. `backend/tests/test_notification_inbox_gate4_v1.py`
3. `backend/tests/test_gate4_push_channel_routing_v1.py`
4. `backend/tests/test_notification_api_b2.py`
5. `backend/tests/test_section15_i0_interaction_response.py`
6. `backend/tests/test_section15_b8_interaction_idempotency.py`
7. `backend/tests/test_gate4c_interaction_events.py`

### ۲۶.۶ پوشش مورد انتظار (پس از dispatch)
| حوزه | فایل(ها) |
|------|-----------|
| A1 timezone/grouping/inbox | memory_history_timezone، notification_inbox_gate4 |
| B4/B6/B7 | notification_api_b2، gate4_push_channel_routing |
| I0 | section15_i0_interaction_response |
| B8 | section15_b8_interaction_idempotency |
| Gate4C | test_gate4c_interaction_events |

PostgreSQL-marked B8 tests در CI ephemeral Postgres باید **skip نشوند**.

### ۲۶.۷ وضعیت
**implemented but unverified pending GitHub Actions**

- تست محلی: **اجرا نشد**
- commit/push/dispatch: **انجام نشد**

### ۲۶.۸ گام‌های تأیید بعدی
1. commit (پیشنهاد: `ci: collect section15 backend foundation tests in freeze workflow`)
2. push
3. `workflow_dispatch` روی `feature/section15/backend-continuity-foundation` و بازبینی log برای collected/passed/skipped دقیق

---

## ۲۷) CI-Extend validation — push + dispatch @ `eaf6634`

### ۲۷.۱ commit و push
| مورد | مقدار |
|------|--------|
| CI-Extend commit | `eaf6634346d3e8b84fb196d3f7b9946052af0d5a` |
| Push timestamp (UTC) | ۲۰۲۶-۰۷-۱۴ ~08:11Z |
| Remote SHA verified | `eaf6634346d3e8b84fb196d3f7b9946052af0d5a` |
| `origin/main` | `89b79ad3fc20236a23ffae65fd868aafb60843e8` (بدون تغییر) |

### ۲۷.۲ GitHub Actions run
| مورد | مقدار |
|------|--------|
| Workflow | Backend V1 freeze tests |
| Run ID | **29317145557** |
| URL | https://github.com/javadmeighani-oss/sedi-backend/actions/runs/29317145557 |
| Event | workflow_dispatch |
| Branch | `feature/section15/backend-continuity-foundation` |
| Head SHA | `eaf6634346d3e8b84fb196d3f7b9946052af0d5a` |
| Duration | ~1m44s |
| **Conclusion** | **failure** |

### ۲۷.۳ Existing freeze suite (همان run)
| Step | Passed |
|------|--------|
| Section 10 + contract subset | 91 |
| contracts | 27 |
| interact stabilization | 147 |
| OTP/SMS gateway | 171 |
| acceptance subset | 12 |
| notification prefs | 4 |
| **جمع freeze** | **452** (0 failed) |

Ephemeral `alembic upgrade head` موفق — revision `050_gate4_event_idem` فقط در DB ephemeral CI اعمال شد. production/staging تماس نگرفته.

### ۲۷.۴ Section 15 step — `Section 15 backend foundation tests`
| مورد | مقدار |
|------|--------|
| Collected | **82** |
| Passed | **81** |
| Failed | **1** |
| Skipped | **0** |
| Deselected | **0** |
| Warnings | 1 |
| Duration | ~2.24s |

**هفت فایل جمع‌آوری شد** (همه explicit):
1. `test_memory_history_timezone_v1.py` ✓
2. `test_notification_inbox_gate4_v1.py` ✓
3. `test_gate4_push_channel_routing_v1.py` ✓
4. `test_notification_api_b2.py` ✓
5. `test_section15_i0_interaction_response.py` ✓
6. `test_section15_b8_interaction_idempotency.py` ✗ (۱ failure)
7. `test_gate4c_interaction_events.py` ✓

**B8 PostgreSQL tests:** `_require_postgres` tests **اجرا شدند** (skip نشد): concurrency، migration upgrade، fail-closed preflight — همه passed جز static migration-source test.

### ۲۷.۵ شکست واحد
| فیلد | مقدار |
|------|--------|
| File | `backend/tests/test_section15_b8_interaction_idempotency.py` |
| Test | `test_migration_source_defines_index_and_fail_closed_preflight` |
| Line | 362 |
| Assertion | `assert f"DROP INDEX IF EXISTS {UQ_NOTIF_CHAT_ONCE}" in text_src` |
| Root cause | migration downgrade uses `f"DROP INDEX IF EXISTS {INDEX_NAME}"` (متغیر `INDEX_NAME`)؛ تست literal string کامل `uq_interaction_events_notif_chat_once` را در source می‌خواهد |
| Likely fix | اصلاح assertion تست برای پذیرش `INDEX_NAME` / `UQ_NOTIF_CHAT_ONCE` constant pattern — **نه** تغییر migration |

### ۲۷.۶ ماتریس پوشش Section 15

| حوزه | وضعیت |
|------|--------|
| A1 timezone/grouping/ISO week/current_group_key | **verified passed** (9 tests) |
| A1 inbox metadata/ownership/safe context | **verified passed** |
| B4 auth 401/ownership 403/JWT | **verified passed** |
| B6 channel precedence | **verified passed** |
| B7 invalid language → en | **verified passed** |
| I0 `message`/LLM bypass/auth | **verified passed** (3 tests) |
| B8 sequential/null-conversation/dedupe/isolation | **verified passed** |
| B8 PG concurrency/index/preflight runtime | **verified passed** |
| B8 migration static source assertions | **executed failed** (۱ assertion) |
| Gate4C interaction events | **verified passed** (22 tests) |

### ۲۷.۷ وضعیت بسته
**blocked pending correction** — workflow failure به‌خاطر ۱ assertion static در B8 test؛ 81/82 Section 15 tests passed؛ PG B8 tests skip نشدند.

### ۲۷.۸ ممنوعیت‌ها
deploy، image publication، SSH، prod migration، frontend، commit، rerun — **انجام نشد**.

### ۲۷.۹ گام بعد
**Package 15-B8-TestFix (یا معادل):** اصلاح `test_migration_source_defines_index_and_fail_closed_preflight` assertion → commit → push → dispatch مجدد. **15-I1** فقط پس از run سبز با 82/82 passed.

---

## ۲۸) Package 15-B8-TestFix — اصلاح assertion static migration source

### ۲۸.۱ Run مرجع
| مورد | مقدار |
|------|--------|
| Run ID | **29317145557** |
| URL | https://github.com/javadmeighani-oss/sedi-backend/actions/runs/29317145557 |
| Test شکست‌خورده | `test_migration_source_defines_index_and_fail_closed_preflight` |
| خط | `backend/tests/test_section15_b8_interaction_idempotency.py:362` |

### ۲۸.۲ علت ریشه‌ای
Assertion static بیش‌ازحد سخت: تست literal گسترش‌یافته `DROP INDEX IF EXISTS uq_interaction_events_notif_chat_once` را در source می‌خواست، در حالی که migration downgrade از `f"DROP INDEX IF EXISTS {INDEX_NAME}"` با ثابت `INDEX_NAME = "uq_interaction_events_notif_chat_once"` استفاده می‌کند.

### ۲۸.۳ شواهد runtime PostgreSQL (همان run — passed)
| تست runtime | وضعیت |
|-------------|--------|
| migration upgrade creates index | **passed** |
| duplicate preflight fail-closed | **passed** |
| concurrency creates one event | **passed** |
| B8 PostgreSQL tests skipped | **0** (همه اجرا شدند) |

Section 15 step: **81/82 passed**؛ تنها شکست assertion static migration source بود.

### ۲۸.۴ اصلاح minimal (فقط تست)
**قبل:**
```python
assert f"DROP INDEX IF EXISTS {UQ_NOTIF_CHAT_ONCE}" in text_src
```

**بعد:**
```python
assert f'INDEX_NAME = "{UQ_NOTIF_CHAT_ONCE}"' in text_src
assert "DROP INDEX IF EXISTS {INDEX_NAME}" in text_src
```

- ثابت `INDEX_NAME` به مقدار دقیق `uq_interaction_events_notif_chat_once` (از طریق `UQ_NOTIF_CHAT_ONCE`) bind می‌شود.
- downgrade ثابت نام‌دار `INDEX_NAME` را از طریق placeholder دقیق f-string `{INDEX_NAME}` reference می‌کند.
- سایر assertionها (revision، down_revision، partial index، preflight، fail-closed، عدم DELETE، conversation_id) **بدون تغییر**.

### ۲۸.۵ فایل‌های تغییر یافته
| فایل | تغییر |
|------|--------|
| `backend/tests/test_section15_b8_interaction_idempotency.py` | اصلاح assertion static |
| `docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md` | این §۲۸ |

**تغییر نداده شد:** migration `050_gate4_interaction_event_idempotency.py`، service/model/router/schema، workflow، frontend.

### ۲۸.۶ وضعیت
**implemented but unverified pending GitHub Actions rerun**

### ۲۸.۷ ممنوعیت‌ها (رعایت شد)
| عمل | وضعیت |
|-----|--------|
| تست محلی / pytest | **اجرا نشد** |
| commit | **انجام نشد** |
| push | **انجام نشد** |
| workflow dispatch / rerun | **انجام نشد** |
| migration execution / DB | **انجام نشد** |
| deploy / image / SSH | **انجام نشد** |

### ۲۸.۸ گام‌های تأیید بعدی
1. commit (پیشنهاد: `test(section15-b8): bind INDEX_NAME constant in migration source assertion`)
2. push به `feature/section15/backend-continuity-foundation`
3. یک `workflow_dispatch` دقیق روی Backend V1 freeze @ SHA جدید — انتظار **82/82** Section 15 passed

**15-I1** فقط پس از run سبز.

---

## ۲۹) Package 15-B8-TestFix — push + CI validation @ `a176680`

### ۲۹.۱ commit و push
| مورد | مقدار |
|------|--------|
| Commit | `a17668071e580e456c82dad0d876b28c549825d3` |
| Subject | `test(section15-b8): bind INDEX_NAME constant in migration source assertion` |
| Parent | `eaf6634346d3e8b84fb196d3f7b9946052af0d5a` |
| Push timestamp (UTC) | ۲۰۲۶-۰۷-۱۴ ~08:34Z |
| Remote SHA verified | `a17668071e580e456c82dad0d876b28c549825d3` |
| `origin/main` | `89b79ad3fc20236a23ffae65fd868aafb60843e8` (بدون تغییر) |

### ۲۹.۲ GitHub Actions run
| مورد | مقدار |
|------|--------|
| Workflow | Backend V1 freeze tests |
| Path | `.github/workflows/ci-backend-tests.yml` |
| Run ID | **29318539239** |
| URL | https://github.com/javadmeighani-oss/sedi-backend/actions/runs/29318539239 |
| Event | workflow_dispatch |
| Branch | `feature/section15/backend-continuity-foundation` |
| Head SHA | `a17668071e580e456c82dad0d876b28c549825d3` |
| Created (UTC) | ۲۰۲۶-۰۷-۱۴ 08:34:57Z |
| Duration | ~1m38s |
| **Conclusion** | **success** |

### ۲۹.۳ Existing freeze suite (همان run — actual)
| Step | Passed |
|------|--------|
| Section 10 + contract subset | **91** |
| contracts | **27** |
| interact stabilization | **147** |
| OTP/SMS gateway | **171** |
| acceptance subset | **12** (3+6+1+1+1) |
| notification prefs | **4** |
| **جمع freeze** | **452** (0 failed) |

OpenAPI snapshot/contract validation passed. `alembic upgrade head` موفق روی ephemeral PostgreSQL CI (`127.0.0.1:5432/sedi_test`). revision `050_gate4_event_idem` اعمال شد — **فقط ephemeral CI**؛ production/staging تماس نگرفته.

### ۲۹.۴ Section 15 step — `Section 15 backend foundation tests`
| مورد | مقدار |
|------|--------|
| Collected | **82** |
| Passed | **82** |
| Failed | **0** |
| Skipped | **0** |
| Deselected | **0** |
| Warnings | 1 |
| Duration | ~2.16s |

**هفت فایل explicit جمع‌آوری شد:**
1. `test_memory_history_timezone_v1.py` ✓
2. `test_notification_inbox_gate4_v1.py` ✓
3. `test_gate4_push_channel_routing_v1.py` ✓
4. `test_notification_api_b2.py` ✓
5. `test_section15_i0_interaction_response.py` ✓
6. `test_section15_b8_interaction_idempotency.py` ✓
7. `test_gate4c_interaction_events.py` ✓

### ۲۹.۵ B8 corrected assertion + PostgreSQL runtime
| Test | Result |
|------|--------|
| `test_migration_source_defines_index_and_fail_closed_preflight` | **PASSED** |
| `test_concurrent_duplicates_produce_one_row` | **PASSED** |
| `test_migration_upgrade_creates_index_on_postgres` | **PASSED** |
| `test_migration_preflight_fails_closed_on_duplicates` | **PASSED** |

B8 `_require_postgres` tests **skip نشدند** — همه اجرا و passed.

### ۲۹.۶ ماتریس پوشش Section 15 (verified)
| حوزه | وضعیت |
|------|--------|
| A1 timezone/grouping/ISO week/current_group_key | **verified passed** |
| A1 inbox metadata/ownership/safe context | **verified passed** |
| B4 auth 401/ownership 403/JWT | **verified passed** |
| B6 channel precedence | **verified passed** |
| B7 invalid language → en | **verified passed** |
| I0 `message`/LLM bypass/auth | **verified passed** (3 tests) |
| B8 sequential/null-conversation/dedupe/isolation | **verified passed** |
| B8 PG concurrency/index/preflight runtime | **verified passed** |
| B8 migration static source assertions | **verified passed** |
| Gate4C interaction events | **verified passed** |

### ۲۹.۷ وضعیت نهایی B8
**verified** — 82/82 Section 15 passed؛ freeze 452/452 passed؛ assertion اصلاح‌شده و runtime PostgreSQL B8 تأیید شد.

### ۲۹.۸ ممنوعیت‌ها
production migration، deploy، image publication، SSH، commit مجدد، rerun اضافی — **انجام نشد**. تست محلی — **اجرا نشد**.

### ۲۹.۹ گام بعد
**15-I1** — **unblocked** برای اجرای package بعدی پس از تأیید صریح.

---

## ۳۰) Package 15-I1 — Connected Intelligence Orchestrator Foundation

### ۳۰.۱ مجوز و محدودیت‌ها
| مورد | مقدار |
|------|--------|
| Package | **15-I1** |
| Worktree | `Demo-wt-section15-backend` |
| Branch | `feature/section15/backend-continuity-foundation` |
| Base HEAD | `a17668071e580e456c82dad0d876b28c549825d3` |
| CI پایه | Run **29318539239** success / 82+452 |

**مجاز:** intelligence modules، اتصال `/interact/chat`، تست I1، append به CI step Section 15، flag پیش‌فرض OFF، به‌روزرسانی master log.

**ممنوع:** commit/push/dispatch، تست محلی، migration، deploy، فعال‌سازی flag، frontend، weekly KB، durable memory، nutrition، FCM، Gate 4 visual.

### ۳۰.۲ مسیر تولید قبل از I1
```
POST /interact/chat
  → JWT + ownership + reminder/settings short-circuits
  → (notification verify + InteractionEvent)
  → ConversationBrain(db).process_message(...)   # مستقیم از router
  → InteractionResponse.message
```

### ۳۰.۳ مسیر متصل پس از I1
```
POST /interact/chat
  → JWT + ownership + reminder/settings short-circuits (بدون تغییر مالکیت)
  → (notification verify + InteractionEvent — قبل از orchestrator)
  → IntelligenceOrchestrator.process(...)         # همیشه
       → stages I1 deterministic
       → legacy ConversationBrain via injected/default generator (یک‌بار)
       → validate non-empty message
  → InteractionResponse.message                   # قرارداد عمومی بدون تغییر
```

Orchestrator **disconnected scaffold نیست**: router مسیر generation دیگر `process_message` را مستقیم صدا نمی‌زند؛ همیشه از gateway عبور می‌کند (flag OFF = compatibility، flag ON = structured؛ هر دو از brain استفاده می‌کنند).

### ۳۰.۴ فایل‌های افزوده‌/تغییریافته
| فایل | نقش |
|------|-----|
| `backend/app/services/intelligence/__init__.py` | package export |
| `backend/app/services/intelligence/contracts.py` | context/result/reason codes |
| `backend/app/services/intelligence/feature_flags.py` | `SEDI_INTELLIGENCE_ORCHESTRATOR_V1` default OFF |
| `backend/app/services/intelligence/orchestrator.py` | `IntelligenceOrchestrator` |
| `backend/app/routers/interact.py` | wire generation path |
| `backend/tests/test_section15_i1_intelligence_orchestrator.py` | I1 tests |
| `.github/workflows/ci-backend-tests.yml` | append I1 test path (۸مین فایل) |
| `docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md` | این §۳۰ |

### ۳۰.۵ قرارداد داخلی context
`sedi.intelligence.context.v1` — request-scoped؛ شامل metadata (`request_id` سرورساخت، UTC)، identity از JWT، conversation، locale (`fa|ar|en` + timezone reason)، notification origin فقط شناسه‌های امن، safety constraints، stage trace با reason code، rollout mode. پیام خام و health/body در trace ذخیره نمی‌شوند و به LLM به‌عنوان identity metadata ارسال نمی‌شوند.

### ۳۰.۶ Flag
`SEDI_INTELLIGENCE_ORCHESTRATOR_V1` — پیش‌فرض **false**. Router **همیشه** orchestrator را صدا می‌زند. OFF → `compatibility`؛ ON → `structured` بدون ادعای قابلیت‌های I2–I10. در هیچ محیطی فعال نشده.

### ۳۰.۷ مراحل deterministic
1. `initialize_request` → `CTX_INITIALIZED`
2. `resolve_safe_identity` → `IDENTITY_FROM_JWT`
3. `resolve_locale_context` → `LANGUAGE_NORMALIZED` (+ `TIMEZONE_AVAILABLE`/`TIMEZONE_UNAVAILABLE`)
4. `resolve_conversation_origin` → `NOTIFICATION_CONTEXT_VERIFIED`/`ABSENT`
5. `prepare_compatibility_generation` → `COMPATIBILITY_GENERATOR_SELECTED` (+ `STRUCTURED_MODE_ACTIVE` اگر ON)
6. `generate_with_legacy_brain` → `LEGACY_GENERATION_COMPLETED` / `GENERATION_FAILED`
7. `validate_generation_result` → `RESPONSE_VALIDATED` / `EMPTY_GENERATION_REJECTED`
8. `complete` → `ORCHESTRATION_COMPLETED`

### ۳۰.۸ شکست / no-bypass
خروجی خالی brain → خطا (نه response خالی موفق). استثنای generator → بدون فراخوانی دوم/مستقیم brain از router. بدون double LLM، double persistence، یا double InteractionEvent. short-circuitهای reminder/settings بیرون از orchestrator می‌مانند.

### ۳۰.۹ سازگاری legacy
ConversationBrain همچنان generator است؛ persistence مالکیت قبلی حفظ شده (brain برای path عادی؛ router برای settings). قرارداد عمومی `InteractionResponse` و OpenAPI بدون تغییر مورد انتظار.

### ۳۰.۱۰ تست‌ها
`backend/tests/test_section15_i1_intelligence_orchestrator.py` — پوشش orchestrator invocation، یک‌بار بودن generator، JWT identity، flag OFF/ON، stage order، reason codes ایمن، locale/timezone، notification safe IDs، concurrency، empty/exception fail-closed، reminder/settings short-circuits، بدون LLM خارجی.

تست‌های موجود که `ConversationBrain.process_message` را patch می‌کنند (I0/Gate4C) بدون بازنویسی مکانیکی حفظ شدند — مرز call هنوز به همان method می‌رسد.

### ۳۰.۱۱ CI
گام `Section 15 backend foundation tests` اکنون ۸ path صریح دارد؛ I1 آخرین آیتم است. بدون تغییر trigger/secret/runner/DB/deploy.

### ۳۰.۱۲ بسته‌های نام‌دار باقی‌مانده (unowned نیست)
weekly Knowledge Engine، durable/consent memory، semantic summary، nutrition intelligence، missing-info، FCM `user_id`، Gate 4 visuals — متعلق به packages بعدی Section 15 هستند.

### ۳۰.۱۳ وضعیت
**implemented but unverified pending GitHub Actions**

| عمل | وضعیت |
|-----|--------|
| تست محلی / pytest | **اجرا نشد** |
| commit / push / dispatch | **انجام نشد** |
| migration / deploy / flag activation | **انجام نشد** |

### ۳۰.۱۴ گام بعد
review → commit approval → push/CI approval (انتظار: Section 15 شامل I1 سبز).

---

## ۳۱) Package 15-I1 — push + CI validation @ `e9da0c2` — **blocked**

### ۳۱.۱ commit و push
| مورد | مقدار |
|------|--------|
| Commit | `e9da0c2f540401e70c74a5cab6d7eec3af7ab0f0` |
| Subject | `feat(intelligence): connect deterministic chat orchestrator` |
| Parent | `a17668071e580e456c82dad0d876b28c549825d3` |
| Push timestamp (UTC) | ۲۰۲۶-۰۷-۱۴ ~15:38Z |
| Remote SHA verified | `e9da0c2f540401e70c74a5cab6d7eec3af7ab0f0` |
| `origin/main` | `89b79ad3fc20236a23ffae65fd868aafb60843e8` (بدون تغییر) |
| Flag `SEDI_INTELLIGENCE_ORCHESTRATOR_V1` | **inactive** (default false؛ در CI فعال نشد) |

### ۳۱.۲ GitHub Actions run
| مورد | مقدار |
|------|--------|
| Workflow | Backend V1 freeze tests |
| Path | `.github/workflows/ci-backend-tests.yml` |
| Run ID | **29346252298** |
| URL | https://github.com/javadmeighani-oss/sedi-backend/actions/runs/29346252298 |
| Event | workflow_dispatch |
| Branch | `feature/section15/backend-continuity-foundation` |
| Head SHA | `e9da0c2f540401e70c74a5cab6d7eec3af7ab0f0` |
| Created (UTC) | ۲۰۲۶-۰۷-۱۴ 15:38:56Z |
| Duration | ~1m43s |
| **Conclusion** | **failure** |

### ۳۱.۳ Existing freeze suite (actual)
| Step | Passed |
|------|--------|
| Section 10 + contract subset | **91** |
| contracts (incl. OpenAPI snapshot) | **27** |
| interact stabilization | **147** |
| OTP/SMS gateway | **171** |
| acceptance subset | **12** (3+6+1+1+1) |
| notification prefs | **4** |
| **جمع freeze** | **452** (0 failed) |

`alembic upgrade head` موفق روی ephemeral PostgreSQL (`127.0.0.1:5432/sedi_test`)؛ revision `050_gate4_event_idem` فقط ephemeral. production/staging تماس نگرفته.

### ۳۱.۴ Section 15 step — totals
| مورد | مقدار |
|------|--------|
| Collected | **114** |
| Passed | **108** |
| Failed | **6** |
| Skipped | **0** |
| Deselected | **0** |
| Warnings | 1 |
| Duration | ~2.59s |

**هشت فایل explicit جمع‌آوری شد:**
1. `test_memory_history_timezone_v1.py` ✓
2. `test_notification_inbox_gate4_v1.py` ✓
3. `test_gate4_push_channel_routing_v1.py` ✓
4. `test_notification_api_b2.py` ✓
5. `test_section15_i0_interaction_response.py` ✓
6. `test_section15_b8_interaction_idempotency.py` ✓
7. `test_gate4c_interaction_events.py` ✓
8. `test_section15_i1_intelligence_orchestrator.py` ✗ (۶ failure)

Baseline قبلی **۸۲/۸۲** همچنان passed (رگرسیون A1/I0/B8/Gate4C دیده نشد). I1 collected ≈ **۳۲** تست؛ **۲۶ passed / ۶ failed**.

### ۳۱.۵ شکست‌های دقیق I1
| Test | Error | Classification |
|------|-------|----------------|
| `test_trace_excludes_raw_user_message_and_user_id` | `TypeError: can only concatenate tuple (not "list") to tuple` (line 165) | **test bug** — `reason_codes` (tuple) + `list(stage_names)` |
| `test_notification_origin_uses_safe_ids_only` | همان `TypeError` (line 262) | **test bug** — همان الگوی join |
| `test_language_normalization[fa-fa]` | `assert 'en' == 'fa'` (line 204) | **code** — `OrchestrationResult.language` از خروجی generator/`_legacy_ok` (`language=en`) می‌آید، نه از locale نرمال‌شده ورودی |
| `test_language_normalization[FA-fa]` | `assert 'en' == 'fa'` | **code** (همان) |
| `test_language_normalization[ar-ar]` | `assert 'en' == 'ar'` | **code** (همان) |
| `test_two_users_do_not_share_state` | `assert 'en' == 'fa'` برای user B | **code** (همان منبع language) |

`LANGUAGE_NORMALIZED` در reason codes برای locale stage ثبت می‌شود، اما `result.language` نهایی با brain stub overwrite می‌شود.

کد/تست در این بسته **تغییر داده نشد**. Rerun انجام نشد.

### ۳۱.۶ ماتریس پوشش I1 (evidence از logs)

| # | رفتار | وضعیت |
|---|--------|--------|
| 1 | Router always enters orchestrator | **verified passed** |
| 2 | No direct normal-path brain call outside orchestrator | **verified passed** |
| 3 | Compatibility mode flag OFF | **verified passed** |
| 4 | Structured mode flag ON | **verified passed** |
| 5 | Flag default false | **verified passed** |
| 6 | Legacy generator exactly once | **verified passed** |
| 7 | Existing response message preserved | **verified passed** |
| 8 | JWT/server identity source | **verified passed** |
| 9 | Caller `user_id` cannot replace identity | **verified passed** |
| 10 | Request-scoped state | **verified passed** (request_id unique + concurrent traces) |
| 11 | User/concurrent isolation | **executed failed** (language assert for user B); concurrency traces **verified passed** |
| 12 | Unique server request IDs | **verified passed** |
| 13 | fa/ar/en normalization on result.language | **executed failed** (fa/ar) |
| 14 | Invalid-language fallback | **verified passed** (xx/empty/invalid → en) |
| 15 | Safe timezone reason codes | **verified passed** |
| 16 | Safe notification identifiers only | **executed failed** (test TypeError before full assert) |
| 17 | No raw message/user ID/health in trace | **executed failed** (test TypeError) |
| 18 | Deterministic stage order | **verified passed** |
| 19 | Safe reason codes | **verified passed** |
| 20 | Empty output failure | **verified passed** |
| 21 | Generator exception no bypass/second call | **verified passed** |
| 22 | No duplicate persistence/InteractionEvent | **verified passed** |
| 23 | Reminder/settings short-circuit compatibility | **verified passed** |
| 24 | Public InteractionResponse.message compatibility | **verified passed** |
| 25 | No external LLM/network in tests | **verified passed** |

### ۳۱.۷ وضعیت نهایی I1
**blocked** — workflow failure به‌خاطر ۶ تست I1؛ freeze 452 سبز؛ ۸۲ baseline Section 15 سبز؛ I1 کامل verified نیست.

### ۳۱.۸ ممنوعیت‌ها
production migration، deploy، SSH، image، flag activation، commit، rerun، اصلاح کد — **انجام نشد**. تست محلی — **اجرا نشد**.

### ۳۱.۹ گام بعد
**Package 15-I1-TestFix** (یا معادل): اصلاح (۱) TypeError در join tuple/list تست‌ها؛ (۲) منبع `result.language` در orchestrator تا locale نرمال‌شده حفظ شود یا stub generator زبان را پاس دهد — سپس commit → push → یک dispatch. **15-I2 فقط پس از I1 verified.**

---

## ۳۲) Package 15-I1-TestFix — اصلاح language ownership + TypeError تست

### ۳۲.۱ Run مرجع
| مورد | مقدار |
|------|--------|
| Run ID | **29346252298** |
| URL | https://github.com/javadmeighani-oss/sedi-backend/actions/runs/29346252298 |
| Head SHA | `e9da0c2f540401e70c74a5cab6d7eec3af7ab0f0` |
| Section 15 | **114** collected / **108** passed / **6** failed / **0** skipped |
| Baseline هفت فایل قبلی | **82/82** passed (بدون رگرسیون) |

### ۳۲.۲ شش failure
| Test | Root cause class |
|------|------------------|
| `test_language_normalization[fa-fa]` | language ownership (code) |
| `test_language_normalization[FA-fa]` | language ownership (code) |
| `test_language_normalization[ar-ar]` | language ownership (code) |
| `test_two_users_do_not_share_state` | language ownership (code) |
| `test_trace_excludes_raw_user_message_and_user_id` | tuple+list TypeError (test) |
| `test_notification_origin_uses_safe_ids_only` | tuple+list TypeError (test) |

فقط **دو** علت ریشه؛ علت سوم نیست.

### ۳۲.۳ اصلاح language ownership (product)
فایل: `backend/app/services/intelligence/orchestrator.py`

**قبل:** `out_language` از `raw["language"]` generator گرفته می‌شد (stub همیشه `en`).

**بعد:** `out_language = ctx.locale.language` — locale نرمال‌شدهٔ request مالک deterministic است. فیلد language خروجی legacy generator در I1 برای نتیجهٔ نهایی **نادیده** گرفته می‌شود؛ generator فقط مالک متن `message` می‌ماند.

### ۳۲.۴ اصلاح TypeError تست
فایل: `backend/tests/test_section15_i1_intelligence_orchestrator.py`

ساخت sequence یکنواخت با `list(result.reason_codes) + list(result.stage_names) [...]` قبل از join. assertionهای privacy (user id، raw message، RAW BODY، health) **حفظ و اجراپذیر** شدند؛ بدون suppress/xfail.

افزوده: `test_result_language_ignores_legacy_generator_language_in_both_modes` برای fa/ar/en در modeهای OFF و ON.

### ۳۲.۵ فایل‌های تغییر یافته
1. `backend/app/services/intelligence/orchestrator.py`
2. `backend/tests/test_section15_i1_intelligence_orchestrator.py`
3. `docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md` (این §۳۲)

**تغییر نداده:** workflow، contracts، router، migration، frontend، feature-flag semantics، schema عمومی.

### ۳۲.۶ وضعیت
**implemented but unverified pending GitHub Actions**

| عمل | وضعیت |
|-----|--------|
| تست محلی | **اجرا نشد** |
| commit / push / dispatch | **انجام نشد** |
| migration / deploy / flag activation | **انجام نشد** |

### ۳۲.۷ گام‌های بعد
1. review
2. commit approval
3. push + یک `workflow_dispatch` دقیق @ SHA جدید

---

## ۳۳) Package 15-I1-TestFix — push + CI validation @ `a704b15` — **verified**

### ۳۳.۱ commit و push
| مورد | مقدار |
|------|--------|
| Commit | `a704b15d7dcbda8c00b4ca081f6bd974a3a9e345` |
| Subject | `fix(intelligence): own result language from normalized request locale` |
| Parent | `e9da0c2f540401e70c74a5cab6d7eec3af7ab0f0` |
| Push timestamp (UTC) | ۲۰۲۶-۰۷-۱۴ ~15:55Z |
| Remote SHA verified | `a704b15d7dcbda8c00b4ca081f6bd974a3a9e345` |
| `origin/main` | `89b79ad3fc20236a23ffae65fd868aafb60843e8` (بدون تغییر) |
| Flag `SEDI_INTELLIGENCE_ORCHESTRATOR_V1` | **inactive** (default false) |

### ۳۳.۲ GitHub Actions run
| مورد | مقدار |
|------|--------|
| Workflow | Backend V1 freeze tests |
| Run ID | **29347442538** |
| URL | https://github.com/javadmeighani-oss/sedi-backend/actions/runs/29347442538 |
| Event | workflow_dispatch |
| Branch | `feature/section15/backend-continuity-foundation` |
| Head SHA | `a704b15d7dcbda8c00b4ca081f6bd974a3a9e345` |
| Created (UTC) | ۲۰۲۶-۰۷-۱۴ 15:55:13Z |
| Duration | ~1m47s |
| **Conclusion** | **success** |

### ۳۳.۳ Existing freeze suite (actual)
| Step | Passed |
|------|--------|
| Section 10 + contract | **91** |
| contracts / OpenAPI | **27** |
| interact stabilization | **147** |
| OTP/SMS gateway | **171** |
| acceptance subset | **12** (3+6+1+1+1) |
| notification prefs | **4** |
| **جمع freeze** | **452** (0 failed) |

`alembic upgrade head` موفق روی ephemeral PostgreSQL؛ `050_gate4_event_idem` فقط ephemeral. production/staging تماس نگرفته.

### ۳۳.۴ Section 15 step
| مورد | مقدار |
|------|--------|
| Collected | **115** |
| Passed | **115** |
| Failed | **0** |
| Skipped | **0** |
| Deselected | **0** |
| Warnings | 1 |
| Duration | ~2.56s |

**هشت فایل explicit — همه passed:**
1. `test_memory_history_timezone_v1.py`
2. `test_notification_inbox_gate4_v1.py`
3. `test_gate4_push_channel_routing_v1.py`
4. `test_notification_api_b2.py`
5. `test_section15_i0_interaction_response.py`
6. `test_section15_b8_interaction_idempotency.py`
7. `test_gate4c_interaction_events.py`
8. `test_section15_i1_intelligence_orchestrator.py`

Baseline غیر-I1 = **۸۲/۸۲** passed. I1 = **۳۳** tests (**۳۳/۳۳** passed). جمع 115 (= 82 + 33؛ +۱ نسبت به run شکست‌خورده به‌خاطر regression جدید).

### ۳۳.۵ شش failure قبلی → این run
| Test | Result |
|------|--------|
| `test_language_normalization[fa-fa]` | **PASSED** |
| `test_language_normalization[FA-fa]` | **PASSED** |
| `test_language_normalization[ar-ar]` | **PASSED** |
| `test_two_users_do_not_share_state` | **PASSED** |
| `test_trace_excludes_raw_user_message_and_user_id` | **PASSED** |
| `test_notification_origin_uses_safe_ids_only` | **PASSED** |

### ۳۳.۶ regression جدید
| Test | Result |
|------|--------|
| `test_result_language_ignores_legacy_generator_language_in_both_modes` | **PASSED** |

(همچنین تمام cases پارامتری زبان: en-US/xx/empty/invalid → en — **PASSED**)

### ۳۳.۷ ماتریس پوشش I1 (verified)
| رفتار | وضعیت |
|--------|--------|
| Router → orchestrator connected | **verified passed** |
| Compatibility mode (flag OFF) | **verified passed** |
| Structured mode (flag ON) | **verified passed** |
| Flag default false | **verified passed** |
| Single generator call | **verified passed** |
| Normalized language ownership | **verified passed** |
| fa/ar/en/invalid behavior | **verified passed** |
| Two-user language isolation | **verified passed** |
| Request/concurrency isolation | **verified passed** |
| Server request IDs | **verified passed** |
| JWT identity | **verified passed** |
| Caller user_id rejection | **verified passed** |
| Deterministic stage order | **verified passed** |
| Safe reason codes | **verified passed** |
| No raw message/user ID/health in trace | **verified passed** |
| Safe notification origin | **verified passed** |
| Empty output failure | **verified passed** |
| Generator exception without bypass | **verified passed** |
| No duplicate persistence/event | **verified passed** |
| Reminder/settings compatibility | **verified passed** |
| Public response compatibility | **verified passed** |
| No external LLM/network | **verified passed** |

### ۳۳.۸ وضعیت نهایی I1
**verified** — 115/115 Section 15؛ freeze 452/452؛ شش failure قبلی سبز؛ regression زبان سبز؛ flag inactive.

### ۳۳.۹ ممنوعیت‌ها
production migration، deploy، SSH، image، flag activation، commit، rerun — **انجام نشد**. تست محلی — **اجرا نشد**.

### ۳۳.۱۰ گام بعد
**15-I2** — **unblocked** برای اجرای package بعدی پس از تأیید صریح.

---

## ۳۴) Package 15-I2 — Connected Authorized Context Adapters

### ۳۴.۱ مجوز و محدودیت‌ها
| مورد | مقدار |
|------|--------|
| Package | **15-I2** |
| Base HEAD | `a704b15d7dcbda8c00b4ca081f6bd974a3a9e345` |
| CI پایه | Run **29347442538** — 452 freeze + 115 Section 15 (I1 verified) |

**ممنوع حفظ شد:** commit/push/dispatch، تست محلی، migration، durable memory write، KB hybrid، nutrition، FCM، frontend، flag activation، deploy.

### ۳۴.۲ مصرف فعلی (inventory خلاصه)
| کلاس | منابع |
|------|--------|
| A — مصرف chat امروز | Persona+`[USER_CONTEXT]`، `[USER_PROFILE]`، optional Local/RAG، CARE (پزشکی)، notification امن، ۱۰ turn حافظه |
| B — ذخیره بدون مصرف chat | Vitals خام، caregiver phone، full care dict، quiet_hours در UCS، KcUserFact |
| C — scaffold جدا | `unified_context_builder`، `prompt_assembler` (روی مسیر chat نیستند) |
| D — خارج از گسترش I2 | body اعلان، raw health/dose، caregiver phones، device signals، cross-user |

### ۳۴.۳ دامنه included / excluded I2
**Included (فقط منابع قبلاً مصرف‌شده):** profile پایه، lifestyle/goals summary، conditions+medications (همان RAG helpers)، DailyMemorySummary + turns محدود، notification امن.

**Excluded (query/projection نشد):** caregivers، emergency contacts، raw device/vitals/signals، notification prefs، InteractionEvent timeline، KcUserFact، KB جدید، شناسه‌های داخلی مخفی، داده کاربر دیگر.

### ۳۴.۴ Adapterها
`ProfileContextAdapter`، `LifestyleContextAdapter`، `HealthContextAdapter`، `CurrentMemoryContextAdapter`، `SafeNotificationContextAdapter` — همه با `authenticated_user_id` سرورساخت، session درخواست، بدون state سراسری.

### ۳۴.۵ قرارداد / consent / freshness
`context_types.py`: provenance، sensitivity، consent (`explicit|legacy_scope|unknown|denied`)، freshness (`fresh|stale|unknown|not_applicable`). Consent صریح ساخته نمی‌شود؛ داده مسیر فعلی = `legacy_scope`. بدون timestamp جعلی → freshness `unknown`.

### ۳۴.۶ Precedence / conflict / budgets
ترتیب adapter قطعی؛ precedence منبع؛ conflict هم‌سطح → mark + حذف از projection. Budgets: 10/section، 40 total، 3500 chars projection، 10 memory turns؛ truncation با reason امن.

### ۳۴.۷ اتصال generation
- Flag OFF: assembly **skipped**؛ brain legacy بدون تغییر.
- Flag ON: assembler اجرا → projection به `ConversationBrain.process_message(..., use_structured_context=True)`؛ USER_CONTEXT/USER_PROFILE/Local RAG/RAG_CONTEXT/Gate3 care/notification/history **دوباره‌بارگیری نمی‌شوند**؛ یک generator call؛ failure assembly → fail-closed بدون bypass.

### ۳۴.۸ فایل‌ها
| مسیر | نقش |
|------|-----|
| `intelligence/context_types.py` | types/budgets |
| `intelligence/adapters.py` | ۵ adapter |
| `intelligence/assembler.py` | assembler + projection |
| `intelligence/contracts.py` | stage assemble + reason codes |
| `intelligence/orchestrator.py` | wire structured assembly |
| `intelligence/__init__.py` | exports |
| `core/conversation/brain.py` | optional prebuilt context path |
| `tests/test_section15_i2_context_adapters.py` | I2 tests |
| `tests/test_section15_i1_...` | سازگاری stage/kwargs |
| `.github/workflows/ci-backend-tests.yml` | مسیر نهم |
| master log | این §۳۴ |

### ۳۴.۹ CI
گام Section 15 اکنون **۹** path صریح دارد (I2 آخرین).

### ۳۴.۱۰ وضعیت
**implemented but unverified pending GitHub Actions**

بدون تست محلی / commit / push / dispatch / migration / deploy / flag activation.

### ۳۴.۱۱ بسته‌های نام‌دار باقی‌مانده
I3 missing-info/intent؛ I4 safety/risk؛ I5 governed KB؛ I6 memory writes/consent؛ I7 semantic summaries؛ I8 nutrition؛ notification intelligence؛ weekly Knowledge Engine؛ FCM hardening؛ frontend intelligence UX؛ Gate 4 visuals.

### ۳۴.۱۲ گام بعد
review → commit approval → push/CI approval.

---

## ۳۵) Package 15-I2-PreCommitAudit — سیاست precedence / budget / parity / حریم سلامت

### ۳۵.۱ وضعیت پایه
| مورد | مقدار |
|------|--------|
| Package | **15-I2-PreCommitAudit** |
| HEAD | `a704b15d7dcbda8c00b4ca081f6bd974a3a9e345` |
| Scope dirty | فقط مسیرهای I2 (+ CI + master log) |

### ۳۵.۲ Precedence قبل از audit
`SOURCE_PRECEDENCE`: PROFILE=50، HEALTH=45، LIFESTYLE=40، MEMORY=30، NOTIFICATION=20 — **ادعای authority بدون evidence مخزن**.
Assembler نابرابر precedence را **خاموش supersede** می‌کرد.

### ۳۵.۳ شواهد authority در مخزن
هیچ canonical source-of-truth برای supersession بین adapter sectionها یافت نشد.
ترتیب قطعی projection مجاز است؛ authority برای حل تناقض فعال نیازمند evidence است — evidence غایب بود.

### ۳۵.۴ اصلاح supersession
سیاست نهایی:
1. مقدار یکسان روی یک canonical key → coalesce + حفظ provenance ترکیبی.
2. مقادیر متفاوت → conflicted + حذف از projection + `CONTEXT_CONFLICT_DETECTED`.
3. `SOURCE_SORT_RANK` / `ADAPTER_ORDER` فقط ordering (نه authority).
4. تازگی به‌تنهایی truth نیست.

### ۳۵.۵ Budgets و provenance
| مقدار | provenance | طبقه |
|------|------------|------|
| memory turns=10 | evidence: `get_recent_messages(..., limit=10)` | evidence-backed |
| 10/section | — | `I2 conservative technical safety defaults pending evaluation` |
| 40 total | — | همان technical default |
| 3500 projection chars | — | technical default (نه token؛ نه سیاست پزشکی) |

تمرکز در `ContextBudgets`؛ override تستی بدون state سراسری؛ truncation فقط روی whole lines/items؛ `CONTEXT_BUDGET_TRUNCATED` فقط هنگام truncation واقعی.

### ۳۵.۶ ماتریس parity legacy→structured
| Legacy | Structured | طبقه |
|--------|------------|------|
| Persona/system | `build_system_prompt_with_context` همچنان | parity preserved |
| USER_CONTEXT | Profile+Lifestyle+Memory daily | parity preserved |
| USER_PROFILE | Profile knowledge + UserFact | parity corrected |
| RAG_CONTEXT (goals/habits/restrictions/events/conditions/meds/identity) | Lifestyle Gate2 + Health RAG helpers + identity facts | parity preserved (subset LLM-serialized) |
| Gate3 CARE curated KB snippets | deferred | `GATE3_CARE_SNIPPETS_NOT_CONNECTED` → I5 |
| Local/hybrid KB | deferred | `GOVERNED_KB_NOT_CONNECTED` → I5 |
| notification safe block | SafeNotificationContextAdapter allowlist | parity preserved |
| last 10 Memory turns | CurrentMemoryContextAdapter | parity preserved |
| doctors/care_plan dump / quiet_hours UCS | intentionally excluded | privacy / not dedicated LLM lines |
| Flag | default OFF | inactive؛ structured **not production-ready** |

### ۳۵.۷ Structured readiness (داخلی فقط)
Reason codes: `CONTEXT_ADAPTERS_CONNECTED`، `GOVERNED_KB_NOT_CONNECTED`، `GATE3_CARE_SNIPPETS_NOT_CONNECTED`، `MISSING_INFORMATION_ENGINE_NOT_CONNECTED`، `ADVANCED_SAFETY_RISK_ENGINE_NOT_CONNECTED`، `CONSENT_AWARE_MEMORY_WRITES_NOT_CONNECTED`، `SEMANTIC_SUMMARIES_NOT_CONNECTED`، `STRUCTURED_MODE_NOT_PRODUCTION_READY`.

### ۳۵.۸ ماتریس health/medication
| فیلد | legacy brain | حساسیت | consent | LLM | دلیل |
|------|--------------|--------|--------|-----|------|
| medical condition name | yes (RAG) | high | legacy_scope | yes | parity |
| medication name+dosage+times string | yes (`_get_user_medications_for_context`) | high | legacy_scope | yes | evidence-backed preservation |
| raw vitals/signals/clinician notes | no | — | — | no | excluded |
| DB IDs / caregivers | no | — | — | no | excluded |

### ۳۵.۹ Notification privacy
Allowlist هم‌تراز brain/A1: category/template_key/risk_level/source_type/source_id/title/summary/conversation_id/interaction_source + sanitized hints. body/dose/health/FCM dump رد می‌شوند.

### ۳۵.۱۰ No double-load
Assembler یک‌بار `UserContextService.get_user_context`؛ structured brain reload نمی‌کند UCS/USER_PROFILE/RAG/Local/Gate3/notification/history؛ generator یک‌بار؛ failure assembly → صفر generator.

### ۳۵.۱۱ تست‌ها
`test_section15_i2_context_adapters.py` تقویت شد (coalesce، cross-source conflict، budget override، readiness، persona، allowlist، UCS once، …). CI مسیر نهم بدون تغییر نام فایل.

### ۳۵.۱۲ فایل‌های تغییر یافته در این audit
`context_types.py`، `adapters.py`، `assembler.py`، `contracts.py`، `orchestrator.py`، `__init__.py`، `test_section15_i2_context_adapters.py`، master log (§۳۵). brain/CI در صورت نیاز parity از I2 حفظ.

### ۳۵.۱۳ ممنوعیت‌ها
تست محلی / commit / push / dispatch / migration / deploy / flag activation — **انجام نشد**.

### ۳۵.۱۴ وضعیت
**implemented but unverified pending GitHub Actions**

### ۳۵.۱۵ گام بعد
review → commit approval → push/CI approval.

---

## ۳۶) Package 15-I2 — Push + GitHub CI Validation @ `7fabc0f` — **blocked**

### ۳۶.۱ Commit / push
| مورد | مقدار |
|------|--------|
| Commit | `7fabc0f0eb2cc16fb3c160e55a45d927d3272648` |
| Parent | `a704b15d7dcbda8c00b4ca081f6bd974a3a9e345` |
| Subject | `feat(intelligence): connect authorized context adapters` |
| Push | `a704b15..7fabc0f` → `origin/feature/section15/backend-continuity-foundation` |
| Remote feature | `7fabc0f0eb2cc16fb3c160e55a45d927d3272648` |
| origin/main | `89b79ad3fc20236a23ffae65fd868aafb60843e8` (بدون تغییر) |

### ۳۶.۲ CI run
| مورد | مقدار |
|------|--------|
| Run ID | **29350819292** |
| URL | https://github.com/javadmeighani-oss/sedi-backend/actions/runs/29350819292 |
| Workflow | Backend V1 freeze tests |
| Event | workflow_dispatch |
| Branch | feature/section15/backend-continuity-foundation |
| Head SHA | `7fabc0f0eb2cc16fb3c160e55a45d927d3272648` |
| Conclusion | **failure** |

### ۳۶.۳ Freeze totals (غیر Section 15)
مجموع steps غیر Section 15 از log واقعی:
`91 + 27 + 147 + 171 + 3 + 6 + 1 + 1 + 1 + 4` = **452 passed** (مطابق baseline قبلی).
همهٔ freeze steps قبل از Section 15: success.
OpenAPI/contracts: success (درون freeze).
failed/skipped در freeze: **۰**.

### ۳۶.۴ Section 15 totals
| متریک | مقدار |
|--------|--------|
| collected | **146** |
| passed | **143** |
| failed | **3** |
| skipped | **0** |
| deselected | **0** |

### ۳۶.۵ Collection نه فایل (از log)
| فایل | تعداد اجراشده (از خطوط `::`) |
|------|------------------------------|
| test_memory_history_timezone_v1.py | 12 |
| test_notification_inbox_gate4_v1.py | 9 |
| test_gate4_push_channel_routing_v1.py | 10 |
| test_notification_api_b2.py | 12 |
| test_section15_i0_interaction_response.py | 3 |
| test_section15_b8_interaction_idempotency.py | 14 |
| test_gate4c_interaction_events.py | 22 |
| test_section15_i1_intelligence_orchestrator.py | 33 collected / **1 failed** |
| test_section15_i2_context_adapters.py | **31 collected** / **2 failed** / 29 passed |

جمع: 12+9+10+12+3+14+22+33+31 = **146**. هر ۹ فایل collect شدند؛ skip/deselect نداریم.

### ۳۶.۶ Failures (بدون اصلاح کد)
1) `test_section15_i1_intelligence_orchestrator.py::test_flag_on_uses_structured_mode_without_claiming_future_capabilities` (line ~176)
   - Assertion: `assert "missing_info" not in joined`
   - علت: reason code داخلی `MISSING_INFORMATION_ENGINE_NOT_CONNECTED` شامل substring `missing_info` است.
   - طبقه: **test assertion stale vs intentional I2 readiness marker** (نه ادعای قابلیت آینده).

2) `test_section15_i2_context_adapters.py::test_brain_skips_covered_loaders_when_structured_projection_supplied` (line ~622)
   - `mock_mem.get_recent_messages.assert_not_called()` → Called 1 times.
   - شواهد کد: پس از skip تاریخچهٔ prompt، `brain.py` هنوز برای `_extract_name_from_message` مسیر `get_recent_messages(..., limit=5)` را همیشه اجرا می‌کند (~خط 464).
   - طبقه: **product residual double-load** روی memory turns برای name-extract (نه loader تاریخچهٔ ۱۰-turn برای prompt)؛ TestFix باید یا call را در structured mode حذف/جایگزین کند یا assertion را به «history pack loader» محدود کند.
3) `test_section15_i2_context_adapters.py::test_ucs_loaded_once_during_assemble` (line ~634)
   - `mock_ucs.call_count == 1` اما واقعی **3**.
   - طبقه: **product defect / incomplete single-load** — وقتی `get_user_context` مقدار `None` برمی‌گرداند، Profile/Lifestyle adapters دوباره UCS را صدا می‌زنند (`if pack is None: reload`).

### ۳۶.۷ Coverage matrix (نتیجه واقعی از PASSEDها)
| مورد | نتیجه |
|------|--------|
| compatibility assembly skip | passed |
| structured AuthorizedContextAssembler + readiness | passed |
| پنج adapter isolation/empty | passed |
| assembly failure → zero generator | passed |
| identical coalesce | passed |
| conflict exclusion | passed |
| technical budgets / no false truncate / whole-line truncate | passed |
| legacy_scope / no explicit consent | passed |
| notification allowlist / no body | passed |
| cross-user reject / concurrent isolation | passed |
| flag default OFF | passed (I1) |
| I1 regression کلی | **۱ failure** در ادعاهای readiness |
| brain no double-load covered packs | **failed** (get_recent_messages روی mock) |
| UCS once | **failed** (3 calls when pack None) |

### ۳۶.۸ Migration موقت CI
`alembic upgrade head` روی PostgreSQL سرویس Actions موفق؛ chain تا `050_gate4_event_idem` روی DB موقت. هیچ تماس production/staging ندارد.

### ۳۶.۹ ممنوعیت‌ها
local tests / commit پس از push / rerun / production migration / deploy / flag activation — **انجام نشد**.
Flag `SEDI_INTELLIGENCE_ORCHESTRATOR_V1` همچنان default OFF.

### ۳۶.۱۰ وضعیت
**blocked** — Package **15-I2-TestFix** گام بعدی پیشنهادی.
**I3 unblocked نیست.**

§۳۳–§۳۵ حفظ شدند؛ این §۳۶ uncommitted باقی می‌ماند.

---

## ۳۷) Package 15-I2-TestFix — اصلاح سه failure CI بدون تأیید مجدد

### ۳۷.۱ شواهد پایه
| مورد | مقدار |
|------|--------|
| Base SHA | `7fabc0f0eb2cc16fb3c160e55a45d927d3272648` |
| Failed run | **29350819292** |
| Section 15 | 146 collected / 143 passed / **3 failed** / 0 skipped |
| I2 | 31 / 29 / **2** |
| I1 | 33 / 32 / **1** |

### ۳۷.۲ Root causes و اصلاحات
1) **I1 ready assertion stale** — substring `missing_info` با `MISSING_INFORMATION_ENGINE_NOT_CONNECTED` تداخل داشت → assertionهای exact reason-code + عدم وجود stage موتور missing-info + تأیید `STRUCTURED_MODE_NOT_PRODUCTION_READY`.
2) **Hidden memory reload** — `get_recent_messages(limit=5)` برای name extract حتی در structured → در structured mode: بدون فراخوانی memory، بدون `_extract_name_from_message`؛ نام فقط از `structured_preferred_name` (Profile adapter)؛ بدون نام اختراع.
3) **None-as-cache-miss** — adapters با `if pack is None` دوباره UCS می‌زدند → sentinel `USER_CONTEXT_PACK_UNSET`؛ pack=None یعنی loaded-empty؛ UCS دقیقاً یک‌بار در assembler.

### ۳۷.۳ Invariants
compatibility legacy حفظ؛ generator یک‌بار؛ fail-closed روی UCS exception؛ API/migration/workflow/frontend/flag بدون تغییر؛ flag default OFF.

### ۳۷.۴ فایل‌های تغییر یافته
`brain.py`، `adapters.py`، `assembler.py`، `context_types.py` (sentinel)، `test_section15_i1_...`، `test_section15_i2_...`، master log (§۳۷).

### ۳۷.۵ وضعیت
**implemented but unverified pending GitHub Actions rerun**

I2 و I3 همچنان **blocked** تا CI سبز. بدون ادعای تست موفق محلی.

### ۳۷.۶ گام بعد
review → commit approval → push → one CI dispatch.

---

## ۳۸) Package 15-I2-PreferredName-Hardening — بستن کانال جانبی نام

### ۳۸.۱ دلیل توقف commit قبلی
Audit commit-only نشان داد `preferred_name_from_items` روی snapshot پیش از char-budget انتخاب می‌شد و `may_send_to_llm` / consent denied را چک نمی‌کرد → PII side-channel جدا از projection.

### ۳۸.۲ اصلاح
- `is_llm_projection_eligible` یک policy مرکزی (active، not conflicted، may_send_to_llm، consent نه denied، unknown+high خارج).
- `build_compatibility_projection` خطوط را با همان policy می‌سازد، itemهای final-included را نگه می‌دارد، سپس `preferred_name_from_included_items`.
- `ContextSnapshot.preferred_name = None` (پیش‌از-projectionمصرف‌نشدنی).
- حذف helper ناامن روی snapshot خام از adapters.
- conflict/empty/whitespace/item-budget/char-budget → None.
- نام در reason codes / stages نیست؛ cross-user همچنان در assembler fail-closed است.

### ۳۸.۳ فایل‌های این hardening
`context_types.py`، `assembler.py`، `adapters.py` (حذف helper)، `test_section15_i2_...`، master log (§۳۸).
brain/I1 در این package لمس نشدند.

### ۳۸.۴ وضعیت
**implemented but unverified pending GitHub Actions rerun**

I2 و I3 همچنان **blocked**. بدون API/workflow/migration/frontend/flag change. بدون ادعای pass محلی.

### ۳۸.۵ گام بعد
review → commit (TestFix+Hardening با هم) → push → CI.

---

## ۳۹) Package 15-I2-TestFix+Hardening — Final Push + CI @ `4f1633b` — **blocked**

### ۳۹.۱ Commit / push
| مورد | مقدار |
|------|--------|
| Commit | `4f1633b01243c4f5a83bd305bac96ad47dcdf1e3` |
| Parent | `7fabc0f0eb2cc16fb3c160e55a45d927d3272648` |
| Subject | `fix(intelligence): enforce single-load structured context` |
| Remote feature | `4f1633b01243c4f5a83bd305bac96ad47dcdf1e3` |
| origin/main | `89b79ad3fc20236a23ffae65fd868aafb60843e8` (بدون تغییر) |

### ۳۹.۲ CI run
| مورد | مقدار |
|------|--------|
| Run ID | **29353839958** |
| URL | https://github.com/javadmeighani-oss/sedi-backend/actions/runs/29353839958 |
| Event | workflow_dispatch |
| Head SHA | `4f1633b01243c4f5a83bd305bac96ad47dcdf1e3` |
| Conclusion | **failure** |

### ۳۹.۳ Freeze
`91+27+147+171+3+6+1+1+1+4` = **452 passed**. contracts/OpenAPI سبز. failed/skipped freeze = 0.

### ۳۹.۴ Section 15
| متریک | مقدار |
|--------|--------|
| collected | **161** |
| passed | **159** |
| failed | **2** |
| skipped | **0** |
| deselected | **0** |
| duration | **3.58s** |

۹ فایل collect شدند (از log `::` counts تقریبی): timezone12 / inbox9 / gate4push10 / notif_api12 / i03 / b814 / gate4c22 / i133 / i248.

### ۳۹.۵ سه failure قبلی (run 29350819292) — در این run
| تست | نتیجه |
|------|--------|
| `test_flag_on_uses_structured_mode_without_claiming_future_capabilities` | **PASSED** |
| `test_brain_skips_covered_loaders_when_structured_projection_supplied` | **PASSED** |
| `test_ucs_loaded_once_when_pack_is_none` (+ object) | **PASSED** |

### ۳۹.۶ Failures جدید (۲)
1) `test_ucs_two_users_do_not_share_pack_cache` (~L766)
   - `TypeError: lambda() missing 1 required positional argument: 'uid'` هنگام patch `get_user_context`
   - طبقه: **test harness defect** (side_effect signature اشتباه برای instance method)؛ product path isolation جدا با concurrent test پاس شد.

2) `test_preferred_name_none_when_dropped_by_char_budget` (~L1080)
   - `ValueError: invalid_projection_budget` چون `ContextBudgets` حداقل projection chars را ۶۴ می‌خواهد و تست ۴۰ گذاشت.
   - طبقه: **test budget fixture invalid در برابر validation محصول**؛ behavior char-budget هنوز نیاز به fixture ≥۶۴ با محتوای بزرگ‌تر دارد.

### ۳۹.۷ Preferred-name / hardening coverage (از log)
eligible / may_send=false / denied / item-budget / conflict / whitespace / coalesce / not-in-trace / shared policy / no-invent / structured zero reload / UCS none+object+exception→zero gen / compatibility recent-messages — **PASSED**.
char-budget preferred-name و ucs_two_users — **FAILED** (بالا).

### ۳۹.۸ Regression matrix
A1/B4/B6/B7/I0/B8/Gate4C/I1: سبز در همین session؛ I2: ۲ failure تست جدید.

### ۳۹.۹ Migration موقت
`alembic upgrade head` تا `050_gate4_event_idem` روی Postgres Actions موفق. بدون production/staging.

### ۳۹.۱۰ ممنوعیت‌ها
local tests / code fix / commit / rerun / production migration / deploy / flag activation — **انجام نشد**. Flag default OFF.

### ۳۹.۱۱ وضعیت
**I2 = blocked** · **I3 = blocked**
گام بعدی پیشنهادی: **15-I2-TestFix2** (فقط دو harness defect بالا).

§۳۳–§۳۸ حفظ شدند؛ این §۳۹ uncommitted است.

---

## ۴۰) Package 15-I2-TestFix2 — اصلاح فقط دو harness (implementation only)

### ۴۰.۱ مرجع
| مورد | مقدار |
|------|--------|
| HEAD (unverifiable until CI) | `4f1633b01243c4f5a83bd305bac96ad47dcdf1e3` |
| Run مرجع failure | **29353839958** |
| URL | https://github.com/javadmeighani-oss/sedi-backend/actions/runs/29353839958 |
| Section 15 آن run | **161 collected / 159 passed / 2 failed / 0 skipped / 0 deselected** |
| Freeze | **452 passed** |

### ۴۰.۲ دو failure و root cause
1) `test_ucs_two_users_do_not_share_pack_cache`
   - `TypeError: lambda() missing 1 required positional argument: 'uid'`
   - root cause: `side_effect=lambda self, uid: …` با فراخوانی واقعی MagicMock روی class method (۱ آرگومان یا binding متفاوت از فرض test) سازگار نبود → داخل assembler به `ContextAssemblyError` wrap شد.

2) `test_preferred_name_none_when_dropped_by_char_budget`
   - `ValueError: invalid_projection_budget`
   - root cause: harness با `max_compatibility_projection_chars=40` در برابر حداقل تولیدی ۶۴.

سه failure قبلی run 29350819292 در همان run همچنان **PASSED** بودند (بدون دست‌کاری مجدد).

### ۴۰.۳ اصلاح mock / isolation
- Production loader: `UserContextService.get_user_context(self, user_id: int)` — یک‌بار per assemble در assembler.
- Harness: `side_effect=[pack_a, pack_b]` ترتیبی صریح برای دو assembly، بدون `*args/**kwargs` برای پنهان‌کردن mismatch.
- استخراج `user_id` از آخرین positional arg هر call.
- assertions: call_count==2، uid جدا، preferred_name/projection بدون cross-user leakage، دو request جدا.

### ۴۰.۴ اصلاح char-budget harness
- `ContextBudgets(..., max_compatibility_projection_chars=64)` — حداقل معتبر؛ validation محصول **بدون تغییر**.
- خط filler `profile.addressing_preference` (sort قبل از preferred_name) با display طول ۳۰ → line ۴۲؛ با header دقیقاً ۶۴ char پر می‌شود.
- preferred-name eligible و active می‌ماند؛ فقط در final whole-line char budget حذف می‌شود → `proj.preferred_name is None`، `proj.truncated is True`.
- item budgets باز؛ `CONTEXT_BUDGET_TRUNCATED` در snapshot از item-budget جعلی ثبت نمی‌شود.

### ۴۰.۵ محدوده فایل
فقط:
- `backend/tests/test_section15_i2_context_adapters.py`
- `docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md` (§۴۰)

`backend/app/**`، workflow، budget validation، assembler/adapters/brain، migration/schema، frontend، feature flag — **unchanged**.

### ۴۰.۶ وضعیت
**implemented but unverified pending GitHub Actions rerun**

**I2 = blocked** · **I3 = blocked**

بدون ادعای pass برای این دو اصلاح. بدون local pytest/Python، بدون stage/commit/push/rerun، بدون production migration/deploy، بدون flag activation.

### ۴۰.۷ پیشنهاد commit (هنوز انجام نشود)
`test(intelligence): correct I2 isolation and budget harnesses`

§۳۳–§۳۹ حفظ شدند؛ این §۴۰ uncommitted است.

---

*پایان گزارش اصلی سکشن ۱۵ — Package 15-I2-TestFix2 implemented unverified — ۲۰۲۶-۰۷-۱۴*

# رفع مشکل OPENAI_API_KEY

## مشکل
`OPENAI_API_KEY` در `.env` به درستی تنظیم نشده است. در نتیجه:
- GPT API کار نمی‌کند
- همه پاسخ‌ها از fallback responses استفاده می‌کنند (یکسان هستند)
- Conversation Brain نمی‌تواند پاسخ‌های طبیعی تولید کند

## راه حل

### 1. بررسی فایل .env

```bash
cd /var/www/sedi/backend
cat .env | grep OPENAI_API_KEY
```

### 2. تنظیم OPENAI_API_KEY صحیح

```bash
# اگر API key دارید، آن را تنظیم کنید:
nano /var/www/sedi/backend/.env
```

یا به صورت مستقیم:

```bash
# حذف خط قدیمی (اگر وجود دارد)
sed -i '/OPENAI_API_KEY/d' /var/www/sedi/backend/.env

# اضافه کردن API key جدید
echo "OPENAI_API_KEY=sk-your-actual-api-key-here" >> /var/www/sedi/backend/.env
```

**⚠️ مهم:** 
- API key را از https://platform.openai.com/account/api-keys دریافت کنید
- API key باید با `sk-` شروع شود
- API key را در `.env` قرار دهید (نه در کد)

### 3. بررسی تنظیمات

```bash
# بررسی که API key تنظیم شده (بدون نمایش مقدار کامل)
grep OPENAI_API_KEY /var/www/sedi/backend/.env | sed 's/=.*/=***HIDDEN***/'
```

### 4. راه‌اندازی مجدد سرویس

```bash
systemctl restart sedi-backend
```

### 5. بررسی وضعیت

```bash
systemctl status sedi-backend --no-pager
```

### 6. بررسی لاگ‌ها

```bash
# بررسی که خطای API key برطرف شده
journalctl -u sedi-backend -n 20 --no-pager | grep -i "api\|error"
```

### 7. تست مجدد

```bash
# تست greeting
curl "http://localhost:8000/interact/greeting?user_id=1&lang=en" | python3 -m json.tool

# تست chat (باید پاسخ‌های متفاوت و طبیعی بدهد)
curl -X POST "http://localhost:8000/interact/chat?message=Hello&name=testuser&secret_key=test123&lang=en" | python3 -m json.tool

# تست دوم (باید متفاوت باشد)
curl -X POST "http://localhost:8000/interact/chat?message=I%20like%20reading&name=testuser&secret_key=test123&lang=en" | python3 -m json.tool
```

## نکات امنیتی

1. **فایل .env را محافظت کنید:**
   ```bash
   chmod 600 /var/www/sedi/backend/.env
   ```

2. **API key را در Git commit نکنید:**
   - `.env` باید در `.gitignore` باشد
   - API key را فقط در سرور تنظیم کنید

3. **از API key قوی استفاده کنید:**
   - API key را از OpenAI dashboard دریافت کنید
   - در صورت لزوم، API key جدید ایجاد کنید

## در صورت عدم دسترسی به API key

اگر API key ندارید:
1. به https://platform.openai.com/account/api-keys بروید
2. API key جدید ایجاد کنید
3. آن را در `.env` تنظیم کنید

## تایید نهایی

پس از تنظیم API key، باید:
- ✅ لاگ‌ها بدون خطای API key باشند
- ✅ پاسخ‌ها طبیعی و متفاوت باشند
- ✅ Conversation Brain به درستی کار کند


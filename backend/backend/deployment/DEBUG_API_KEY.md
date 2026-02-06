# Debug API Key Issue

## مشکل
پاسخ‌ها هنوز یکسان هستند و از fallback responses استفاده می‌شود.

## بررسی‌های لازم

### 1. بررسی لاگ‌های جدید (بعد از restart)

```bash
# بررسی لاگ‌های بعد از restart (07:27:12)
journalctl -u sedi-backend --since "2025-12-26 07:27:12" --no-pager | grep -i "error\|api\|prompts\|openai"
```

### 2. بررسی اینکه API key درست خوانده می‌شود

```bash
# تست مستقیم Python
cd /var/www/sedi/backend
source .venv/bin/activate
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('OPENAI_API_KEY')
if key:
    print(f'API Key found: {key[:20]}...')
    print(f'Length: {len(key)}')
    print(f'Starts with sk-: {key.startswith(\"sk-\")}')
else:
    print('API Key NOT found!')
"
```

### 3. تست مستقیم OpenAI API

```bash
python3 -c "
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

try:
    response = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{'role': 'user', 'content': 'Hello'}],
        max_tokens=10
    )
    print('✅ API Key works!')
    print(f'Response: {response.choices[0].message.content}')
except Exception as e:
    print(f'❌ API Key error: {e}')
"
```

### 4. بررسی فایل .env

```bash
# بررسی کامل فایل .env (بدون نمایش API key کامل)
cat /var/www/sedi/backend/.env | sed 's/OPENAI_API_KEY=.*/OPENAI_API_KEY=***HIDDEN***/'
```

### 5. بررسی Environment Variables در systemd

```bash
# بررسی که systemd از .env استفاده می‌کند
cat /etc/systemd/system/sedi-backend.service | grep EnvironmentFile
```

## مشکلات احتمالی

1. **API key هنوز placeholder است**
   - بررسی کنید که API key واقعی است نه `sk-proj-xxxxxxx`

2. **systemd از .env استفاده نمی‌کند**
   - بررسی کنید که `EnvironmentFile=/var/www/sedi/backend/.env` در service file وجود دارد

3. **API key درست خوانده نمی‌شود**
   - ممکن است مشکل در load_dotenv باشد

4. **API key معتبر نیست**
   - ممکن است API key منقضی شده یا اعتبار ندارد


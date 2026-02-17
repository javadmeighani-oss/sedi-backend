# راهنمای کامل Setup CI/CD - مرحله به مرحله

## 🎯 هدف
Setup سیستم CI/CD که به صورت خودکار backend را از GitHub به سرور ابری deploy کند.

---

## ✅ وضعیت فعلی

- ✅ Workflow file ایجاد شده: `.github/workflows/deploy.yml`
- ✅ Commit و Push شده به GitHub
- ⚠️ نیاز به Setup SSH Key و GitHub Secrets

---

## 📋 مراحل Setup (مرحله به مرحله)

### STEP 1: تولید SSH Key برای GitHub Actions

**در PowerShell (در پوشه backend):**

```powershell
# اطمینان از اینکه در پوشه backend هستید
cd "D:\Rimiya Design Studio\Sedi\software\Demo\backend"

# تولید SSH key
ssh-keygen -t ed25519 -C "github-actions-sedi-backend" -f .github_actions_key -N ""

# نمایش public key (این را کپی کنید)
Get-Content .github_actions_key.pub
```

**خروجی مثال:**
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... github-actions-sedi-backend
```

**⚠️ مهم:** تمام این خروجی را کپی کنید و ذخیره کنید.

---

### STEP 2: اضافه کردن Public Key به سرور

**گزینه A: استفاده از ssh-copy-id (اگر در Windows کار می‌کند)**

```powershell
ssh-copy-id -i .github_actions_key.pub root@91.107.168.130
```

**گزینه B: روش دستی (پیشنهادی)**

**2.1. اتصال به سرور:**
```powershell
ssh root@91.107.168.130
```

**2.2. در سرور، اجرا کنید:**
```bash
# ایجاد پوشه .ssh (اگر وجود ندارد)
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# اضافه کردن public key
nano ~/.ssh/authorized_keys
```

**2.3. در nano editor:**
- به انتهای فایل بروید (Ctrl+End)
- Enter بزنید (خط جدید)
- Public key را paste کنید (از Step 1)
- Ctrl+X، سپس Y، سپس Enter (ذخیره)

**2.4. تنظیم permissions:**
```bash
chmod 600 ~/.ssh/authorized_keys
exit
```

**2.5. تست اتصال (از کامپیوتر محلی):**
```powershell
ssh -i .github_actions_key root@91.107.168.130 "echo 'SSH connection successful! ✅'"
```

اگر پیام "SSH connection successful! ✅" را دیدید، به Step 3 بروید.

---

### STEP 3: اضافه کردن Private Key به GitHub Secrets

**3.1. دریافت Private Key:**

```powershell
# نمایش private key
Get-Content .github_actions_key
```

**⚠️ مهم:** تمام محتوا را کپی کنید (شامل `-----BEGIN OPENSSH PRIVATE KEY-----` و `-----END OPENSSH PRIVATE KEY-----`)

**3.2. رفتن به GitHub:**

1. به این آدرس بروید:
   ```
   https://github.com/javadmeighani-oss/sedi-backend/settings/secrets/actions
   ```

2. روی **"New repository secret"** کلیک کنید

**3.3. اضافه کردن Secret 1 (الزامی):**

- **Name:** `SSH_PRIVATE_KEY`
- **Value:** محتوای private key (از Step 3.1)
- روی **"Add secret"** کلیک کنید

**3.4. اضافه کردن Secret 2 (اختیاری - برای انعطاف بیشتر):**

- **Name:** `SERVER_HOST`
- **Value:** `91.107.168.130`
- روی **"Add secret"** کلیک کنید

**3.5. اضافه کردن Secret 3 (اختیاری):**

- **Name:** `SERVER_USER`
- **Value:** `root`
- روی **"Add secret"** کلیک کنید

---

### STEP 4: Commit .gitignore (اگر نیاز بود)

```powershell
git add .gitignore
git commit -m "chore: Ignore GitHub Actions SSH keys"
git push
```

---

### STEP 5: تست Deployment

**5.1. روش 1: Push یک تغییر کوچک**

```powershell
# ایجاد یک تغییر کوچک (مثلاً یک کامنت)
# یا فقط push کنید (workflow خودکار اجرا می‌شود)
git push
```

**5.2. روش 2: Manual Trigger**

1. به این آدرس بروید:
   ```
   https://github.com/javadmeighani-oss/sedi-backend/actions
   ```

2. روی **"Deploy Backend to Cloud Server"** کلیک کنید

3. روی **"Run workflow"** کلیک کنید

4. Branch را انتخاب کنید: `main`

5. روی **"Run workflow"** کلیک کنید

**5.3. مشاهده Workflow:**

- روی workflow در حال اجرا کلیک کنید
- مراحل را مشاهده کنید
- در صورت خطا، لاگ‌ها را بررسی کنید

**5.4. بررسی روی سرور:**

```powershell
ssh root@91.107.168.130 "systemctl status sedi-backend --no-pager | head -15"
```

---

## ✅ چک‌لیست نهایی

- [ ] SSH key تولید شده
- [ ] Public key به سرور اضافه شده
- [ ] SSH connection تست شده (موفق)
- [ ] Private key به GitHub Secrets اضافه شده
- [ ] `.gitignore` به‌روزرسانی شده
- [ ] Workflow file commit شده
- [ ] اولین deployment تست شده
- [ ] Service روی سرور restart شده

---

## 🔍 Troubleshooting

### مشکل: SSH Connection Failed

**بررسی:**
```powershell
# تست دستی
ssh -i .github_actions_key -v root@91.107.168.130
```

**راه‌حل:**
- بررسی کنید public key درست paste شده
- بررسی permissions: `chmod 600 ~/.ssh/authorized_keys`
- بررسی که key در `~/.ssh/authorized_keys` است

---

### مشکل: GitHub Actions Fails - SSH Error

**بررسی:**
- GitHub Secret `SSH_PRIVATE_KEY` درست است؟
- Private key شامل headers است؟ (`-----BEGIN...` و `-----END...`)
- No extra spaces or line breaks

**راه‌حل:**
- Secret را دوباره اضافه کنید
- مطمئن شوید تمام محتوا کپی شده

---

### مشکل: Service Restart Failed

**بررسی روی سرور:**
```bash
systemctl status sedi-backend
journalctl -u sedi-backend -n 50
```

**راه‌حل:**
- بررسی service file: `/etc/systemd/system/sedi-backend.service`
- بررسی paths و permissions

---

## 📊 بعد از Setup

### هر بار که push می‌کنید:

```powershell
git add .
git commit -m "your message"
git push
```

**به صورت خودکار:**
1. GitHub Actions workflow اجرا می‌شود
2. Code به سرور pull می‌شود
3. Service restart می‌شود
4. Deployment verify می‌شود

### مشاهده History:

```
https://github.com/javadmeighani-oss/sedi-backend/actions
```

---

## 🎉 نتیجه

پس از تکمیل Steps 1-5:
- ✅ هر push به `main` → Deploy خودکار
- ✅ No manual SSH needed
- ✅ Deployment history در GitHub
- ✅ Automatic verification

---

**آماده برای شروع؟** Step 1 را شروع کنید!


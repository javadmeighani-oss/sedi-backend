# رفع مشکل SSH در GitHub Actions

## 🔍 مشکل
GitHub Actions workflow با خطای `Permission denied (publickey, password)` مواجه می‌شود.

## ✅ راه حل

### مرحله 1: SSH Key ایجاد شد
✅ SSH key جدید ایجاد شد:
- **Private Key:** `backend/.github_actions_key`
- **Public Key:** `backend/.github_actions_key.pub`

### مرحله 2: اضافه کردن Public Key به سرور

**Public Key:**
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAID/vcvbKW5aWecogrxdZyQpn3dTpvzBmAkHNMyaZC8EB github-actions-sedi-backend
```

**دستور برای اضافه کردن به سرور:**
```powershell
ssh root@91.107.168.130 'mkdir -p /root/.ssh && chmod 700 /root/.ssh && echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAID/vcvbKW5aWecogrxdZyQpn3dTpvzBmAkHNMyaZC8EB github-actions-sedi-backend" >> /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys'
```

**یا به صورت دستی:**
1. به سرور SSH کنید: `ssh root@91.107.168.130`
2. دستورات زیر را اجرا کنید:
```bash
mkdir -p /root/.ssh
chmod 700 /root/.ssh
nano /root/.ssh/authorized_keys
# Public Key بالا را paste کنید
# Ctrl+X, Y, Enter برای ذخیره
chmod 600 /root/.ssh/authorized_keys
```

### مرحله 3: اضافه کردن Private Key به GitHub Secrets

1. به GitHub بروید:
   ```
   https://github.com/javadmeighani-oss/sedi-backend/settings/secrets/actions
   ```

2. اگر `SEDI_DEPLOY_KEY` یا `SSH_PRIVATE_KEY` وجود دارد:
   - روی **Edit** کلیک کنید
   - محتوای فایل `backend/.github_actions_key` را کپی کنید
   - جایگزین کنید و **Update** کنید

3. اگر وجود ندارد:
   - روی **New repository secret** کلیک کنید
   - **Name:** `SEDI_DEPLOY_KEY`
   - **Value:** محتوای کامل فایل `backend/.github_actions_key` (شامل `-----BEGIN...` و `-----END...`)

**برای گرفتن محتوای Private Key:**
```powershell
cd "D:\Rimiya Design Studio\Sedi\software\Demo\backend"
Get-Content .github_actions_key -Raw
```

### مرحله 4: تست SSH Connection

**از local machine:**
```powershell
cd "D:\Rimiya Design Studio\Sedi\software\Demo\backend"
ssh -i .github_actions_key root@91.107.168.130 "echo 'SSH works! ✅'"
```

اگر این دستور کار کرد، GitHub Actions هم باید کار کند!

### مرحله 5: تست GitHub Actions

1. به GitHub Actions بروید:
   ```
   https://github.com/javadmeighani-oss/sedi-backend/actions
   ```

2. روی workflow failed کلیک کنید

3. روی **"Re-run jobs"** کلیک کنید

4. یا یک commit جدید push کنید تا workflow دوباره اجرا شود

---

## ✅ Checklist

- [ ] Public Key به `/root/.ssh/authorized_keys` روی سرور اضافه شد
- [ ] Private Key به GitHub Secrets (`SEDI_DEPLOY_KEY` یا `SSH_PRIVATE_KEY`) اضافه شد
- [ ] تست SSH از local machine موفق بود
- [ ] GitHub Actions workflow دوباره اجرا شد

---

**تاریخ:** 2025-12-26  
**Status:** در انتظار تنظیم SSH


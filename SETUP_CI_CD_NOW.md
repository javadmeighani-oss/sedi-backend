# 🚀 Setup CI/CD - دستورات سریع

## ⚡ Quick Setup (کپی و اجرا)

### 1️⃣ تولید SSH Key

```powershell
cd "D:\Rimiya Design Studio\Sedi\software\Demo\backend"
ssh-keygen -t ed25519 -C "github-actions-sedi" -f .github_actions_key -N ""
Get-Content .github_actions_key.pub
```

**📋 خروجی را کپی کنید** (شروع با `ssh-ed25519`)

---

### 2️⃣ اضافه کردن به سرور

```powershell
ssh root@91.107.168.130
```

**در سرور:**
```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "PASTE_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
exit
```

**⚠️ `PASTE_PUBLIC_KEY_HERE` را با public key از Step 1 جایگزین کنید**

**تست:**
```powershell
ssh -i .github_actions_key root@91.107.168.130 "echo '✅ SSH works!'"
```

---

### 3️⃣ اضافه کردن به GitHub Secrets

1. بروید به: `https://github.com/javadmeighani-oss/sedi-backend/settings/secrets/actions`
2. کلیک کنید: **"New repository secret"**
3. **Name:** `SSH_PRIVATE_KEY`
4. **Value:** 
   ```powershell
   Get-Content .github_actions_key
   ```
   **تمام محتوا را کپی کنید**

---

### 4️⃣ تست

1. بروید به: `https://github.com/javadmeighani-oss/sedi-backend/actions`
2. کلیک کنید: **"Deploy Backend to Cloud Server"** → **"Run workflow"**
3. ✅ Done!

---

## 📚 راهنمای کامل

برای جزئیات بیشتر: `docs/SETUP_CI_CD_STEP_BY_STEP.md`


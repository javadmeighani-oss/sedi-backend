# Setup SSH Key for GitHub Actions - Windows Guide

## مشکل: ssh-keygen در Windows

در Windows، syntax کمی متفاوت است. این راهنما برای Windows PowerShell است.

---

## روش 1: استفاده از اسکریپت PowerShell (پیشنهادی)

### اجرای اسکریپت:

```powershell
cd "D:\Rimiya Design Studio\Sedi\software\Demo\backend"
.\deployment\GENERATE_SSH_KEY.ps1
```

یا اگر execution policy مشکل دارد:

```powershell
powershell -ExecutionPolicy Bypass -File .\deployment\GENERATE_SSH_KEY.ps1
```

---

## روش 2: دستورات دستی (اگر اسکریپت کار نکرد)

### Step 1: تولید SSH Key

```powershell
cd "D:\Rimiya Design Studio\Sedi\software\Demo\backend"

# در Windows، از این syntax استفاده کنید:
ssh-keygen -t ed25519 -C "github-actions-sedi-backend" -f ".github_actions_key"
```

**⚠️ توجه:** وقتی passphrase خواست، Enter بزنید (خالی بگذارید)

### Step 2: نمایش Public Key

```powershell
Get-Content .github_actions_key.pub
```

**📋 این خروجی را کپی کنید** (برای Step بعدی)

### Step 3: نمایش Private Key (برای GitHub Secrets)

```powershell
Get-Content .github_actions_key
```

**📋 این خروجی را کپی کنید** (برای GitHub Secrets)

---

## روش 3: استفاده از Git Bash (اگر نصب دارید)

اگر Git Bash نصب دارید، می‌توانید از آن استفاده کنید:

```bash
cd "/d/Rimiya Design Studio/Sedi/software/Demo/backend"
ssh-keygen -t ed25519 -C "github-actions-sedi-backend" -f .github_actions_key -N ""
cat .github_actions_key.pub
```

---

## اگر ssh-keygen کار نمی‌کند

### بررسی نصب OpenSSH:

```powershell
# بررسی که OpenSSH نصب است
Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH*'
```

### نصب OpenSSH (اگر نصب نیست):

```powershell
# Run as Administrator
Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
```

---

## بعد از تولید Key

### 1. Public Key را به سرور اضافه کنید (Step 2 از راهنمای اصلی)

### 2. Private Key را به GitHub Secrets اضافه کنید (Step 3 از راهنمای اصلی)

---

## تست

بعد از اضافه کردن public key به سرور:

```powershell
ssh -i .github_actions_key root@91.107.168.130 "echo '✅ SSH works!'"
```

اگر پیام "✅ SSH works!" را دیدید، setup موفق بوده است!


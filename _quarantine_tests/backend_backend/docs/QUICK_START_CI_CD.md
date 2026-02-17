# Quick Start: GitHub Actions CI/CD Setup

## 🚀 Fast Setup (5 Steps)

### STEP 1: Generate SSH Key

**PowerShell:**
```powershell
cd "D:\Rimiya Design Studio\Sedi\software\Demo\backend"
ssh-keygen -t ed25519 -C "github-actions-sedi" -f .github_actions_key -N ""
Get-Content .github_actions_key.pub
```

**Copy the output** (public key)

---

### STEP 2: Add Public Key to Server

**PowerShell:**
```powershell
# Connect to server
ssh root@91.107.168.130

# In server, run:
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "PASTE_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
exit
```

**Replace `PASTE_PUBLIC_KEY_HERE` with the public key from Step 1**

---

### STEP 3: Add Private Key to GitHub Secrets

1. Go to: `https://github.com/javadmeighani-oss/sedi-backend/settings/secrets/actions`
2. Click **"New repository secret"**
3. **Name:** `SSH_PRIVATE_KEY`
4. **Value:** 
   ```powershell
   Get-Content .github_actions_key
   ```
   Copy entire content (including `-----BEGIN...` and `-----END...`)

---

### STEP 4: Commit Workflow File

```powershell
git add .github/workflows/deploy.yml .gitignore
git commit -m "ci: Add GitHub Actions automated deployment"
git push
```

---

### STEP 5: Test!

1. Go to: `https://github.com/javadmeighani-oss/sedi-backend/actions`
2. Watch the workflow run automatically
3. ✅ Done!

---

## ✅ That's It!

Now every push to `main` will automatically deploy to your server!

---

## 📚 Full Guide

For detailed instructions, see: `docs/GITHUB_ACTIONS_COMPLETE_GUIDE.md`


# Complete GitHub Actions CI/CD Setup Guide

## 🎯 Goal

Automatically deploy Sedi Backend to cloud server whenever code is pushed to `main` branch.

---

## 📋 Step-by-Step Setup

### STEP 1: Generate SSH Key for GitHub Actions

**On your local machine (PowerShell):**

```powershell
# Navigate to backend directory
cd "D:\Rimiya Design Studio\Sedi\software\Demo\backend"

# Generate SSH key (dedicated for GitHub Actions)
ssh-keygen -t ed25519 -C "github-actions-sedi-backend" -f .github_actions_key -N ""

# Display public key (SAVE THIS)
Get-Content .github_actions_key.pub
```

**Output example:**
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... github-actions-sedi-backend
```

**⚠️ IMPORTANT:** Copy the entire public key output.

---

### STEP 2: Add Public Key to Server

**Option A: Using ssh-copy-id (if available on Windows)**

```powershell
ssh-copy-id -i .github_actions_key.pub root@91.107.168.130
```

**Option B: Manual (Recommended)**

```powershell
# 1. Connect to server
ssh root@91.107.168.130

# 2. In server terminal, run:
mkdir -p ~/.ssh
chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys
```

**3. In nano editor:**
- Press `Ctrl+End` to go to end of file
- Press `Enter` to add new line
- Paste the public key (from Step 1)
- Press `Ctrl+X`, then `Y`, then `Enter` to save

**4. Set permissions:**
```bash
chmod 600 ~/.ssh/authorized_keys
exit
```

**5. Test connection (from local machine):**
```powershell
ssh -i .github_actions_key root@91.107.168.130 "echo 'SSH key works! ✅'"
```

If you see "SSH key works! ✅", proceed to Step 3.

---

### STEP 3: Add Private Key to GitHub Secrets

**1. Go to GitHub repository:**
```
https://github.com/javadmeighani-oss/sedi-backend/settings/secrets/actions
```

**2. Click "New repository secret"**

**3. Add Secret 1:**
- **Name:** `SSH_PRIVATE_KEY`
- **Value:** Get the private key content:
  ```powershell
  Get-Content .github_actions_key
  ```
  Copy the ENTIRE content (including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`)

**4. (Optional) Add Secret 2:**
- **Name:** `SERVER_HOST`
- **Value:** `91.107.168.130`

**5. (Optional) Add Secret 3:**
- **Name:** `SERVER_USER`
- **Value:** `root`

**⚠️ IMPORTANT:** 
- Never commit `.github_actions_key` file to Git
- Add it to `.gitignore` if not already there

---

### STEP 4: Add SSH Key to .gitignore

```powershell
# Add to .gitignore
echo ".github_actions_key" >> .gitignore
echo ".github_actions_key.pub" >> .gitignore
```

---

### STEP 5: Commit and Push Workflow File

The workflow file (`.github/workflows/deploy.yml`) is already created. Now commit it:

```powershell
git add .github/workflows/deploy.yml
git add .gitignore
git commit -m "ci: Add GitHub Actions for automated deployment"
git push
```

---

### STEP 6: Test Deployment

**1. Go to GitHub:**
```
https://github.com/javadmeighani-oss/sedi-backend/actions
```

**2. You should see the workflow running automatically**

**3. Or trigger manually:**
- Go to Actions tab
- Click "Deploy Backend to Cloud Server"
- Click "Run workflow"
- Select branch: `main`
- Click "Run workflow"

**4. Watch the workflow:**
- Click on the running workflow
- Watch each step execute
- Check for any errors

**5. Verify on server:**
```powershell
ssh root@91.107.168.130 "systemctl status sedi-backend --no-pager | head -10"
```

---

## 🔍 How It Works

### Workflow Triggers:
1. **Automatic:** On push to `main` branch (only for specific paths)
2. **Manual:** Can be triggered manually from GitHub Actions tab

### Workflow Steps:
1. ✅ Checkout code from repository
2. ✅ Setup SSH with private key from secrets
3. ✅ Connect to server
4. ✅ Pull latest code (`git pull`)
5. ✅ Install/update dependencies (if needed)
6. ✅ Restart service (`systemctl restart sedi-backend`)
7. ✅ Verify service status
8. ✅ Test API endpoint
9. ✅ Report deployment status

---

## 📊 Monitoring

### View Deployment History:
```
https://github.com/javadmeighani-oss/sedi-backend/actions
```

### View Deployment Logs:
- Click on any workflow run
- Click on "Deploy to Production Server" job
- View detailed logs for each step

### Server Logs:
```bash
# On server
journalctl -u sedi-backend -f
```

---

## 🔧 Configuration

### Modify Deployment Paths:

Edit `.github/workflows/deploy.yml`:

```yaml
on:
  push:
    branches:
      - main
    paths:
      - 'app/**'           # Deploy on app changes
      - 'requirements.txt'  # Deploy on dependency changes
      - 'deployment/**'    # Deploy on deployment config changes
```

### Modify Deployment Steps:

Edit the `Deploy to server` step in `.github/workflows/deploy.yml` to add custom commands.

---

## 🛠️ Troubleshooting

### Issue: SSH Connection Fails

**Check:**
1. SSH key is correctly added to server `~/.ssh/authorized_keys`
2. Permissions: `chmod 600 ~/.ssh/authorized_keys`
3. Test manually: `ssh -i .github_actions_key root@91.107.168.130`

**Solution:**
- Re-add public key to server
- Verify GitHub Secret `SSH_PRIVATE_KEY` is correct

---

### Issue: Service Restart Fails

**Check:**
```bash
# On server
systemctl status sedi-backend
journalctl -u sedi-backend -n 50
```

**Solution:**
- Check service file: `/etc/systemd/system/sedi-backend.service`
- Verify paths are correct
- Check permissions

---

### Issue: Git Pull Fails

**Check:**
```bash
# On server
cd /var/www/sedi/backend
git status
```

**Solution:**
- May have uncommitted changes
- May need to reset: `git reset --hard origin/main`

---

### Issue: Dependencies Install Fails

**Check:**
- Virtual environment exists: `/var/www/sedi/backend/.venv`
- Python version compatibility
- Network connectivity on server

**Solution:**
- Create venv manually if missing
- Check `requirements.txt` for issues

---

## 🔒 Security Best Practices

1. ✅ **Dedicated SSH Key:** Use separate key for CI/CD
2. ✅ **GitHub Secrets:** Never commit private keys
3. ✅ **Limited Permissions:** SSH key only for deployment
4. ✅ **Monitor Logs:** Regularly check deployment logs
5. ✅ **Rollback Plan:** Keep previous versions accessible

---

## 📝 Workflow File Location

```
.github/workflows/deploy.yml
```

This file is already created and ready to use!

---

## ✅ Verification Checklist

- [ ] SSH key generated
- [ ] Public key added to server
- [ ] Private key added to GitHub Secrets
- [ ] `.github_actions_key` added to `.gitignore`
- [ ] Workflow file committed and pushed
- [ ] First deployment tested
- [ ] Service restarts successfully
- [ ] API endpoint responds

---

## 🎉 Success!

Once setup is complete:
- Every push to `main` will automatically deploy
- No manual SSH needed
- Deployment history in GitHub Actions
- Automatic verification

---

**Next:** Follow Step 1-6 above to complete setup!


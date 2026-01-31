# GitHub Actions CI/CD Setup Guide

## Overview

This guide will help you set up automated deployment for Sedi Backend using GitHub Actions.

**What it does:**
- Automatically deploys backend on every push to `main` branch
- Runs tests (optional)
- Pulls latest code on server
- Restarts service
- Verifies deployment

---

## Prerequisites

1. GitHub repository (already have)
2. Server access (already have)
3. SSH access to server (already have)

---

## Step 1: Generate SSH Key for GitHub Actions

### On Your Local Machine (PowerShell):

```powershell
# Navigate to backend directory
cd "D:\Rimiya Design Studio\Sedi\software\Demo\backend"

# Generate SSH key for GitHub Actions (dedicated key)
ssh-keygen -t ed25519 -C "github-actions-sedi-backend" -f .github_actions_key -N ""

# Display public key (you'll need this)
Get-Content .github_actions_key.pub
```

**Output:** Copy the public key (starts with `ssh-ed25519`)

---

## Step 2: Add SSH Key to Server

### Option A: Using ssh-copy-id (if available)

```powershell
# Copy public key to server
ssh-copy-id -i .github_actions_key.pub root@91.107.168.130
```

### Option B: Manual (Recommended)

```powershell
# 1. Connect to server
ssh root@91.107.168.130

# 2. In server, create .ssh directory if not exists
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# 3. Add public key to authorized_keys
nano ~/.ssh/authorized_keys
# Paste the public key content (from Step 1)
# Save and exit (Ctrl+X, Y, Enter)

# 4. Set correct permissions
chmod 600 ~/.ssh/authorized_keys

# 5. Test connection (from local machine)
ssh -i .github_actions_key root@91.107.168.130 "echo 'SSH key works!'"
```

---

## Step 3: Add SSH Private Key to GitHub Secrets

### In GitHub Repository:

1. Go to: `https://github.com/javadmeighani-oss/sedi-backend/settings/secrets/actions`
2. Click **"New repository secret"**
3. Add these secrets:

**Secret 1:**
- **Name:** `SSH_PRIVATE_KEY`
- **Value:** Content of `.github_actions_key` file (private key)
  ```powershell
  Get-Content .github_actions_key
  ```
  Copy the entire content (including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`)

**Secret 2 (Optional):**
- **Name:** `SERVER_HOST`
- **Value:** `91.107.168.130`

**Secret 3 (Optional):**
- **Name:** `SERVER_USER`
- **Value:** `root`

---

## Step 4: Create GitHub Actions Workflow

The workflow file will be created in the next step. It will:
1. Checkout code
2. Setup SSH
3. Connect to server
4. Pull latest changes
5. Restart service
6. Verify deployment

---

## Step 5: Test Deployment

1. Make a small change in code
2. Commit and push:
   ```powershell
   git add .
   git commit -m "test: Test GitHub Actions deployment"
   git push
   ```
3. Go to GitHub → Actions tab
4. Watch the workflow run
5. Verify deployment on server

---

## Troubleshooting

### SSH Connection Fails
- Check SSH key is correctly added to server
- Verify permissions on `~/.ssh/authorized_keys` (should be 600)
- Test SSH connection manually

### Service Restart Fails
- Check service name is correct
- Verify user has permissions to restart service
- Check logs: `journalctl -u sedi-backend -n 50`

### GitHub Actions Fails
- Check GitHub Secrets are set correctly
- Verify SSH private key format (should include headers)
- Check workflow logs in GitHub Actions tab

---

## Security Best Practices

1. ✅ Use dedicated SSH key for CI/CD (not your personal key)
2. ✅ Never commit private keys to repository
3. ✅ Use GitHub Secrets for all sensitive data
4. ✅ Limit SSH key permissions (if possible)
5. ✅ Monitor deployment logs regularly

---

## Next: Create Workflow File

See next step for creating the actual workflow file.


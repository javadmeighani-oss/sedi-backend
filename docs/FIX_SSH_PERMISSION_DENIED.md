# Fix "Permission denied (publickey, password)" Error

## 🔍 Problem

**Error:** `Permission denied (publickey, password)`  
**Exit code:** 255

This means the SSH key authentication is failing. The private key in GitHub Secrets doesn't match the public key on the server.

---

## ✅ Solution Steps

### Step 1: Get Public Key from Local Machine

**On Windows PowerShell:**

```powershell
cd "D:\Rimiya Design Studio\Sedi\software\Demo\backend"

# If you have the key file
Get-Content .github_actions_key.pub

# Or if you need to generate it
ssh-keygen -t ed25519 -C "github-actions-sedi-backend" -f ".github_actions_key" -N '""'
Get-Content .github_actions_key.pub
```

**📋 Copy the entire output** (starts with `ssh-ed25519`)

---

### Step 2: Add Public Key to Server

**Connect to server:**

```powershell
ssh root@91.107.168.130
```

**On server, run diagnostic first:**

```bash
# Upload and run diagnostic script
chmod +x /path/to/DIAGNOSE_SSH_AUTH.sh
/path/to/DIAGNOSE_SSH_AUTH.sh
```

**Or manually:**

```bash
# Ensure .ssh directory exists
mkdir -p /root/.ssh
chmod 700 /root/.ssh

# Add public key to authorized_keys
nano /root/.ssh/authorized_keys
```

**In nano:**
- Go to end of file (Ctrl+End)
- Press Enter (new line)
- Paste the public key from Step 1
- Save (Ctrl+X, Y, Enter)

**Set correct permissions:**

```bash
chmod 600 /root/.ssh/authorized_keys
```

**Verify:**

```bash
cat /root/.ssh/authorized_keys
# Should show your public key
```

---

### Step 3: Verify SSH Config on Server

**On server:**

```bash
# Check SSH config
grep -E "^(PermitRootLogin|PubkeyAuthentication)" /etc/ssh/sshd_config

# Should show:
# PermitRootLogin yes
# PubkeyAuthentication yes
```

**If not, fix it:**

```bash
# Backup
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup

# Edit
nano /etc/ssh/sshd_config
```

**Ensure these lines exist (uncommented):**
```
PermitRootLogin yes
PubkeyAuthentication yes
PasswordAuthentication no
```

**Restart SSH:**

```bash
systemctl restart sshd
```

---

### Step 4: Verify Private Key in GitHub Secrets

**In GitHub:**
1. Go to: `https://github.com/javadmeighani-oss/sedi-backend/settings/secrets/actions`
2. Check `SSH_PRIVATE_KEY` or `SEDI_DEPLOY_KEY`
3. Verify it matches the private key from `.github_actions_key` file

**To get private key (on local machine):**

```powershell
Get-Content .github_actions_key -Raw
```

**Important:**
- Must include `-----BEGIN OPENSSH PRIVATE KEY-----`
- Must include `-----END OPENSSH PRIVATE KEY-----`
- No passphrase
- No extra spaces

---

### Step 5: Test SSH Connection Locally

**On Windows PowerShell:**

```powershell
# Test SSH connection
ssh -i .github_actions_key root@91.107.168.130 "echo 'SSH works! ✅'"
```

**Expected:** Should see "SSH works! ✅" without password prompt

**If it fails:**
- Check public key is in server's `authorized_keys`
- Check permissions (700 for .ssh, 600 for authorized_keys)
- Check SSH config allows root login

---

### Step 6: Test GitHub Actions Again

1. Go to: `https://github.com/javadmeighani-oss/sedi-backend/actions`
2. Click "Deploy Sedi Backend to Cloud Server"
3. Click "Run workflow"
4. Watch "Test SSH connection" step

**Expected:** Should pass without permission denied error

---

## 🔧 Quick Fix Script (On Server)

**Create and run on server:**

```bash
cat > /tmp/fix_ssh_auth.sh << 'EOF'
#!/bin/bash
# Quick fix for SSH authentication

# 1. Ensure .ssh directory
mkdir -p /root/.ssh
chmod 700 /root/.ssh

# 2. Fix SSH config
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
if ! grep -q "^PermitRootLogin" /etc/ssh/sshd_config; then
    echo "PermitRootLogin yes" >> /etc/ssh/sshd_config
fi
if ! grep -q "^PubkeyAuthentication" /etc/ssh/sshd_config; then
    echo "PubkeyAuthentication yes" >> /etc/ssh/sshd_config
fi

# 3. Restart SSH
systemctl restart sshd

# 4. Show status
echo "✅ SSH configuration updated"
grep -E "^(PermitRootLogin|PubkeyAuthentication)" /etc/ssh/sshd_config
echo ""
echo "⚠️  Don't forget to add your public key to /root/.ssh/authorized_keys"
EOF

chmod +x /tmp/fix_ssh_auth.sh
/tmp/fix_ssh_auth.sh
```

---

## 📋 Checklist

- [ ] Public key generated on local machine
- [ ] Public key added to `/root/.ssh/authorized_keys` on server
- [ ] Permissions set: `/root/.ssh` → 700, `authorized_keys` → 600
- [ ] SSH config: `PermitRootLogin yes`
- [ ] SSH config: `PubkeyAuthentication yes`
- [ ] SSH service restarted
- [ ] Private key in GitHub Secrets matches local private key
- [ ] Test SSH from local machine works
- [ ] GitHub Actions workflow tested

---

## 🎯 Root Cause

**Most likely:** Public key is not in server's `authorized_keys` file, or doesn't match the private key in GitHub Secrets.

**Fix:** Add the correct public key to `/root/.ssh/authorized_keys` on the server.

---

**Next:** Follow Steps 1-6 above to fix the issue!


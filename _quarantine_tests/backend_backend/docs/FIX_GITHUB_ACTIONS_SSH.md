# Fix GitHub Actions SSH Deployment - Complete Guide

## 🔍 Problem Diagnosis

**Error:** `Permission denied (publickey,password)`  
**Exit code:** 255

This means SSH authentication is failing. Let's fix it step by step.

---

## 📋 Diagnostic Checklist

### A) SERVER-SIDE CHECKS

Run these commands on the server:

```bash
# 1. Check SSH config
grep -E "^(PermitRootLogin|PubkeyAuthentication|PasswordAuthentication)" /etc/ssh/sshd_config

# 2. Check .ssh directory
ls -la /root/.ssh/

# 3. Check authorized_keys
cat /root/.ssh/authorized_keys

# 4. Check permissions
stat -c "%a %n" /root/.ssh
stat -c "%a %n" /root/.ssh/authorized_keys
```

**Expected:**
- `/root/.ssh` → 700
- `/root/.ssh/authorized_keys` → 600
- `PermitRootLogin yes`
- `PubkeyAuthentication yes`

---

## 🔧 FIXES

### FIX 1: Update SSH Configuration

**On server, run:**

```bash
# Backup config
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup

# Edit config
nano /etc/ssh/sshd_config
```

**Ensure these lines exist:**
```
PermitRootLogin yes
PubkeyAuthentication yes
PasswordAuthentication no
```

**If changed, restart SSH:**
```bash
systemctl restart sshd
```

**Or use the fix script:**
```bash
chmod +x /path/to/FIX_SSH_CONFIG.sh
/path/to/FIX_SSH_CONFIG.sh
```

---

### FIX 2: Setup SSH Key on Server

**Step 1: Get public key from local machine**

```powershell
# On Windows (in backend directory)
Get-Content .github_actions_key.pub
```

**Step 2: Add to server**

```bash
# On server
mkdir -p /root/.ssh
chmod 700 /root/.ssh
nano /root/.ssh/authorized_keys
# Paste public key, save (Ctrl+X, Y, Enter)
chmod 600 /root/.ssh/authorized_keys
```

**Or use the script:**
```bash
chmod +x /path/to/ADD_SSH_KEY_TO_SERVER.sh
./ADD_SSH_KEY_TO_SERVER.sh "ssh-ed25519 AAAA... (paste your public key)"
```

---

### FIX 3: Verify GitHub Secret Format

**In GitHub Secrets (`SSH_PRIVATE_KEY` or `SEDI_DEPLOY_KEY`):**

1. Must contain ONLY the private key
2. Must include headers:
   ```
   -----BEGIN OPENSSH PRIVATE KEY-----
   ...
   -----END OPENSSH PRIVATE KEY-----
   ```
3. No extra spaces
4. No Windows line endings (CRLF) - should be LF only

**To get correct format:**
```powershell
# On Windows
Get-Content .github_actions_key | Set-Content -Path temp_key.txt -Encoding UTF8
Get-Content temp_key.txt
# Copy this output
```

---

### FIX 4: Update GitHub Actions Workflow

The workflow file (`.github/workflows/deploy.yml`) has been updated with:
- Better SSH options (`BatchMode=yes`, `ConnectTimeout=10`)
- Support for both `SSH_PRIVATE_KEY` and `SEDI_DEPLOY_KEY` secrets
- Proper known_hosts handling

**No action needed** - already updated!

---

## ✅ Verification Steps

### 1. Test SSH from Local Machine

```powershell
# On Windows
ssh -i .github_actions_key root@91.107.168.130 "echo 'SSH works! ✅'"
```

**Expected:** Should see "SSH works! ✅" without password prompt

---

### 2. Test GitHub Actions

1. Go to: `https://github.com/javadmeighani-oss/sedi-backend/actions`
2. Click "Deploy Backend to Cloud Server"
3. Click "Run workflow"
4. Watch the logs

**Expected:** Should pass "Test SSH connection" step

---

## 🛠️ Quick Fix Script (All-in-One)

**On server, create and run:**

```bash
cat > /tmp/fix_ssh.sh << 'EOF'
#!/bin/bash
# Fix SSH for GitHub Actions

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
EOF

chmod +x /tmp/fix_ssh.sh
/tmp/fix_ssh.sh
```

---

## 📝 Final Checklist

- [ ] SSH config allows root login (`PermitRootLogin yes`)
- [ ] SSH config allows public key auth (`PubkeyAuthentication yes`)
- [ ] `/root/.ssh` exists with 700 permissions
- [ ] `/root/.ssh/authorized_keys` exists with 600 permissions
- [ ] Public key is in `authorized_keys` (exact match)
- [ ] GitHub Secret contains private key (correct format)
- [ ] SSH service restarted after config changes
- [ ] Test SSH from local machine works
- [ ] GitHub Actions workflow updated

---

## 🎯 Root Cause (Most Likely)

1. **PermitRootLogin disabled** → Enable it
2. **Public key not in authorized_keys** → Add it
3. **Wrong permissions** → Fix to 700/600
4. **Private key format wrong in GitHub Secrets** → Fix format

---

## 📊 Files Changed

1. `.github/workflows/deploy.yml` - Updated SSH options
2. `deployment/FIX_SSH_CONFIG.sh` - SSH config fix script
3. `deployment/ADD_SSH_KEY_TO_SERVER.sh` - Add key script
4. `deployment/DIAGNOSE_SSH.sh` - Diagnostic script

---

## ✅ Expected Result

After fixes:
- ✅ GitHub Actions can SSH without password
- ✅ Deployment completes successfully
- ✅ Service restarts automatically
- ✅ API endpoint verified

---

**Next:** Follow the fixes above, then test GitHub Actions deployment!


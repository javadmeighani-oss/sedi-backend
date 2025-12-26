# Verify GitHub Secret - SEDI_DEPLOY_KEY

## ✅ Current Status

**Secret Name:** `SEDI_DEPLOY_KEY`  
**Last Updated:** 25 minutes ago  
**Status:** ✅ Exists in GitHub Secrets

---

## 🔍 Verification Steps

### Step 1: Get Private Key from Local Machine

**On Windows PowerShell:**

```powershell
cd "D:\Rimiya Design Studio\Sedi\software\Demo\backend"

# If you have the key file
Get-Content .github_actions_key -Raw

# Or verify format
.\deployment\VERIFY_SSH_KEY_FORMAT.ps1
```

**📋 Copy the entire output** (including `-----BEGIN...` and `-----END...`)

---

### Step 2: Compare with GitHub Secret

**In GitHub:**
1. Go to: `https://github.com/javadmeighani-oss/sedi-backend/settings/secrets/actions`
2. Click the **edit (pencil) icon** next to `SEDI_DEPLOY_KEY`
3. **Don't change anything** - just verify the format

**The secret should:**
- ✅ Start with `-----BEGIN OPENSSH PRIVATE KEY-----`
- ✅ End with `-----END OPENSSH PRIVATE KEY-----`
- ✅ Match the private key from Step 1
- ✅ Have no passphrase (no `Proc-Type: 4,ENCRYPTED`)

---

### Step 3: Get Matching Public Key

**The public key that matches this private key:**

```powershell
Get-Content .github_actions_key.pub
```

**This public key MUST be in the server's `/root/.ssh/authorized_keys`**

---

### Step 4: Verify Public Key on Server

**Connect to server:**

```powershell
ssh root@91.107.168.130
```

**On server:**

```bash
# Check if public key exists
cat /root/.ssh/authorized_keys

# Should contain a line starting with: ssh-ed25519
# That matches the public key from Step 3
```

**If not found, add it:**

```bash
# Get public key from local machine first, then:
nano /root/.ssh/authorized_keys
# Paste the public key, save (Ctrl+X, Y, Enter)
chmod 600 /root/.ssh/authorized_keys
```

---

## 🔧 Quick Fix Checklist

- [ ] Private key in GitHub Secret `SEDI_DEPLOY_KEY` is correct format
- [ ] Public key (from `.github_actions_key.pub`) is in server's `authorized_keys`
- [ ] Server SSH config allows root login (`PermitRootLogin yes`)
- [ ] Server SSH config allows public key auth (`PubkeyAuthentication yes`)
- [ ] Permissions correct: `/root/.ssh` → 700, `authorized_keys` → 600
- [ ] Test SSH from local machine works

---

## 🧪 Test SSH Connection

**On local machine:**

```powershell
ssh -i .github_actions_key root@91.107.168.130 "echo 'SSH works! ✅'"
```

**If this works, GitHub Actions should also work!**

---

## 📝 Next Steps

1. **Verify secret format** (Step 1-2)
2. **Add public key to server** (Step 3-4)
3. **Test locally** (Test section)
4. **Test GitHub Actions** workflow

---

**The secret exists - now we need to ensure the matching public key is on the server!**


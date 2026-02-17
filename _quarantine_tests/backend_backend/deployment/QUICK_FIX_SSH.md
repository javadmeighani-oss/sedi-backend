# Quick Fix SSH Authentication - Step by Step

## 🎯 Goal

Fix "Permission denied" error in GitHub Actions by ensuring:
1. Private key in GitHub Secret matches local private key
2. Public key is on server's `authorized_keys`

---

## ⚡ Quick Steps

### 1. Get Public Key (Local Machine)

```powershell
cd "D:\Rimiya Design Studio\Sedi\software\Demo\backend"
Get-Content .github_actions_key.pub
```

**Copy this output** (starts with `ssh-ed25519`)

---

### 2. Add to Server

```powershell
ssh root@91.107.168.130
```

**On server:**

```bash
mkdir -p /root/.ssh
chmod 700 /root/.ssh
nano /root/.ssh/authorized_keys
```

**Paste the public key, save (Ctrl+X, Y, Enter)**

```bash
chmod 600 /root/.ssh/authorized_keys
cat /root/.ssh/authorized_keys
```

**Verify you see your public key**

---

### 3. Test Locally

```powershell
# Exit server first
exit

# Test from local machine
ssh -i .github_actions_key root@91.107.168.130 "echo '✅ SSH works!'"
```

**If this works → GitHub Actions will work!**

---

### 4. Test GitHub Actions

1. Go to: `https://github.com/javadmeighani-oss/sedi-backend/actions`
2. "Deploy Sedi Backend to Cloud Server" → "Run workflow"
3. ✅ Should work now!

---

## 🔍 If Still Fails

**Check SSH config on server:**

```bash
ssh root@91.107.168.130
grep -E "^(PermitRootLogin|PubkeyAuthentication)" /etc/ssh/sshd_config
```

**Should show:**
```
PermitRootLogin yes
PubkeyAuthentication yes
```

**If not, fix:**

```bash
nano /etc/ssh/sshd_config
# Add/update the lines above
systemctl restart sshd
```

---

**That's it! Follow steps 1-4 above.**


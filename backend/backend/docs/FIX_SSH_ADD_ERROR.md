# Fix "ssh-add" Error in GitHub Actions

## 🔍 Problem

**Error:** `Error: Command failed: ssh-add`  
**Symptom:** `Enter passphrase for (stdin):` appears twice

This means the SSH private key in GitHub Secrets either:
1. Has a passphrase (but we generated it without one)
2. Has wrong format (extra spaces, wrong line endings)
3. Is corrupted

---

## ✅ Solution

### Step 1: Verify Private Key Format

The private key in GitHub Secrets must be:
- **No passphrase** (we used `-N ""` when generating)
- **Correct format** with headers:
  ```
  -----BEGIN OPENSSH PRIVATE KEY-----
  ...
  -----END OPENSSH PRIVATE KEY-----
  ```
- **LF line endings** (not CRLF)
- **No extra spaces** before/after

---

### Step 2: Regenerate SSH Key (If Needed)

**On Windows PowerShell:**

```powershell
cd "D:\Rimiya Design Studio\Sedi\software\Demo\backend"

# Remove old key if exists
Remove-Item .github_actions_key -ErrorAction SilentlyContinue
Remove-Item .github_actions_key.pub -ErrorAction SilentlyContinue

# Generate new key WITHOUT passphrase
ssh-keygen -t ed25519 -C "github-actions-sedi-backend" -f ".github_actions_key" -N '""'

# Verify no passphrase
Get-Content .github_actions_key | Select-String "BEGIN"
```

**Expected output:** Should see `-----BEGIN OPENSSH PRIVATE KEY-----`

---

### Step 3: Get Private Key in Correct Format

**Important:** Copy the ENTIRE key including headers:

```powershell
# Get private key (entire content)
Get-Content .github_actions_key -Raw
```

**Or save to file for easier copying:**

```powershell
Get-Content .github_actions_key -Raw | Out-File -FilePath private_key.txt -Encoding UTF8 -NoNewline
notepad private_key.txt
```

**Copy everything from Notepad** (including `-----BEGIN...` and `-----END...`)

---

### Step 4: Update GitHub Secret

1. Go to: `https://github.com/javadmeighani-oss/sedi-backend/settings/secrets/actions`
2. Find `SSH_PRIVATE_KEY` or `SEDI_DEPLOY_KEY`
3. Click "Update"
4. **Delete old value completely**
5. **Paste new value** (from Step 3)
6. **Make sure:**
   - No extra spaces at start/end
   - Includes `-----BEGIN...` and `-----END...`
   - No passphrase
7. Click "Update secret"

---

### Step 5: Verify Key Format

**Check in GitHub Secret:**
- First line should be: `-----BEGIN OPENSSH PRIVATE KEY-----`
- Last line should be: `-----END OPENSSH PRIVATE KEY-----`
- No `Proc-Type: 4,ENCRYPTED` (this means it has passphrase)

---

### Step 6: Test Again

1. Go to Actions: `https://github.com/javadmeighani-oss/sedi-backend/actions`
2. Click "Deploy Backend to Cloud Server"
3. Click "Run workflow"
4. Watch "Setup SSH" step

**Expected:** Should pass without asking for passphrase

---

## 🔧 Alternative: Use Different SSH Action

If the issue persists, we can use a different approach:

```yaml
- name: Setup SSH
  run: |
    mkdir -p ~/.ssh
    echo "${{ secrets.SSH_PRIVATE_KEY || secrets.SEDI_DEPLOY_KEY }}" > ~/.ssh/deploy_key
    chmod 600 ~/.ssh/deploy_key
    eval "$(ssh-agent -s)"
    ssh-add ~/.ssh/deploy_key
```

But first, try fixing the key format (Steps 1-6 above).

---

## 📋 Checklist

- [ ] SSH key generated WITHOUT passphrase (`-N ""`)
- [ ] Private key includes `-----BEGIN...` and `-----END...`
- [ ] No extra spaces in GitHub Secret
- [ ] LF line endings (not CRLF)
- [ ] GitHub Secret updated with correct format
- [ ] Workflow tested again

---

## 🎯 Root Cause

**Most likely:** Private key in GitHub Secrets has:
- Wrong format (missing headers)
- Extra spaces/characters
- CRLF line endings instead of LF
- Or was generated with passphrase

**Fix:** Regenerate key and update GitHub Secret with correct format.

---

**Next:** Follow Steps 1-6 above to fix the issue!


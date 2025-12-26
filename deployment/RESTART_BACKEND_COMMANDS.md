# Backend Restart Commands - PowerShell

## Option 1: Single Command (Copy & Paste)

```powershell
ssh root@91.107.168.130 "cd /var/www/sedi/backend && git pull && systemctl restart sedi-backend && sleep 3 && systemctl status sedi-backend --no-pager"
```

---

## Option 2: Step by Step Commands

### Step 1: Connect to Server
```powershell
ssh root@91.107.168.130
```

### Step 2: Navigate to Backend Directory
```bash
cd /var/www/sedi/backend
```

### Step 3: Pull Latest Changes
```bash
git pull
```

### Step 4: Restart Service
```bash
systemctl restart sedi-backend
```

### Step 5: Check Status
```bash
systemctl status sedi-backend --no-pager
```

### Step 6: Check Logs
```bash
journalctl -u sedi-backend -n 30 --no-pager
```

### Step 7: Test API
```bash
curl http://localhost:8000/ | python3 -m json.tool
```

---

## Option 3: Complete One-Liner (All Steps)

```powershell
ssh root@91.107.168.130 "cd /var/www/sedi/backend && git pull && systemctl restart sedi-backend && sleep 3 && echo '=== SERVICE STATUS ===' && systemctl status sedi-backend --no-pager | head -15 && echo '' && echo '=== RECENT LOGS ===' && journalctl -u sedi-backend -n 20 --no-pager | tail -20 && echo '' && echo '=== API TEST ===' && curl -s http://localhost:8000/ | python3 -m json.tool"
```

---

## Option 4: Using PowerShell Script

Run the script file:
```powershell
.\deployment\RESTART_BACKEND.ps1
```

Or if you're in the backend directory:
```powershell
.\RESTART_BACKEND.ps1
```

---

## Quick Verification Commands

### Test from Local Machine:
```powershell
# Test root endpoint
curl http://91.107.168.130:8000/

# Test greeting
curl "http://91.107.168.130:8000/interact/greeting?user_id=1&lang=en"
```

---

## Troubleshooting

### If SSH connection fails:
```powershell
# Check SSH connection
ssh -v root@91.107.168.130
```

### If service fails to start:
```powershell
# Check detailed logs
ssh root@91.107.168.130 "journalctl -u sedi-backend -n 50 --no-pager"
```

### If git pull fails:
```powershell
# Check git status
ssh root@91.107.168.130 "cd /var/www/sedi/backend && git status"
```

---

## Recommended: Use Option 3 (Complete One-Liner)

This will:
1. ✅ Pull latest changes
2. ✅ Restart service
3. ✅ Show status
4. ✅ Show recent logs
5. ✅ Test API

Just copy and paste in PowerShell!


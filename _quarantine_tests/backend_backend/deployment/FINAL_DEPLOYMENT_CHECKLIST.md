# Final Deployment Checklist - Server Verification

## Quick Server Commands

### 1. Pull Latest Changes
```bash
cd /var/www/sedi/backend
git pull
```

### 2. Verify Service Status
```bash
systemctl status sedi-backend --no-pager
```

### 3. Check Logs (No Errors)
```bash
journalctl -u sedi-backend -n 50 --no-pager | grep -i "error\|exception"
```

### 4. Test API Endpoints
```bash
# Test root endpoint
curl http://localhost:8000/ | python3 -m json.tool

# Test greeting
curl "http://localhost:8000/interact/greeting?user_id=1&lang=en" | python3 -m json.tool

# Test notifications
curl "http://localhost:8000/notifications?user_id=1" | python3 -m json.tool
```

### 5. Verify Database Connection
```bash
PGPASSWORD='Sedi2025!SecurePass' psql -h localhost -U sedi_user -d sedi_db -c "SELECT COUNT(*) FROM users;"
```

### 6. Check Environment Variables
```bash
# Check DATABASE_URL
grep DATABASE_URL /var/www/sedi/backend/.env

# Check OPENAI_API_KEY (should show first few chars only)
grep OPENAI_API_KEY /var/www/sedi/backend/.env | head -c 30
```

### 7. Restart Service (if needed)
```bash
systemctl restart sedi-backend
sleep 3
systemctl status sedi-backend --no-pager
```

---

## External Access Test

### From Local Machine:
```bash
# Test from external network
curl http://91.107.168.130:8000/ | python3 -m json.tool

# Test API docs
curl http://91.107.168.130:8000/docs
```

---

## Frontend Integration Info

### Base URL:
```
http://91.107.168.130:8000
```

### Key Endpoints:
- Chat: `POST /interact/chat`
- Greeting: `GET /interact/greeting`
- Notifications: `GET /notifications`
- Feedback: `POST /notifications/feedback`

### Authentication:
- Method: Query parameters
- Required: `name` + `secret_key`

---

## Status: ✅ READY FOR FRONTEND BUILD


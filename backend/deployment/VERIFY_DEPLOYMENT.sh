#!/bin/bash
# Verification script for Sedi Backend deployment

echo "=========================================="
echo "Sedi Backend Deployment Verification"
echo "=========================================="
echo ""

# 1. Check service status
echo "1️⃣ Checking service status..."
systemctl status sedi-backend --no-pager | head -10
echo ""

# 2. Check recent logs for errors
echo "2️⃣ Checking recent logs for errors..."
journalctl -u sedi-backend -n 30 --no-pager | grep -i "error\|exception" || echo "✅ No errors found"
echo ""

# 3. Test root endpoint
echo "3️⃣ Testing root endpoint..."
curl -s http://localhost:8000/ | python3 -m json.tool
echo ""

# 4. Test greeting endpoint
echo "4️⃣ Testing greeting endpoint..."
curl -s "http://localhost:8000/interact/greeting?user_id=1&lang=en" | python3 -m json.tool
echo ""

# 5. Test notifications endpoint
echo "5️⃣ Testing notifications endpoint..."
curl -s "http://localhost:8000/notifications?user_id=1" | python3 -m json.tool
echo ""

# 6. Check database connection
echo "6️⃣ Checking database connection..."
PGPASSWORD='Sedi2025!SecurePass' psql -h localhost -U sedi_user -d sedi_db -c "SELECT COUNT(*) as user_count FROM users;" 2>/dev/null || echo "⚠️ Database check failed"
echo ""

# 7. Check memory entries
echo "7️⃣ Checking conversation memory..."
PGPASSWORD='Sedi2025!SecurePass' psql -h localhost -U sedi_user -d sedi_db -c "SELECT COUNT(*) as memory_count FROM memory WHERE user_id=1;" 2>/dev/null || echo "⚠️ Memory check failed"
echo ""

echo "=========================================="
echo "✅ Verification Complete"
echo "=========================================="


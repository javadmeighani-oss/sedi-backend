#!/bin/bash
# SSH Authentication Diagnostic Script
# Run this on the server as root

echo "=========================================="
echo "SSH Authentication Diagnostic"
echo "=========================================="
echo ""

# 1. Check SSH config
echo "1️⃣ Checking SSH daemon configuration..."
echo "----------------------------------------"
grep -E "^(PermitRootLogin|PubkeyAuthentication|PasswordAuthentication)" /etc/ssh/sshd_config || echo "⚠️  Config not found"
echo ""

# 2. Check .ssh directory
echo "2️⃣ Checking /root/.ssh directory..."
echo "----------------------------------------"
if [ -d "/root/.ssh" ]; then
    echo "✅ /root/.ssh exists"
    ls -la /root/.ssh/
    echo ""
    echo "Permissions:"
    stat -c "%a %n" /root/.ssh
else
    echo "❌ /root/.ssh does NOT exist"
fi
echo ""

# 3. Check authorized_keys
echo "3️⃣ Checking authorized_keys..."
echo "----------------------------------------"
if [ -f "/root/.ssh/authorized_keys" ]; then
    echo "✅ /root/.ssh/authorized_keys exists"
    echo "Permissions:"
    stat -c "%a %n" /root/.ssh/authorized_keys
    echo ""
    echo "Number of keys:"
    wc -l /root/.ssh/authorized_keys
    echo ""
    echo "First key (first 50 chars):"
    head -1 /root/.ssh/authorized_keys | cut -c1-50
else
    echo "❌ /root/.ssh/authorized_keys does NOT exist"
fi
echo ""

# 4. Check SSH service status
echo "4️⃣ Checking SSH service..."
echo "----------------------------------------"
systemctl status sshd --no-pager | head -5
echo ""

# 5. Test SSH from localhost
echo "5️⃣ Testing SSH from localhost..."
echo "----------------------------------------"
ssh -o BatchMode=yes -o ConnectTimeout=5 root@localhost "echo 'SSH test successful'" 2>&1 || echo "⚠️  SSH test failed"
echo ""

echo "=========================================="
echo "Diagnostic Complete"
echo "=========================================="


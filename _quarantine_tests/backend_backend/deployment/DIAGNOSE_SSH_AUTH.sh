#!/bin/bash
# SSH Authentication Diagnostic Script
# Run this on the server to check SSH key setup

echo "=========================================="
echo "SSH Authentication Diagnostic"
echo "=========================================="
echo ""

# 1. Check SSH config
echo "1️⃣ Checking SSH daemon configuration..."
echo "----------------------------------------"
grep -E "^(PermitRootLogin|PubkeyAuthentication|PasswordAuthentication|AuthorizedKeysFile)" /etc/ssh/sshd_config | grep -v "^#" || echo "⚠️  Config not found or commented"
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
    echo "Creating it..."
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh
    echo "✅ Created"
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
    echo "First key (first 80 chars):"
    head -1 /root/.ssh/authorized_keys | cut -c1-80
    echo ""
    echo "Last key (first 80 chars):"
    tail -1 /root/.ssh/authorized_keys | cut -c1-80
else
    echo "❌ /root/.ssh/authorized_keys does NOT exist"
    echo "⚠️  You need to add your public key here!"
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
echo "Summary"
echo "=========================================="
echo ""
echo "Required settings:"
echo "  - PermitRootLogin yes"
echo "  - PubkeyAuthentication yes"
echo "  - /root/.ssh permissions: 700"
echo "  - /root/.ssh/authorized_keys permissions: 600"
echo "  - Public key must be in authorized_keys"
echo ""


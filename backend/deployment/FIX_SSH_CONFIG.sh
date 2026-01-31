#!/bin/bash
# Fix SSH Configuration for GitHub Actions
# Run this on the server as root

set -e

echo "🔧 Fixing SSH Configuration for GitHub Actions..."
echo ""

# 1. Backup SSH config
echo "1️⃣ Backing up SSH config..."
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup.$(date +%Y%m%d_%H%M%S)
echo "✅ Backup created"

# 2. Ensure .ssh directory exists
echo ""
echo "2️⃣ Ensuring /root/.ssh directory exists..."
mkdir -p /root/.ssh
chmod 700 /root/.ssh
echo "✅ Directory created/verified"

# 3. Fix SSH config
echo ""
echo "3️⃣ Updating SSH configuration..."

# Check current settings
PERMIT_ROOT=$(grep -E "^PermitRootLogin" /etc/ssh/sshd_config || echo "")
PUBKEY_AUTH=$(grep -E "^PubkeyAuthentication" /etc/ssh/sshd_config || echo "")

# Update PermitRootLogin
if [ -z "$PERMIT_ROOT" ]; then
    echo "PermitRootLogin yes" >> /etc/ssh/sshd_config
    echo "✅ Added PermitRootLogin yes"
elif [[ "$PERMIT_ROOT" == *"no"* ]]; then
    sed -i 's/^PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
    echo "✅ Changed PermitRootLogin to yes"
else
    echo "✅ PermitRootLogin already enabled"
fi

# Update PubkeyAuthentication
if [ -z "$PUBKEY_AUTH" ]; then
    echo "PubkeyAuthentication yes" >> /etc/ssh/sshd_config
    echo "✅ Added PubkeyAuthentication yes"
elif [[ "$PUBKEY_AUTH" == *"no"* ]]; then
    sed -i 's/^PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
    echo "✅ Changed PubkeyAuthentication to yes"
else
    echo "✅ PubkeyAuthentication already enabled"
fi

# Ensure PasswordAuthentication is disabled (security)
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
if ! grep -q "^PasswordAuthentication" /etc/ssh/sshd_config; then
    echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
fi
echo "✅ PasswordAuthentication disabled"

# 4. Restart SSH service
echo ""
echo "4️⃣ Restarting SSH service..."
systemctl restart sshd
sleep 2
systemctl status sshd --no-pager | head -5
echo "✅ SSH service restarted"

# 5. Verify configuration
echo ""
echo "5️⃣ Verifying configuration..."
echo "----------------------------------------"
grep -E "^(PermitRootLogin|PubkeyAuthentication|PasswordAuthentication)" /etc/ssh/sshd_config
echo ""

echo "=========================================="
echo "✅ SSH Configuration Fixed"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Add your public key to /root/.ssh/authorized_keys"
echo "2. Set permissions: chmod 600 /root/.ssh/authorized_keys"
echo "3. Test SSH connection"


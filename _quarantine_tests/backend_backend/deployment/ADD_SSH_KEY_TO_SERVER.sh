#!/bin/bash
# Add SSH Public Key to Server
# Usage: ./ADD_SSH_KEY_TO_SERVER.sh "ssh-ed25519 AAAA..."

if [ -z "$1" ]; then
    echo "Usage: $0 \"ssh-ed25519 AAAA...\""
    echo "Example: $0 \"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... github-actions-sedi-backend\""
    exit 1
fi

PUBLIC_KEY="$1"

echo "🔑 Adding SSH public key to server..."
echo ""

# Ensure .ssh directory exists
mkdir -p /root/.ssh
chmod 700 /root/.ssh

# Check if key already exists
if grep -q "$PUBLIC_KEY" /root/.ssh/authorized_keys 2>/dev/null; then
    echo "⚠️  Key already exists in authorized_keys"
else
    # Add key to authorized_keys
    echo "$PUBLIC_KEY" >> /root/.ssh/authorized_keys
    echo "✅ Public key added"
fi

# Set correct permissions
chmod 600 /root/.ssh/authorized_keys

# Verify
echo ""
echo "📋 Current authorized_keys:"
echo "----------------------------------------"
cat /root/.ssh/authorized_keys
echo "----------------------------------------"
echo ""
echo "✅ SSH key setup complete!"
echo ""
echo "Test connection from local machine:"
echo "ssh -i /path/to/private/key root@91.107.168.130 'echo \"Test successful\"'"


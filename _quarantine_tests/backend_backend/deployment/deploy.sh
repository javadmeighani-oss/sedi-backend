#!/bin/bash
# Sedi Backend Deployment Script
# Usage: ./deploy.sh

set -e

SERVER_IP="91.107.168.130"
SERVER_USER="ubuntu"
PROJECT_PATH="/var/www/sedi/backend"
SERVICE_NAME="sedi-backend"

echo "🚀 Starting Sedi Backend Deployment..."

# Check if SSH key exists
if [ ! -f ~/.ssh/id_ed25519 ]; then
    echo "📝 Generating SSH key..."
    ssh-keygen -t ed25519 -C "sedi-backend" -f ~/.ssh/id_ed25519 -N ""
fi

# Copy SSH key to server (if not already done)
echo "🔑 Setting up SSH key authentication..."
ssh-copy-id -i ~/.ssh/id_ed25519.pub ${SERVER_USER}@${SERVER_IP} || echo "SSH key may already be configured"

# Copy systemd service file to server
echo "📋 Copying systemd service file..."
scp deployment/sedi-backend.service ${SERVER_USER}@${SERVER_IP}:/tmp/sedi-backend.service

# Execute commands on server
echo "⚙️  Configuring service on server..."
ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
    # Move service file to systemd directory
    sudo mv /tmp/sedi-backend.service /etc/systemd/system/sedi-backend.service
    
    # Reload systemd
    sudo systemctl daemon-reload
    
    # Enable service
    sudo systemctl enable sedi-backend
    
    # Start service
    sudo systemctl restart sedi-backend
    
    # Check status
    echo "📊 Service Status:"
    sudo systemctl status sedi-backend --no-pager
    
    echo "✅ Deployment completed!"
ENDSSH

echo "🎉 Deployment finished successfully!"
echo "📝 To check logs: ssh ${SERVER_USER}@${SERVER_IP} 'sudo journalctl -u sedi-backend -f'"
echo "📝 To restart: ssh ${SERVER_USER}@${SERVER_IP} 'sudo systemctl restart sedi-backend'"


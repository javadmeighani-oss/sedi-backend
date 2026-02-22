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

# Copy SSH key to server (if not already done); skip when on target server or DEPLOY_SKIP_SSH=1
LOCAL_IPS="$(hostname -I 2>/dev/null || true)"
ON_TARGET_SERVER=0
if [ -n "$SERVER_IP" ] && case " $LOCAL_IPS " in *" $SERVER_IP "*) true;; *) false;; esac; then
    ON_TARGET_SERVER=1
fi
if [ "${DEPLOY_SKIP_SSH:-0}" = "1" ] || [ "$ON_TARGET_SERVER" = "1" ]; then
    echo "[DEPLOY] Skipping SSH key setup (already on target server or DEPLOY_SKIP_SSH=1)"
else
    echo "🔑 Setting up SSH key authentication..."
    ssh-copy-id -i ~/.ssh/id_ed25519.pub ${SERVER_USER}@${SERVER_IP} || echo "SSH key may already be configured"
fi

if [ "${DEPLOY_LOCAL:-0}" = "1" ] || [ "$ON_TARGET_SERVER" = "1" ]; then
    # Local mode: no scp/ssh
    echo "[DEPLOY] Running in local mode (no scp/ssh)"
    echo "📋 Copying systemd service file..."
    sudo cp deployment/sedi-backend.service /etc/systemd/system/sedi-backend.service
    echo "⚙️  Configuring service..."
    sudo systemctl daemon-reload
    sudo systemctl enable sedi-backend
    # Enforce V1 production: DEVICE_AUTH_MODE=db_only in env (does not overwrite other vars)
    sudo mkdir -p /etc/sedi
    if [ -f /etc/sedi/sedi-backend.env ]; then
        if sudo grep -q '^DEVICE_AUTH_MODE=' /etc/sedi/sedi-backend.env; then
            sudo sed -i 's/^DEVICE_AUTH_MODE=.*/DEVICE_AUTH_MODE=db_only/' /etc/sedi/sedi-backend.env
        else
            echo 'DEVICE_AUTH_MODE=db_only' | sudo tee -a /etc/sedi/sedi-backend.env > /dev/null
        fi
    else
        echo 'DEVICE_AUTH_MODE=db_only' | sudo tee /etc/sedi/sedi-backend.env > /dev/null
    fi
    echo "[DEPLOY] Enforced DEVICE_AUTH_MODE=db_only"
    sudo systemctl restart sedi-backend
    echo "📊 Service Status:"
    sudo systemctl status sedi-backend --no-pager
    echo "✅ Deployment completed!"
    echo "🎉 Deployment finished successfully!"
    echo "📝 To check logs: sudo journalctl -u sedi-backend -f"
    echo "📝 To restart: sudo systemctl restart sedi-backend"
else
    # Remote mode: scp + ssh
    echo "📋 Copying systemd service file to server..."
    scp deployment/sedi-backend.service ${SERVER_USER}@${SERVER_IP}:/tmp/sedi-backend.service
    echo "⚙️  Configuring service on server..."
    ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
    # Move service file to systemd directory
    sudo mv /tmp/sedi-backend.service /etc/systemd/system/sedi-backend.service
    
    # Reload systemd
    sudo systemctl daemon-reload
    
    # Enable service
    sudo systemctl enable sedi-backend
    
    # Enforce V1 production: DEVICE_AUTH_MODE=db_only in env (does not overwrite other vars)
    sudo mkdir -p /etc/sedi
    if [ -f /etc/sedi/sedi-backend.env ]; then
        if sudo grep -q '^DEVICE_AUTH_MODE=' /etc/sedi/sedi-backend.env; then
            sudo sed -i 's/^DEVICE_AUTH_MODE=.*/DEVICE_AUTH_MODE=db_only/' /etc/sedi/sedi-backend.env
        else
            echo 'DEVICE_AUTH_MODE=db_only' | sudo tee -a /etc/sedi/sedi-backend.env > /dev/null
        fi
    else
        echo 'DEVICE_AUTH_MODE=db_only' | sudo tee /etc/sedi/sedi-backend.env > /dev/null
    fi
    echo "[DEPLOY] Enforced DEVICE_AUTH_MODE=db_only"
    
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
fi


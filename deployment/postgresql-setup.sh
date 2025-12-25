#!/bin/bash
# PostgreSQL Setup Script for Sedi Backend
# Run this script on the Ubuntu 22.04 server

set -e

echo "🐘 Starting PostgreSQL setup for Sedi Backend..."

# Step 1: Install PostgreSQL
echo "📦 Installing PostgreSQL..."
apt-get update
apt-get install -y postgresql postgresql-contrib

# Step 2: Start and enable PostgreSQL service
echo "🚀 Starting PostgreSQL service..."
systemctl start postgresql
systemctl enable postgresql

# Step 3: Create database and user
echo "🗄️  Creating database and user..."

# Generate a random password
DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)

# Switch to postgres user and create database/user
sudo -u postgres psql << EOF
-- Create user
CREATE USER sedi_user WITH PASSWORD '${DB_PASSWORD}';

-- Create database
CREATE DATABASE sedi_db OWNER sedi_user;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE sedi_db TO sedi_user;

-- Connect to sedi_db and grant schema privileges
\c sedi_db
GRANT ALL ON SCHEMA public TO sedi_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO sedi_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO sedi_user;
EOF

# Step 4: Update .env file
echo "📝 Updating .env file..."
ENV_FILE="/var/www/sedi/backend/.env"

# Check if .env exists, if not create it
if [ ! -f "$ENV_FILE" ]; then
    touch "$ENV_FILE"
fi

# Add or update DATABASE_URL
if grep -q "DATABASE_URL" "$ENV_FILE"; then
    # Update existing DATABASE_URL
    sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg2://sedi_user:${DB_PASSWORD}@localhost:5432/sedi_db|" "$ENV_FILE"
else
    # Add new DATABASE_URL
    echo "DATABASE_URL=postgresql+psycopg2://sedi_user:${DB_PASSWORD}@localhost:5432/sedi_db" >> "$ENV_FILE"
fi

echo ""
echo "✅ PostgreSQL setup completed successfully!"
echo ""
echo "📋 Database Information:"
echo "   Database: sedi_db"
echo "   User: sedi_user"
echo "   Password: ${DB_PASSWORD}"
echo "   Connection: localhost:5432"
echo ""
echo "⚠️  IMPORTANT: Save the password above securely!"
echo ""
echo "📝 DATABASE_URL has been added to: $ENV_FILE"
echo ""
echo "🔧 Next steps:"
echo "   1. Install Python dependencies: pip install -r requirements.txt"
echo "   2. Restart backend service: systemctl restart sedi-backend"
echo "   3. Verify: systemctl status sedi-backend"


#!/bin/bash
# Script to apply dedupe_key migration to notifications table
# Usage: ./apply_migration.sh

set -e

DB_NAME="sedi_db"
MIGRATION_FILE="001_add_dedupe_key_to_notifications.sql"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATION_PATH="$SCRIPT_DIR/$MIGRATION_FILE"

echo "=========================================="
echo "Applying dedupe_key migration"
echo "=========================================="
echo ""

# Check if migration file exists
if [ ! -f "$MIGRATION_PATH" ]; then
    echo "❌ Error: Migration file not found: $MIGRATION_PATH"
    exit 1
fi

# Check if running as postgres user or with sudo
if [ "$EUID" -eq 0 ] || [ "$USER" = "postgres" ]; then
    PSQL_CMD="psql"
else
    echo "⚠️  Note: This script should be run as postgres user or with sudo"
    echo "   Attempting with sudo..."
    PSQL_CMD="sudo -u postgres psql"
fi

# Apply migration
echo "📋 Applying migration: $MIGRATION_FILE"
echo ""

if [ -n "$PSQL_CMD" ]; then
    $PSQL_CMD -d "$DB_NAME" -f "$MIGRATION_PATH"
else
    psql -d "$DB_NAME" -f "$MIGRATION_PATH"
fi

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Migration applied successfully!"
    echo ""
    echo "📊 Verifying migration..."
    echo ""
    
    # Verify column exists
    echo "Checking column..."
    if [ -n "$PSQL_CMD" ]; then
        $PSQL_CMD -d "$DB_NAME" -c "\d+ notifications" | grep -q "dedupe_key" && echo "✅ Column 'dedupe_key' exists" || echo "❌ Column 'dedupe_key' not found"
    else
        psql -d "$DB_NAME" -c "\d+ notifications" | grep -q "dedupe_key" && echo "✅ Column 'dedupe_key' exists" || echo "❌ Column 'dedupe_key' not found"
    fi
    
    # Verify indexes
    echo ""
    echo "Checking indexes..."
    if [ -n "$PSQL_CMD" ]; then
        $PSQL_CMD -d "$DB_NAME" -c "\di+ idx_notifications_user_dedupe_key" > /dev/null 2>&1 && echo "✅ Composite index exists" || echo "❌ Composite index not found"
        $PSQL_CMD -d "$DB_NAME" -c "\di+ idx_notifications_dedupe_key" > /dev/null 2>&1 && echo "✅ dedupe_key index exists" || echo "❌ dedupe_key index not found"
    else
        psql -d "$DB_NAME" -c "\di+ idx_notifications_user_dedupe_key" > /dev/null 2>&1 && echo "✅ Composite index exists" || echo "❌ Composite index not found"
        psql -d "$DB_NAME" -c "\di+ idx_notifications_dedupe_key" > /dev/null 2>&1 && echo "✅ dedupe_key index exists" || echo "❌ dedupe_key index not found"
    fi
    
    echo ""
    echo "=========================================="
    echo "Migration complete!"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "1. Restart backend service: systemctl restart sedi-backend.service"
    echo "2. Check service status: systemctl status sedi-backend.service"
    echo "3. Monitor logs: journalctl -u sedi-backend.service -f"
else
    echo ""
    echo "❌ Migration failed!"
    echo "   Check the error message above"
    exit 1
fi

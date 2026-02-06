# Migration Summary: Add dedupe_key to notifications

## Quick Reference

### Apply Migration (Production Server)

```bash
# Option 1: Using the script
cd /var/www/sedi/backend/deployment/migrations
chmod +x apply_migration.sh
sudo ./apply_migration.sh

# Option 2: Direct SQL
sudo -u postgres psql -d sedi_db -f /var/www/sedi/backend/deployment/migrations/001_add_dedupe_key_to_notifications.sql

# Option 3: Manual SQL
sudo -u postgres psql -d sedi_db << 'EOF'
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(255) NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_user_dedupe_key ON public.notifications(user_id, dedupe_key) WHERE dedupe_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_dedupe_key ON public.notifications(dedupe_key) WHERE dedupe_key IS NOT NULL;
EOF
```

### Verify Migration

```bash
# Check column
sudo -u postgres psql -d sedi_db -c "\d+ notifications" | grep dedupe_key

# Check indexes
sudo -u postgres psql -d sedi_db -c "\di+ idx_notifications_user_dedupe_key"
sudo -u postgres psql -d sedi_db -c "\di+ idx_notifications_dedupe_key"
```

### Restart Service

```bash
systemctl restart sedi-backend.service
systemctl status sedi-backend.service
```

## What Gets Added

1. **Column:** `dedupe_key VARCHAR(255) NULL`
2. **Composite Index:** `(user_id, dedupe_key)` - partial (only non-null values)
3. **Dedupe Index:** `(dedupe_key)` - partial (only non-null values)

## Impact

- ✅ Safe: Column is nullable, existing rows unaffected
- ✅ Efficient: Partial indexes only index non-null values
- ✅ Fast: Composite index optimizes dedupe queries
- ✅ Backward compatible: Old code continues to work

## Files

- Migration SQL: `001_add_dedupe_key_to_notifications.sql`
- Apply Script: `apply_migration.sh`
- Full Docs: `../ADD_DEDUPE_KEY_MIGRATION.md`

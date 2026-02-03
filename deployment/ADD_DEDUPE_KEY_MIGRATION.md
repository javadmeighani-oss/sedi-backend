# Migration: Add dedupe_key to notifications table

**Release:** B - Part B1  
**Date:** 2026-02-02  
**Database:** PostgreSQL (sedi_db)

## Overview

This migration adds the `dedupe_key` column to the `notifications` table to support deterministic deduplication of notifications in Release B.

## Prerequisites

- PostgreSQL database `sedi_db` is running
- You have access to the database as `postgres` user or `sedi_user`
- Backend code has been updated (already done in commit `ce6ff03`)

## Migration Steps

### Step 1: Backup Database (Recommended)

```bash
# Create backup before migration
sudo -u postgres pg_dump sedi_db > /tmp/sedi_db_backup_$(date +%Y%m%d_%H%M%S).sql
```

### Step 2: Apply Migration

**Option A: Using psql command line**

```bash
# Connect to database
sudo -u postgres psql -d sedi_db

# Run migration
\i /var/www/sedi/backend/deployment/migrations/001_add_dedupe_key_to_notifications.sql

# Or from command line:
sudo -u postgres psql -d sedi_db -f /var/www/sedi/backend/deployment/migrations/001_add_dedupe_key_to_notifications.sql
```

**Option B: Copy-paste SQL directly**

```bash
sudo -u postgres psql -d sedi_db << 'EOF'
ALTER TABLE public.notifications
ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(255) NULL;

CREATE INDEX IF NOT EXISTS idx_notifications_user_dedupe_key 
ON public.notifications(user_id, dedupe_key)
WHERE dedupe_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_notifications_dedupe_key 
ON public.notifications(dedupe_key)
WHERE dedupe_key IS NOT NULL;
EOF
```

### Step 3: Verify Migration

```bash
# Check column exists
sudo -u postgres psql -d sedi_db -c "\d+ notifications" | grep dedupe_key

# Expected output should show:
# dedupe_key | character varying(255) |           |          | 

# Check composite index
sudo -u postgres psql -d sedi_db -c "\di+ idx_notifications_user_dedupe_key"

# Check dedupe_key index
sudo -u postgres psql -d sedi_db -c "\di+ idx_notifications_dedupe_key"
```

### Step 4: Restart Backend Service

```bash
# Restart service to ensure it picks up the new schema
systemctl restart sedi-backend.service

# Check status
systemctl status sedi-backend.service --no-pager

# Check logs
journalctl -u sedi-backend.service -n 30 --no-pager
```

## What This Migration Does

1. **Adds `dedupe_key` column:**
   - Type: `VARCHAR(255)`
   - Nullable: `YES` (to avoid breaking existing rows)
   - Default: `NULL`

2. **Creates composite index:**
   - Index name: `idx_notifications_user_dedupe_key`
   - Columns: `(user_id, dedupe_key)`
   - Partial index (only includes rows where `dedupe_key IS NOT NULL`)
   - Optimizes queries like: `WHERE user_id = ? AND dedupe_key = ? AND created_at >= ?`

3. **Creates dedupe_key index:**
   - Index name: `idx_notifications_dedupe_key`
   - Column: `dedupe_key`
   - Partial index (only includes rows where `dedupe_key IS NOT NULL`)
   - Optimizes direct dedupe_key lookups

## Impact

- **Existing rows:** Will have `dedupe_key = NULL` (this is expected and safe)
- **New rows:** Will have `dedupe_key` populated by the application code
- **Performance:** Indexes improve dedupe check performance
- **Storage:** Minimal impact (nullable column, partial indexes)

## Rollback (If Needed)

If you need to rollback this migration:

```sql
-- Remove indexes
DROP INDEX IF EXISTS idx_notifications_dedupe_key;
DROP INDEX IF EXISTS idx_notifications_user_dedupe_key;

-- Remove column
ALTER TABLE public.notifications DROP COLUMN IF EXISTS dedupe_key;
```

**Note:** Only rollback if you're sure no new code is using `dedupe_key`. After rollback, you'll need to revert the code changes as well.

## Testing

After migration, test that:

1. **Backend starts successfully:**
   ```bash
   systemctl status sedi-backend.service
   ```

2. **Notifications can be created:**
   ```bash
   curl -X POST http://localhost:8000/notifications/create \
     -H "Content-Type: application/json" \
     -d '{"user_id": 1, "type": "morning_brief", "title": "Test", "body": "Test notification"}'
   ```

3. **Dedupe logic works:**
   - Create a notification with a `dedupe_key`
   - Try to create the same notification again
   - Second attempt should be blocked (duplicate)

## Troubleshooting

### Error: "column dedupe_key already exists"
- This means the migration was already applied. You can safely skip it.

### Error: "permission denied"
- Make sure you're running as `postgres` user or have proper permissions:
  ```bash
  sudo -u postgres psql -d sedi_db
  ```

### Backend fails to start after migration
- Check logs: `journalctl -u sedi-backend.service -n 50`
- Verify column exists: `sudo -u postgres psql -d sedi_db -c "\d+ notifications"`
- Ensure SQLAlchemy model matches: Check `app/models.py` line 55

## Related Files

- Migration SQL: `deployment/migrations/001_add_dedupe_key_to_notifications.sql`
- Model definition: `app/models.py` (line 55)
- Dedupe logic: `app/services/notification_engine.py` (methods: `compute_dedupe_key`, `check_dedupe`)

## Next Steps

After successful migration:

1. ✅ Verify column and indexes exist
2. ✅ Restart backend service
3. ✅ Test notification creation
4. ✅ Monitor logs for any issues

---

**Important:** Apply this migration **BEFORE** deploying code that uses `dedupe_key` to avoid errors.

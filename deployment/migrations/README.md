# Database Migrations

This directory contains SQL migration files for the Sedi backend database.

## Migration Files

- `001_add_dedupe_key_to_notifications.sql` - Adds `dedupe_key` column and indexes to notifications table (Release B - Part B1)
- `002_add_device_events.sql` - Creates `device_events` table for device ingestion platform (Release C1)
- `003_harden_device_events.sql` - Hardens `device_events` table with defaults and indexes (Release C1.1)

## How to Apply Migrations

### On Production Server

1. **Connect to PostgreSQL:**
   ```bash
   sudo -u postgres psql -d sedi_db
   ```

2. **Apply migration:**
   ```sql
   \i /var/www/sedi/backend/deployment/migrations/001_add_dedupe_key_to_notifications.sql
   ```
   
   Or copy-paste the SQL directly:
   ```bash
   sudo -u postgres psql -d sedi_db -f /var/www/sedi/backend/deployment/migrations/001_add_dedupe_key_to_notifications.sql
   ```

3. **Verify migration:**
   ```sql
   \d+ notifications
   ```
   
   You should see the `dedupe_key` column and the indexes.

### Verification Commands

```bash
# Check column exists
sudo -u postgres psql -d sedi_db -c "\d+ notifications" | grep dedupe_key

# Check index (matches production: ix_notifications_user_dedupe)
sudo -u postgres psql -d sedi_db -c "\di+ ix_notifications_user_dedupe"

# Verify device_events table structure
sudo -u postgres psql -d sedi_db -c "\d+ device_events"

# Check device_events indexes
sudo -u postgres psql -d sedi_db -c "\di+ ix_device_events_user_time"
sudo -u postgres psql -d sedi_db -c "\di+ ix_device_events_user_dedupe"
```

## Migration Order

Migrations should be applied in order (001, 002, etc.). Always check the migration file for any prerequisites.

## Rollback

If you need to rollback a migration, check the migration file for rollback instructions or create a rollback script.

# Deployment Documentation

This directory contains deployment scripts, configurations, and migration files for the Sedi backend.

## Database Migrations

Database migrations are located in `deployment/migrations/` directory.

### Applying Migrations

To apply a migration on the production server:

```bash
sudo -u postgres psql -d sedi_db -f /var/www/sedi/backend/deployment/migrations/001_add_dedupe_key_to_notifications.sql
```

Or from within psql:

```sql
\i /var/www/sedi/backend/deployment/migrations/001_add_dedupe_key_to_notifications.sql
```

### Available Migrations

- `001_add_dedupe_key_to_notifications.sql` - Adds `dedupe_key` column and index to notifications table (Release B - Part B1)

See `deployment/migrations/README.md` for detailed migration instructions.

## Service Management

### Systemd Service

The backend runs as a systemd service: `sedi-backend.service`

**Location:** `/etc/systemd/system/sedi-backend.service`

**Common Commands:**

```bash
# Restart service
systemctl restart sedi-backend.service

# Check status
systemctl status sedi-backend.service

# View logs
journalctl -u sedi-backend.service -f
```

## Server Information

- **Server IP:** 91.107.168.130
- **Backend Path:** `/var/www/sedi/backend`
- **Database:** PostgreSQL (`sedi_db`)
- **Service:** `sedi-backend.service`

## Deployment Process

1. **Push to GitHub:** Changes are automatically deployed via GitHub Actions
2. **Apply Migrations:** If database changes are needed, apply migrations manually
3. **Restart Service:** Service restarts automatically after deployment

## Related Documentation

- `POSTGRESQL_MIGRATION.md` - PostgreSQL setup and migration guide
- `ADD_DEDUPE_KEY_MIGRATION.md` - Detailed dedupe_key migration guide
- `migrations/README.md` - Migration files documentation

# Notifications DB Index Sanity (Stage 16.6.7)

Index inventory and sanity checks for the notification subsystem.

---

## Indexes (from migration 006)

### push_devices

| Index | Columns | Purpose |
|-------|---------|---------|
| `ix_push_devices_fcm_token` | fcm_token | Token lookups, upsert |
| `ix_push_devices_user_active` | user_id, is_active | Devices per user for delivery |

### notification_feedback

| Index | Columns | Purpose |
|-------|---------|---------|
| `ix_notification_feedback_notification_id` | notification_id | Lookups by notification |
| `ix_notification_feedback_user_id` | user_id | Feedback per user |

### notifications

| Index | Columns | Purpose |
|-------|---------|---------|
| `ix_notifications_status_sent_created` | status, is_sent, created_at | Delivery outbox query |
| `ix_notifications_user_channel_created` | user_id, channel, created_at | User history, dedupe |

---

## Delivery Query

The delivery outbox filters:

```sql
WHERE is_sent = false
  AND (scheduled_for IS NULL OR scheduled_for <= now())
ORDER BY created_at ASC
```

`ix_notifications_status_sent_created` supports this when combined with status filters. For high load, consider an additional index on `(is_sent, scheduled_for)` if query plans show seq scans.

---

## Sanity Checks (PostgreSQL)

```sql
-- List notification-related indexes
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename IN ('push_devices', 'notification_feedback', 'notifications')
  AND schemaname = 'public';
```

---

## Ops Cadence

- **Weekly**: Check `notifications` row count; run `VACUUM ANALYZE notifications` if large.
- **Post-rollout**: Run `EXPLAIN ANALYZE` on delivery query; ensure index usage.
- **Scale-up**: If `DELIVER_BATCH_SIZE` > 500, verify index usage and DB connections.

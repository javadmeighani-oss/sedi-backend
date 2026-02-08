-- Migration: Add sent_at + indexes for Release D notifications
-- Idempotent: ADD COLUMN IF NOT EXISTS, CREATE INDEX IF NOT EXISTS
-- Do NOT drop/rename anything.

BEGIN;

ALTER TABLE public.notifications
  ADD COLUMN IF NOT EXISTS sent_at timestamp without time zone;

CREATE INDEX IF NOT EXISTS ix_notifications_user_type
  ON public.notifications (user_id, type);

CREATE INDEX IF NOT EXISTS ix_notifications_unsent_scheduled
  ON public.notifications (is_sent, scheduled_for);

COMMIT;

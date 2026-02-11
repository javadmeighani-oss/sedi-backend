-- Migration: Stage 16.6 Push Notifications v1 (FCM)
-- Adds: push_devices, notification_feedback, notifications push columns + indexes
-- Idempotent: CREATE TABLE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS, CREATE INDEX IF NOT EXISTS

BEGIN;

-- 1) push_devices table
CREATE TABLE IF NOT EXISTS public.push_devices (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    platform VARCHAR(20) NOT NULL,
    fcm_token VARCHAR(512) NOT NULL,
    device_id VARCHAR(255) NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    last_seen_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_push_devices_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE,
    CONSTRAINT uq_push_devices_fcm_token UNIQUE (fcm_token)
);

CREATE INDEX IF NOT EXISTS ix_push_devices_fcm_token ON public.push_devices(fcm_token);
CREATE INDEX IF NOT EXISTS ix_push_devices_user_active ON public.push_devices(user_id, is_active);

-- 2) notification_feedback table
CREATE TABLE IF NOT EXISTS public.notification_feedback (
    id SERIAL PRIMARY KEY,
    notification_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    action VARCHAR(50) NOT NULL,
    meta_json TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_notification_feedback_notification FOREIGN KEY (notification_id) REFERENCES public.notifications(id) ON DELETE CASCADE,
    CONSTRAINT fk_notification_feedback_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_notification_feedback_notification_id ON public.notification_feedback(notification_id);
CREATE INDEX IF NOT EXISTS ix_notification_feedback_user_id ON public.notification_feedback(user_id);

-- 3) notifications: additive columns (Stage 16.6)
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS channel VARCHAR(50) NULL;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS language VARCHAR(20) NULL;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS actions_json TEXT NULL;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS deeplink_url VARCHAR(512) NULL;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS provider VARCHAR(50) NULL;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS provider_message_id VARCHAR(255) NULL;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS status VARCHAR(20) NULL;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS last_error TEXT NULL;
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS ttl_seconds INTEGER NULL;

-- 4) notifications: indexes for delivery and queries
CREATE INDEX IF NOT EXISTS ix_notifications_status_sent_created
  ON public.notifications (status, is_sent, created_at);

CREATE INDEX IF NOT EXISTS ix_notifications_user_channel_created
  ON public.notifications (user_id, channel, created_at);

COMMIT;

-- Migration: Add devices table (Release C2 - Device Identity v1)
-- Created: 2026-02-04
-- Description: Creates devices table for per-device tokens and device management
-- Status: Idempotent - safe to run multiple times
-- Purpose: Store device identity with hashed tokens (no raw tokens stored)

-- Step 1: Create devices table (idempotent)
CREATE TABLE IF NOT EXISTS public.devices (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    device_id VARCHAR(255) NOT NULL UNIQUE,  -- logical id like "Sedi001"
    device_type VARCHAR(50) NOT NULL DEFAULT 'heart_rate',
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, revoked
    token_hash VARCHAR(255) NOT NULL,              -- sha256 hex, not raw token
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMP NULL,
    last_seen_at TIMESTAMP NULL,
    CONSTRAINT fk_devices_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE
);

-- Step 2: Indexes (idempotent)
CREATE INDEX IF NOT EXISTS ix_devices_user_id
ON public.devices(user_id);

CREATE INDEX IF NOT EXISTS ix_devices_status
ON public.devices(status);

-- Verification queries:
-- \d+ devices
-- \di+ ix_devices_user_id
-- \di+ ix_devices_status
-- SELECT device_id, status, last_seen_at FROM devices ORDER BY id DESC LIMIT 10;

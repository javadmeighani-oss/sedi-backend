-- Migration: Harden devices table defaults (Release C2.1)
-- Created: 2026-02-04
-- Description: Ensures DB defaults exist for devices.device_type/status/created_at and adds optional status check constraint
-- Status: Idempotent - safe to run multiple times

-- Step 1: Ensure defaults (safe if already set)
ALTER TABLE public.devices
ALTER COLUMN device_type SET DEFAULT 'heart_rate';

ALTER TABLE public.devices
ALTER COLUMN status SET DEFAULT 'active';

ALTER TABLE public.devices
ALTER COLUMN created_at SET DEFAULT NOW();

-- Step 2 (optional but recommended): Constrain status to known values
-- Use guarded DO block for idempotency (Postgres)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_devices_status_known'
          AND conrelid = 'public.devices'::regclass
    ) THEN
        ALTER TABLE public.devices
        ADD CONSTRAINT ck_devices_status_known
        CHECK (status IN ('active', 'revoked'));
    END IF;
END $$;

-- Verification:
-- \d+ devices  -- should show defaults on device_type/status/created_at and the check constraint
-- SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'public.devices'::regclass;

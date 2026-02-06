-- Migration: Harden device_events table (Release C1.1)
-- Created: 2026-02-02
-- Description: Ensures received_at has default and creates required indexes for scale
-- Status: Idempotent - safe to run multiple times
-- Purpose: Production hardening for device_events table performance and data integrity

-- Step 1: Ensure received_at has default NOW() (idempotent)
-- This is safe to run even if the default already exists
ALTER TABLE public.device_events
ALTER COLUMN received_at SET DEFAULT NOW();

-- Step 2: Create index for recent queries by user (idempotent)
-- This index supports queries like: WHERE user_id = ? ORDER BY received_at DESC
CREATE INDEX IF NOT EXISTS ix_device_events_user_time
ON public.device_events(user_id, received_at DESC);

-- Step 3: Create dedupe index (partial, only for non-null dedupe_key)
-- This index supports deduplication checks efficiently
CREATE INDEX IF NOT EXISTS ix_device_events_user_dedupe
ON public.device_events(user_id, dedupe_key)
WHERE dedupe_key IS NOT NULL;

-- Verification queries (run these to verify):
-- \d+ device_events  -- Should show received_at with default NOW()
-- \di+ ix_device_events_user_time  -- Should show the index
-- \di+ ix_device_events_user_dedupe  -- Should show the partial index
-- SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'device_events';

-- Migration: Add device_events table (Release C1 - Device Ingestion Platform v0)
-- Created: 2026-02-02
-- Description: Creates device_events table for ingesting device vital signs data
-- Status: Idempotent - safe to run multiple times
-- Purpose: Store raw device events (heart_rate, etc.) with deduplication support

-- Step 1: Create device_events table (idempotent)
CREATE TABLE IF NOT EXISTS public.device_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    device_id VARCHAR(255) NULL,
    event_type VARCHAR(100) NOT NULL,
    payload_json TEXT NOT NULL,
    recorded_at TIMESTAMP NULL,
    received_at TIMESTAMP NOT NULL DEFAULT NOW(),
    dedupe_key VARCHAR(255) NULL,
    embedding_id VARCHAR(255) NULL,
    CONSTRAINT fk_device_events_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE
);

-- Step 2: Create indexes (idempotent)
-- Index for user + time queries (most common pattern)
CREATE INDEX IF NOT EXISTS ix_device_events_user_time 
ON public.device_events(user_id, received_at DESC);

-- Index for user + device_id queries
CREATE INDEX IF NOT EXISTS ix_device_events_user_device 
ON public.device_events(user_id, device_id) 
WHERE device_id IS NOT NULL;

-- Index for event_type filtering
CREATE INDEX IF NOT EXISTS ix_device_events_type 
ON public.device_events(event_type);

-- Composite index for dedupe checks (only when dedupe_key is not null)
CREATE INDEX IF NOT EXISTS ix_device_events_user_dedupe 
ON public.device_events(user_id, dedupe_key) 
WHERE dedupe_key IS NOT NULL;

-- Verification queries (run these to verify):
-- \d+ device_events  -- Should show all columns and indexes
-- SELECT COUNT(*) FROM device_events;  -- Should return 0 initially
-- \di+ ix_device_events_user_time  -- Should show the index

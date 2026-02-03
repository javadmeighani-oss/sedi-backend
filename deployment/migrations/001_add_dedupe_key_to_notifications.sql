-- Migration: Add dedupe_key column to notifications table (Release B - Part B1)
-- Created: 2026-02-02
-- Description: Adds nullable dedupe_key column and composite index for efficient dedupe checks

-- Step 1: Add nullable dedupe_key column
ALTER TABLE public.notifications
ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(255) NULL;

-- Step 2: Add composite index for efficient dedupe queries
-- This index supports queries like: WHERE user_id = ? AND dedupe_key = ? AND created_at >= ?
CREATE INDEX IF NOT EXISTS idx_notifications_user_dedupe_key 
ON public.notifications(user_id, dedupe_key)
WHERE dedupe_key IS NOT NULL;

-- Step 3: Add separate index on dedupe_key for direct lookups (if needed)
-- This is optional but can help with queries that only filter by dedupe_key
CREATE INDEX IF NOT EXISTS idx_notifications_dedupe_key 
ON public.notifications(dedupe_key)
WHERE dedupe_key IS NOT NULL;

-- Verification queries (run these to verify):
-- \d+ notifications  -- Should show dedupe_key column
-- \di+ idx_notifications_user_dedupe_key  -- Should show the composite index
-- \di+ idx_notifications_dedupe_key  -- Should show the dedupe_key index

-- Migration: Add dedupe_key column to notifications table (Release B - Part B1)
-- Created: 2026-02-02
-- Description: Adds nullable dedupe_key column and composite index for efficient dedupe checks
-- Status: Already applied on production (sedi_db)
-- Purpose: Official migration file to keep environments consistent

-- Step 1: Add nullable dedupe_key column (idempotent)
ALTER TABLE public.notifications
ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(255) NULL;

-- Step 2: Add composite index matching production (idempotent)
-- Production index name: ix_notifications_user_dedupe
-- This index supports queries like: WHERE user_id = ? AND dedupe_key = ? AND created_at >= ?
CREATE INDEX IF NOT EXISTS ix_notifications_user_dedupe 
ON public.notifications(user_id, dedupe_key)
WHERE dedupe_key IS NOT NULL;

-- Verification queries (run these to verify):
-- \d+ notifications  -- Should show dedupe_key column
-- \di+ ix_notifications_user_dedupe  -- Should show the composite index

-- Run once in Supabase SQL Editor if the column is missing (fixes UndefinedColumnError).
ALTER TABLE app_users ADD COLUMN IF NOT EXISTS last_username_change TIMESTAMPTZ;

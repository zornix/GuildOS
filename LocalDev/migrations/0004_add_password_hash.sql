-- 0004_add_password_hash.sql
-- Add nullable password_hash column to members table.
-- Only officers are expected to have a password; members use email-only login.

ALTER TABLE members ADD COLUMN IF NOT EXISTS password_hash TEXT;

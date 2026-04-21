-- 0002_link_members_auth_id.sql
-- Adds optional Supabase auth linkage. In local PostgreSQL this is a no-op
-- beyond adding the nullable column because the auth.users table does not exist.

ALTER TABLE members ADD COLUMN IF NOT EXISTS auth_id UUID;
CREATE INDEX IF NOT EXISTS ix_members_auth_id ON members(auth_id);

DO $$
BEGIN
    IF to_regclass('auth.users') IS NOT NULL THEN
        UPDATE public.members AS m
        SET auth_id = u.id
        FROM auth.users AS u
        WHERE lower(trim(m.email)) = lower(trim(u.email))
          AND m.auth_id IS NULL
          AND u.email IS NOT NULL;
    END IF;
END $$;

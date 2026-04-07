-- Link public.members.auth_id to auth.users.id by email (Supabase magic link / signup).
-- Run in Supabase Dashboard → SQL Editor (or any superuser session).
--
-- Prerequisites: rows in public.members already exist with the same email as auth.users.

-- Preview rows that would be linked (optional):
-- SELECT m.id AS member_id, m.email, m.auth_id AS current_auth_id, u.id AS auth_user_id
-- FROM public.members m
-- INNER JOIN auth.users u ON lower(trim(m.email)) = lower(trim(u.email))
-- WHERE m.auth_id IS NULL;

-- Safe default: only fill auth_id when it is still NULL.
UPDATE public.members AS m
SET auth_id = u.id
FROM auth.users AS u
WHERE lower(trim(m.email)) = lower(trim(u.email))
  AND m.auth_id IS NULL
  AND u.email IS NOT NULL;

-- Optional — only if you fixed the wrong account or changed emails and need to re-point
-- a member row at the current auth user (review the SELECT below first):
--
-- SELECT m.id, m.email, m.auth_id, u.id AS should_be
-- FROM public.members m
-- JOIN auth.users u ON lower(trim(m.email)) = lower(trim(u.email))
-- WHERE m.auth_id IS DISTINCT FROM u.id;
--
-- UPDATE public.members AS m
-- SET auth_id = u.id
-- FROM auth.users AS u
-- WHERE lower(trim(m.email)) = lower(trim(u.email))
--   AND u.email IS NOT NULL
--   AND m.auth_id IS DISTINCT FROM u.id;

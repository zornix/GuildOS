-- Phone numbers are stored in E.164 everywhere (decision: single canonical form).
--
-- Before this migration `members.phone` held whatever a seed or import wrote
-- (bare 9-digit strings like '555111001'), while the SMS paths wrote and read
-- '+1...' — so "the same number" had several spellings and lookups silently
-- missed. The phone check-in flow was the visible casualty: the check-in page
-- collects 10 digits, the PhoneCheckIn schema demanded exactly 9, and the
-- member row held 9, so no combination could ever match.
--
-- This migration:
--   1. backfills members.phone / recruits.phone to E.164, NULLing anything that
--      cannot be parsed (an unparseable phone is not a phone);
--   2. pins the invariant with a CHECK constraint, added NOT VALID then
--      VALIDATEd so the table is never long-locked.
--
-- The runtime conversion point is `api/phone.py:to_e164` — the ONLY sanctioned
-- normalizer. The CASE expression below is a deliberate one-time mirror of its
-- rules (leading '+' -> 8..15 digits; 10 digits -> +1; 11 digits starting with
-- '1' -> +; else NULL). It is intentionally NOT installed as a permanent SQL
-- function: a second callable normalizer is exactly how the two spellings
-- diverged in the first place.
--
-- Append-only migration rule: new file, nothing in 0001..0148 is edited.

-- ── 1. backfill members.phone ────────────────────────────────────────────────
-- Rows already in E.164 are skipped by the WHERE, so a rerun is a no-op.

UPDATE members
   SET phone = CASE
       WHEN phone ~ '^\s*\+'
            AND length(regexp_replace(phone, '\D', '', 'g')) BETWEEN 8 AND 15
           THEN '+' || regexp_replace(phone, '\D', '', 'g')
       WHEN phone !~ '^\s*\+'
            AND length(regexp_replace(phone, '\D', '', 'g')) = 10
           THEN '+1' || regexp_replace(phone, '\D', '', 'g')
       WHEN phone !~ '^\s*\+'
            AND length(regexp_replace(phone, '\D', '', 'g')) = 11
            AND left(regexp_replace(phone, '\D', '', 'g'), 1) = '1'
           THEN '+' || regexp_replace(phone, '\D', '', 'g')
       ELSE NULL
   END
 WHERE phone IS NOT NULL
   AND phone !~ '^\+[0-9]{8,15}$';

-- ── 2. backfill recruits.phone (same rules) ──────────────────────────────────

UPDATE recruits
   SET phone = CASE
       WHEN phone ~ '^\s*\+'
            AND length(regexp_replace(phone, '\D', '', 'g')) BETWEEN 8 AND 15
           THEN '+' || regexp_replace(phone, '\D', '', 'g')
       WHEN phone !~ '^\s*\+'
            AND length(regexp_replace(phone, '\D', '', 'g')) = 10
           THEN '+1' || regexp_replace(phone, '\D', '', 'g')
       WHEN phone !~ '^\s*\+'
            AND length(regexp_replace(phone, '\D', '', 'g')) = 11
            AND left(regexp_replace(phone, '\D', '', 'g'), 1) = '1'
           THEN '+' || regexp_replace(phone, '\D', '', 'g')
       ELSE NULL
   END
 WHERE phone IS NOT NULL
   AND phone !~ '^\+[0-9]{8,15}$';

-- ── 3. the invariant ─────────────────────────────────────────────────────────
-- NULL stays legal (a member may simply have no phone); '' and '   ' do not,
-- which is the point: "no phone" has exactly one representation now.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'members_phone_e164'
           AND conrelid = 'members'::regclass
    ) THEN
        ALTER TABLE members
            ADD CONSTRAINT members_phone_e164
            CHECK (phone IS NULL OR phone ~ '^\+[0-9]{8,15}$') NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'recruits_phone_e164'
           AND conrelid = 'recruits'::regclass
    ) THEN
        ALTER TABLE recruits
            ADD CONSTRAINT recruits_phone_e164
            CHECK (phone IS NULL OR phone ~ '^\+[0-9]{8,15}$') NOT VALID;
    END IF;
END $$;

-- VALIDATE is a no-op once the constraint is already marked valid, so reruns
-- are safe. It must follow the backfill above or it would reject the old rows.
ALTER TABLE members  VALIDATE CONSTRAINT members_phone_e164;
ALTER TABLE recruits VALIDATE CONSTRAINT recruits_phone_e164;

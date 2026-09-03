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
--   1. copies anything the parser cannot recognise into `phone_unparsed`, then
--      backfills members.phone / recruits.phone to E.164, NULLing what is left
--      (an unparseable phone is not a phone, but it is still evidence);
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
-- CORRECTED IN PLACE 2026-09-03 (issue #31). As written, the `ELSE NULL` below
-- permanently erased every number the three parse branches do not recognise —
-- notably any international number stored without a leading '+' ('442079460958',
-- '0044 20 7946 0958') and any typo a human could have repaired. There was no
-- backup column and no report. The quarantine copy into `phone_unparsed` is added
-- ahead of each UPDATE; the E.164 UPDATE itself is unchanged. The edit is in place
-- rather than a follow-up migration because a follow-up runs after the values are
-- already gone. `schema_migrations` stores file names only, so a database that
-- already ran 0149 will not re-run it: any database migrated BEFORE 2026-09-03
-- got the original behaviour, and its wiped values are recoverable only from a
-- PITR snapshot taken before that run (only the demo database is known to be in
-- that state; its data is accepted as-is).
--
-- DRY RUN — before migrating prod, count what the backfill would discard (run for
-- `recruits` too by swapping the table name; `would_null` is the number of rows
-- that will land in phone_unparsed):
--
--   SELECT count(*) FILTER (WHERE CASE
--              WHEN phone ~ '^\s*\+'
--                   AND length(regexp_replace(phone, '\D', '', 'g')) BETWEEN 8 AND 15
--                  THEN '+' || regexp_replace(phone, '\D', '', 'g')
--              WHEN phone !~ '^\s*\+'
--                   AND length(regexp_replace(phone, '\D', '', 'g')) = 10
--                  THEN '+1' || regexp_replace(phone, '\D', '', 'g')
--              WHEN phone !~ '^\s*\+'
--                   AND length(regexp_replace(phone, '\D', '', 'g')) = 11
--                   AND left(regexp_replace(phone, '\D', '', 'g'), 1) = '1'
--                  THEN '+' || regexp_replace(phone, '\D', '', 'g')
--              ELSE NULL
--          END IS NULL) AS would_null,
--          count(*) AS would_touch
--     FROM members
--    WHERE phone IS NOT NULL
--      AND phone !~ '^\+[0-9]{8,15}$';
--
-- Append-only migration rule: this file's own numbering is unchanged and nothing
-- in 0001..0148 is edited.

-- ── 1. backfill members.phone ────────────────────────────────────────────────
-- Rows already in E.164 are skipped by the WHERE, so a rerun is a no-op.

-- Quarantine first: members rows no branch below recognises would otherwise be
-- erased. The predicate is the negation of the three CASE branches (issue #31).

ALTER TABLE members ADD COLUMN IF NOT EXISTS phone_unparsed TEXT;

UPDATE members
   SET phone_unparsed = phone
 WHERE phone IS NOT NULL
   AND phone !~ '^\+[0-9]{8,15}$'
   AND NOT (
       (phone ~ '^\s*\+'  AND length(regexp_replace(phone, '\D', '', 'g')) BETWEEN 8 AND 15)
    OR (phone !~ '^\s*\+' AND length(regexp_replace(phone, '\D', '', 'g')) = 10)
    OR (phone !~ '^\s*\+' AND length(regexp_replace(phone, '\D', '', 'g')) = 11
        AND left(regexp_replace(phone, '\D', '', 'g'), 1) = '1')
   );

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

-- Quarantine first: recruits rows no branch below recognises would otherwise be
-- erased. The predicate is the negation of the three CASE branches (issue #31).

ALTER TABLE recruits ADD COLUMN IF NOT EXISTS phone_unparsed TEXT;

UPDATE recruits
   SET phone_unparsed = phone
 WHERE phone IS NOT NULL
   AND phone !~ '^\+[0-9]{8,15}$'
   AND NOT (
       (phone ~ '^\s*\+'  AND length(regexp_replace(phone, '\D', '', 'g')) BETWEEN 8 AND 15)
    OR (phone !~ '^\s*\+' AND length(regexp_replace(phone, '\D', '', 'g')) = 10)
    OR (phone !~ '^\s*\+' AND length(regexp_replace(phone, '\D', '', 'g')) = 11
        AND left(regexp_replace(phone, '\D', '', 'g'), 1) = '1')
   );

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

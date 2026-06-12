-- Backfill default Treasury grants for existing officers.
--
-- Migration 0006 gave officers these grants at the time it ran. Local reseeding
-- and imported/demo data can create officer rows later, so keep this idempotent
-- backfill as the durable default for current officers.

INSERT INTO treasury_grants (chapter_id, member_id, capability)
SELECT m.chapter_id, m.id, caps.capability
FROM members m
CROSS JOIN (
    VALUES
        ('treasury:read'),
        ('invoice:create'),
        ('payment:review'),
        ('expense:create'),
        ('adjustment:create'),
        ('refund:create'),
        ('rebuild:run')
) AS caps(capability)
WHERE m.role = 'officer'
  AND m.status = 'active'
ON CONFLICT (chapter_id, member_id, capability) DO NOTHING;

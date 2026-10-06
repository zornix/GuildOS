-- D5: event date/time are entered in the chapter's local time. One timezone per chapter.
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'America/Los_Angeles';

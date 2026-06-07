-- Chunk F-partial · Review Queue: supplemental indexes on payment_submissions.
-- Migration range 0060-0069. Idempotent (CREATE INDEX IF NOT EXISTS).
--
-- Indexes on status, member_id, invoice_id already exist from Chunk A (0010).
-- This migration adds the missing ones needed for queue filter performance:
--   - method (payment method filter)
--   - created_at (default sort column for the queue)
--   - composite (chapter_id, status) for the primary queue filter

CREATE INDEX IF NOT EXISTS ix_payment_submissions_method
    ON payment_submissions(method);

CREATE INDEX IF NOT EXISTS ix_payment_submissions_created_at
    ON payment_submissions(created_at);

CREATE INDEX IF NOT EXISTS ix_payment_submissions_chapter_id_status
    ON payment_submissions(chapter_id, status);

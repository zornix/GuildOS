-- Chunk G · Hardening: durable message outbox for exactly-once notifications.
-- Migration range 0070-0079. Idempotent (CREATE TABLE/INDEX IF NOT EXISTS).
--
-- Replaces the no-op notify_* stubs. Each lifecycle notification (invoice issued,
-- payment approved/rejected, refund issued) is enqueued here. A UNIQUE dedup_key
-- makes the enqueue idempotent: a retried operation re-uses the same key and the
-- ON CONFLICT DO NOTHING insert is a no-op, so a message is enqueued exactly once.
--
-- Delivery is gated by MESSAGE_DELIVERY_MODE (dry_run in tests/dev): in dry_run the
-- row stays status='pending' and nothing is sent externally; a real provider would
-- flip pending -> sent. The outbox is append-only-ish: rows are never deleted, only
-- their delivery status advances. This is the standard transactional-outbox pattern.

CREATE TABLE IF NOT EXISTS message_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type TEXT NOT NULL,
    member_id UUID REFERENCES members(id) ON DELETE SET NULL,
    target_table TEXT NOT NULL,
    target_id UUID NOT NULL,
    dedup_key TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending',
    delivery_mode TEXT NOT NULL DEFAULT 'dry_run',
    delivered_at TIMESTAMPTZ,
    CONSTRAINT message_outbox_event_type_check CHECK (
        event_type IN (
            'INVOICE_ISSUED',
            'PAYMENT_APPROVED',
            'PAYMENT_REJECTED',
            'REFUND_ISSUED'
        )
    ),
    CONSTRAINT message_outbox_status_check CHECK (status IN ('pending', 'sent', 'failed'))
);

-- The exactly-once backstop: a retried lifecycle event re-derives the same dedup_key
-- and the conflicting insert is dropped, so at most one row exists per logical event.
CREATE UNIQUE INDEX IF NOT EXISTS uq_message_outbox_dedup_key
    ON message_outbox(dedup_key);

CREATE INDEX IF NOT EXISTS ix_message_outbox_chapter_id ON message_outbox(chapter_id);
CREATE INDEX IF NOT EXISTS ix_message_outbox_status ON message_outbox(status);
CREATE INDEX IF NOT EXISTS ix_message_outbox_target ON message_outbox(target_table, target_id);

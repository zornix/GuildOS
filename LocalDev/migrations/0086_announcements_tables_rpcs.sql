-- Announcements service: drafts + send via the shared message_outbox (0070).
-- Delivery providers stay behind the outbox; nothing is dispatched externally
-- in V1 (MESSAGE_DELIVERY_MODE=dry_run).

CREATE TABLE IF NOT EXISTS announcements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    audience TEXT NOT NULL DEFAULT 'chapter',
    status TEXT NOT NULL DEFAULT 'draft',
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- members_with_balance is the treasury→announcements audience seam (§7).
    CONSTRAINT announcements_audience_check CHECK (
        audience IN ('chapter', 'officers', 'members_with_balance')
    ),
    CONSTRAINT announcements_status_check CHECK (status IN ('draft', 'sent'))
);

CREATE INDEX IF NOT EXISTS ix_announcements_chapter_id ON announcements(chapter_id);
CREATE INDEX IF NOT EXISTS ix_announcements_status ON announcements(status);
CREATE INDEX IF NOT EXISTS ix_announcements_created_at ON announcements(created_at);

ALTER TABLE announcements ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS announcements_select_chapter ON announcements;
CREATE POLICY announcements_select_chapter ON announcements
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());

-- Extend the outbox event catalog additively (0070 defined the treasury set).
ALTER TABLE message_outbox DROP CONSTRAINT IF EXISTS message_outbox_event_type_check;
ALTER TABLE message_outbox ADD CONSTRAINT message_outbox_event_type_check CHECK (
    event_type IN (
        'INVOICE_ISSUED',
        'PAYMENT_APPROVED',
        'PAYMENT_REJECTED',
        'REFUND_ISSUED',
        'ANNOUNCEMENT_PUBLISHED'
    )
);

-- ── RPC: send = flip draft→sent + enqueue outbox row, atomically ─────────────
CREATE OR REPLACE FUNCTION an_send_announcement(
    p_chapter_id UUID,
    p_announcement_id UUID,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_ann announcements%ROWTYPE;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'an_send_announcement' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    SELECT * INTO v_ann FROM announcements
     WHERE id = p_announcement_id AND chapter_id = p_chapter_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'announcement % not found in chapter %', p_announcement_id, p_chapter_id;
    END IF;
    IF v_ann.status = 'sent' THEN
        RETURN to_jsonb(v_ann);  -- idempotent: already sent
    END IF;

    UPDATE announcements SET status = 'sent', sent_at = now(), updated_at = now()
     WHERE id = p_announcement_id
    RETURNING * INTO v_ann;

    -- One outbox row per announcement; per-member audience fan-out happens at
    -- delivery time. TODO(announcements): resolve audience (chapter | officers |
    -- members_with_balance via treasury balances) in the delivery worker.
    INSERT INTO message_outbox (chapter_id, event_type, member_id, target_table, target_id,
                                dedup_key, payload, status)
    VALUES (p_chapter_id, 'ANNOUNCEMENT_PUBLISHED', NULL, 'announcements', v_ann.id,
            'ANNOUNCEMENT_PUBLISHED:' || v_ann.id,
            jsonb_build_object('audience', v_ann.audience, 'title', v_ann.title),
            'pending')
    ON CONFLICT (dedup_key) DO NOTHING;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'SEND_ANNOUNCEMENT', p_actor_id, 'announcements', v_ann.id,
            jsonb_build_object('audience', v_ann.audience));

    v_result := to_jsonb(v_ann);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'an_send_announcement', p_idempotency_key, v_ann.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

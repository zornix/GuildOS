-- Chunk 0 · Treasury foundations: RLS helpers, officer grants, and base RPCs.

CREATE OR REPLACE FUNCTION treasury_claim_sub_uuid()
RETURNS UUID
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    raw_sub TEXT;
BEGIN
    raw_sub := current_setting('request.jwt.claim.sub', true);
    IF raw_sub IS NULL OR raw_sub = '' THEN
        RETURN NULL;
    END IF;
    RETURN raw_sub::UUID;
EXCEPTION
    WHEN invalid_text_representation THEN
        RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION treasury_request_member_id()
RETURNS UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT m.id
    FROM members m
    WHERE m.status = 'active'
      AND (
        m.id = treasury_claim_sub_uuid()
        OR m.auth_id = treasury_claim_sub_uuid()
      )
    LIMIT 1
$$;

CREATE OR REPLACE FUNCTION treasury_has_capability(p_chapter_id UUID, p_capability TEXT)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM treasury_grants g
        WHERE g.chapter_id = p_chapter_id
          AND g.member_id = treasury_request_member_id()
          AND g.capability = p_capability
    )
$$;

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
ON CONFLICT (chapter_id, member_id, capability) DO NOTHING;

ALTER TABLE treasury_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE big_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS treasury_grants_select_self ON treasury_grants;
CREATE POLICY treasury_grants_select_self
    ON treasury_grants
    FOR SELECT
    USING (
        member_id = treasury_request_member_id()
        OR treasury_has_capability(chapter_id, 'treasury:read')
    );

DROP POLICY IF EXISTS big_ledger_select_treasury_read ON big_ledger;
CREATE POLICY big_ledger_select_treasury_read
    ON big_ledger
    FOR SELECT
    USING (treasury_has_capability(chapter_id, 'treasury:read'));

DROP POLICY IF EXISTS audit_logs_select_treasury_read ON audit_logs;
CREATE POLICY audit_logs_select_treasury_read
    ON audit_logs
    FOR SELECT
    USING (treasury_has_capability(chapter_id, 'treasury:read'));

CREATE OR REPLACE FUNCTION tr_test_atomic_rollback(
    p_chapter_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_ledger_id UUID;
BEGIN
    INSERT INTO big_ledger (
        chapter_id,
        entry_type,
        amount_cents,
        member_id,
        source_table,
        source_id,
        status
    )
    VALUES (
        p_chapter_id,
        'ADJUSTMENT_CREATED',
        42,
        NULL,
        'tr_test_atomic_rollback',
        gen_random_uuid(),
        'active'
    )
    RETURNING id INTO v_ledger_id;

    INSERT INTO audit_logs (
        chapter_id,
        action,
        actor_id,
        target_table,
        target_id,
        metadata
    )
    VALUES (
        p_chapter_id,
        'REBUILD',
        NULL,
        'big_ledger',
        v_ledger_id,
        jsonb_build_object('idempotency_key', p_idempotency_key)
    );

    RAISE EXCEPTION 'forced rollback for treasury atomicity test';
END;
$$;

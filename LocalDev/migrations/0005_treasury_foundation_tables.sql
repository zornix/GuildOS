-- Chunk 0 · Treasury foundations: base tables and append-only triggers.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS treasury_grants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    capability TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT treasury_grants_capability_check CHECK (
        capability IN (
            'treasury:read',
            'invoice:create',
            'payment:review',
            'expense:create',
            'adjustment:create',
            'refund:create',
            'rebuild:run'
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_treasury_grants_member_capability
    ON treasury_grants(chapter_id, member_id, capability);
CREATE INDEX IF NOT EXISTS ix_treasury_grants_member_id ON treasury_grants(member_id);
CREATE INDEX IF NOT EXISTS ix_treasury_grants_chapter_id ON treasury_grants(chapter_id);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    operation TEXT NOT NULL,
    key TEXT NOT NULL,
    result_id UUID,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_idempotency_keys_chapter_operation_key
    ON idempotency_keys(chapter_id, operation, key);
CREATE INDEX IF NOT EXISTS ix_idempotency_keys_chapter_id ON idempotency_keys(chapter_id);

CREATE TABLE IF NOT EXISTS big_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    entry_type TEXT NOT NULL,
    amount_cents BIGINT NOT NULL,
    member_id UUID REFERENCES members(id) ON DELETE SET NULL,
    source_table TEXT NOT NULL,
    source_id UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    reverses_entry_id UUID REFERENCES big_ledger(id),
    invalidated_reason TEXT,
    invalidated_by UUID REFERENCES members(id) ON DELETE SET NULL,
    invalidated_at TIMESTAMPTZ,
    CONSTRAINT big_ledger_entry_type_check CHECK (
        entry_type IN (
            'INVOICE_CREATED',
            'PAYMENT_RECEIVED',
            'EXPENSE_APPROVED',
            'EXPENSE_REVERSED',
            'ADJUSTMENT_CREATED',
            'REFUND_ISSUED',
            'CANCEL_INVOICE'
        )
    ),
    CONSTRAINT big_ledger_status_check CHECK (status IN ('active', 'invalidated'))
);

CREATE INDEX IF NOT EXISTS ix_big_ledger_chapter_id ON big_ledger(chapter_id);
CREATE INDEX IF NOT EXISTS ix_big_ledger_member_id ON big_ledger(member_id);
CREATE INDEX IF NOT EXISTS ix_big_ledger_source ON big_ledger(source_table, source_id);
CREATE INDEX IF NOT EXISTS ix_big_ledger_created_at ON big_ledger(created_at);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    action TEXT NOT NULL,
    actor_id UUID REFERENCES members(id) ON DELETE SET NULL,
    target_table TEXT NOT NULL,
    target_id UUID NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT audit_logs_action_check CHECK (
        action IN (
            'CREATE_INVOICE',
            'VERIFY_PAYMENT',
            'REJECT_PAYMENT',
            'CREATE_EXPENSE',
            'INVALIDATE_EXPENSE',
            'CREATE_ADJUSTMENT',
            'CANCEL_INVOICE',
            'ISSUE_REFUND',
            'REBUILD'
        )
    )
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_chapter_id ON audit_logs(chapter_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_id ON audit_logs(actor_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_target ON audit_logs(target_table, target_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs(created_at);

CREATE OR REPLACE FUNCTION tr_block_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'hard deletes are forbidden on %', TG_TABLE_NAME;
END;
$$;

CREATE OR REPLACE FUNCTION tr_enforce_big_ledger_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status = 'active'
       AND NEW.status = 'invalidated'
       AND NEW.id IS NOT DISTINCT FROM OLD.id
       AND NEW.chapter_id IS NOT DISTINCT FROM OLD.chapter_id
       AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
       AND NEW.entry_type IS NOT DISTINCT FROM OLD.entry_type
       AND NEW.amount_cents IS NOT DISTINCT FROM OLD.amount_cents
       AND NEW.member_id IS NOT DISTINCT FROM OLD.member_id
       AND NEW.source_table IS NOT DISTINCT FROM OLD.source_table
       AND NEW.source_id IS NOT DISTINCT FROM OLD.source_id
       AND NEW.reverses_entry_id IS NOT DISTINCT FROM OLD.reverses_entry_id
    THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'big_ledger is append-only; only status active -> invalidated is allowed';
END;
$$;

CREATE OR REPLACE FUNCTION tr_block_audit_log_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs are append-only';
END;
$$;

DROP TRIGGER IF EXISTS big_ledger_no_delete ON big_ledger;
CREATE TRIGGER big_ledger_no_delete
    BEFORE DELETE ON big_ledger
    FOR EACH ROW EXECUTE FUNCTION tr_block_delete();

DROP TRIGGER IF EXISTS big_ledger_limited_update ON big_ledger;
CREATE TRIGGER big_ledger_limited_update
    BEFORE UPDATE ON big_ledger
    FOR EACH ROW EXECUTE FUNCTION tr_enforce_big_ledger_update();

DROP TRIGGER IF EXISTS audit_logs_immutable ON audit_logs;
CREATE TRIGGER audit_logs_immutable
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION tr_block_audit_log_mutation();

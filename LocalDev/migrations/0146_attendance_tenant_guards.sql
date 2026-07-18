-- Tenant guards for the legacy attendance surface (imp-tenant-guards.md).
--
-- The 0001 tables attendance/excuses/checkin_links predate chapter_id + RLS and
-- carried no tenant invariant, so the two mutation endpoints (manual_checkin,
-- review_excuse) accepted foreign UUIDs and could write across chapters. This
-- migration:
--   1. adds chapter_id (derived from the row's event, never trusted) + RLS to
--      the three tables, mirroring 0084;
--   2. extends the frozen audit_logs action catalog (dual-format, pattern 0100);
--   3. moves both mutations behind at_* plpgsql RPCs with tenant guards,
--      idempotency, and audit_logs writes (template: tk_commit_task, 0142);
--   4. restores the "approved excuse voids the fine" behavior against the
--      invoice model (tr_void_invoice, 0122) that replaced the frozen `fines`
--      table.
-- Append-only migration rule: new file, nothing in 0001..0145 is edited.

-- ── 1. chapter_id + derive trigger + RLS on the three legacy tables ───────────

ALTER TABLE attendance    ADD COLUMN IF NOT EXISTS chapter_id UUID REFERENCES chapters(id);
ALTER TABLE excuses       ADD COLUMN IF NOT EXISTS chapter_id UUID REFERENCES chapters(id);
ALTER TABLE checkin_links ADD COLUMN IF NOT EXISTS chapter_id UUID REFERENCES chapters(id);

-- Backfill from the event each row hangs off (event_id is NOT NULL on all three).
UPDATE attendance    t SET chapter_id = e.chapter_id FROM events e WHERE t.event_id = e.id AND t.chapter_id IS NULL;
UPDATE excuses       t SET chapter_id = e.chapter_id FROM events e WHERE t.event_id = e.id AND t.chapter_id IS NULL;
UPDATE checkin_links t SET chapter_id = e.chapter_id FROM events e WHERE t.event_id = e.id AND t.chapter_id IS NULL;

ALTER TABLE attendance    ALTER COLUMN chapter_id SET NOT NULL;
ALTER TABLE excuses       ALTER COLUMN chapter_id SET NOT NULL;
ALTER TABLE checkin_links ALTER COLUMN chapter_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_attendance_chapter_id    ON attendance(chapter_id);
CREATE INDEX IF NOT EXISTS ix_excuses_chapter_id       ON excuses(chapter_id);
CREATE INDEX IF NOT EXISTS ix_checkin_links_chapter_id ON checkin_links(chapter_id);

-- The column can never disagree with the event it hangs off: on INSERT/UPDATE we
-- derive chapter_id from the row's event when NULL, and RAISE on any mismatch.
-- Existing Python insert paths (link check-in, excuse submission) pass no
-- chapter_id and keep working unchanged.
CREATE OR REPLACE FUNCTION at_derive_chapter_id() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    v_event_chapter UUID;
BEGIN
    SELECT chapter_id INTO v_event_chapter FROM events WHERE id = NEW.event_id;
    IF v_event_chapter IS NULL THEN
        RAISE EXCEPTION 'event % not found for % row', NEW.event_id, TG_TABLE_NAME;
    END IF;
    IF NEW.chapter_id IS NULL THEN
        NEW.chapter_id := v_event_chapter;
    ELSIF NEW.chapter_id <> v_event_chapter THEN
        RAISE EXCEPTION 'chapter_id % does not match event chapter % on % row',
            NEW.chapter_id, v_event_chapter, TG_TABLE_NAME;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_attendance_derive_chapter    ON attendance;
DROP TRIGGER IF EXISTS trg_excuses_derive_chapter        ON excuses;
DROP TRIGGER IF EXISTS trg_checkin_links_derive_chapter  ON checkin_links;

CREATE TRIGGER trg_attendance_derive_chapter
    BEFORE INSERT OR UPDATE ON attendance
    FOR EACH ROW EXECUTE FUNCTION at_derive_chapter_id();
CREATE TRIGGER trg_excuses_derive_chapter
    BEFORE INSERT OR UPDATE ON excuses
    FOR EACH ROW EXECUTE FUNCTION at_derive_chapter_id();
CREATE TRIGGER trg_checkin_links_derive_chapter
    BEFORE INSERT OR UPDATE ON checkin_links
    FOR EACH ROW EXECUTE FUNCTION at_derive_chapter_id();

-- RLS: schema parity with the other 24 tenant tables (mirrors 0084). Per ADR-0002
-- the runtime psycopg/service-role path bypasses RLS; the enforcement layer for
-- these mutations is the at_* RPCs below, with RLS as defense-in-depth.
ALTER TABLE attendance    ENABLE ROW LEVEL SECURITY;
ALTER TABLE excuses       ENABLE ROW LEVEL SECURITY;
ALTER TABLE checkin_links ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS attendance_select_chapter ON attendance;
CREATE POLICY attendance_select_chapter ON attendance
    FOR SELECT USING (chapter_id = rbac_request_chapter_id());

DROP POLICY IF EXISTS excuses_select_chapter ON excuses;
CREATE POLICY excuses_select_chapter ON excuses
    FOR SELECT USING (chapter_id = rbac_request_chapter_id());

DROP POLICY IF EXISTS checkin_links_select_chapter ON checkin_links;
CREATE POLICY checkin_links_select_chapter ON checkin_links
    FOR SELECT USING (chapter_id = rbac_request_chapter_id());

-- ── 2. audit_logs action catalog extension (dual-format, pattern: 0100) ───────

DO $$
DECLARE
    v_def TEXT;
    v_match TEXT[];
    v_actions TEXT[] := ARRAY[]::TEXT[];
    v_elem TEXT;
    v_list TEXT;
    v_new TEXT[] := ARRAY['ATTENDANCE_OVERRIDDEN', 'EXCUSE_REVIEWED'];
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conrelid = 'audit_logs'::regclass AND conname = 'audit_logs_action_check';

    IF v_def IS NOT NULL THEN
        v_match := regexp_match(v_def, 'ARRAY\[(.+?)\]');
        IF v_match IS NOT NULL THEN
            FOREACH v_elem IN ARRAY string_to_array(v_match[1], ',') LOOP
                v_elem := trim(both '''' from regexp_replace(trim(v_elem), '::text$', ''));
                v_actions := v_actions || v_elem;
            END LOOP;
        ELSE
            v_match := regexp_match(v_def, '''(\{.+?\})''::text\[\]');
            IF v_match IS NOT NULL THEN
                v_actions := v_match[1]::text[];
            END IF;
        END IF;
    END IF;

    FOREACH v_elem IN ARRAY v_new LOOP
        IF NOT (v_elem = ANY (v_actions)) THEN
            v_actions := v_actions || v_elem;
        END IF;
    END LOOP;

    SELECT string_agg(quote_literal(a), ', ') INTO v_list FROM unnest(v_actions) AS a;

    EXECUTE 'ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_check';
    EXECUTE 'ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_action_check '
         || 'CHECK (action = ANY (ARRAY[' || v_list || ']::text[]))';
END $$;

-- ── 3. at_set_attendance — officer overrides a member's attendance ────────────
-- Replaces manual_checkin. Validates the event, member, and actor all belong to
-- p_chapter_id, then reproduces the three handler branches atomically.

CREATE OR REPLACE FUNCTION at_set_attendance(
    p_chapter_id UUID,
    p_event_id UUID,
    p_member_id UUID,
    p_status TEXT,
    p_reason TEXT,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_attendance_id UUID;
    v_result JSONB;
    v_now TIMESTAMPTZ := now();
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'at_set_attendance' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM events WHERE id = p_event_id AND chapter_id = p_chapter_id) THEN
        RAISE EXCEPTION 'event % not found in chapter %', p_event_id, p_chapter_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM members
                    WHERE id = p_member_id AND chapter_id = p_chapter_id AND status = 'active') THEN
        RAISE EXCEPTION 'member % not found in chapter %', p_member_id, p_chapter_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM members
                    WHERE id = p_actor_id AND chapter_id = p_chapter_id AND status = 'active') THEN
        RAISE EXCEPTION 'actor % is not an active member of chapter %', p_actor_id, p_chapter_id;
    END IF;

    IF p_status = 'excused' THEN
        IF p_reason IS NULL OR btrim(p_reason) = '' THEN
            RAISE EXCEPTION 'excuse reason is required when marking as excused';
        END IF;

        INSERT INTO attendance (chapter_id, event_id, member_id, checked_in, checked_in_at, method)
        VALUES (p_chapter_id, p_event_id, p_member_id, FALSE, NULL, 'manual')
        ON CONFLICT (event_id, member_id) DO UPDATE
            SET checked_in = FALSE, checked_in_at = NULL, method = 'manual'
        RETURNING id INTO v_attendance_id;

        -- Replace any existing excuse with an approved one stamped by the actor.
        DELETE FROM excuses WHERE event_id = p_event_id AND member_id = p_member_id;
        INSERT INTO excuses (chapter_id, event_id, member_id, reason, status,
                             reviewed_by, reviewed_at, submitted_at)
        VALUES (p_chapter_id, p_event_id, p_member_id, btrim(p_reason), 'approved',
                p_actor_id, v_now, v_now);

        v_result := jsonb_build_object('status', 'excused', 'method', 'manual');

    ELSIF p_status = 'absent' THEN
        INSERT INTO attendance (chapter_id, event_id, member_id, checked_in, checked_in_at, method)
        VALUES (p_chapter_id, p_event_id, p_member_id, FALSE, NULL, 'manual')
        ON CONFLICT (event_id, member_id) DO UPDATE
            SET checked_in = FALSE, checked_in_at = NULL, method = 'manual'
        RETURNING id INTO v_attendance_id;

        DELETE FROM excuses WHERE event_id = p_event_id AND member_id = p_member_id;

        v_result := jsonb_build_object('status', 'absent', 'method', 'manual');

    ELSE
        -- present (any status that is not excused/absent, matching the handler's else)
        INSERT INTO attendance (chapter_id, event_id, member_id, checked_in, checked_in_at, method)
        VALUES (p_chapter_id, p_event_id, p_member_id, TRUE, v_now, 'manual')
        ON CONFLICT (event_id, member_id) DO UPDATE
            SET checked_in = TRUE, checked_in_at = v_now, method = 'manual'
        RETURNING id INTO v_attendance_id;

        v_result := jsonb_build_object('status', 'checked_in', 'method', 'manual');
    END IF;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'ATTENDANCE_OVERRIDDEN', p_actor_id, 'attendance', v_attendance_id,
            jsonb_build_object('status', p_status, 'event_id', p_event_id, 'member_id', p_member_id));

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'at_set_attendance', p_idempotency_key, v_attendance_id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- ── 4. at_review_excuse — officer approves/denies an excuse ───────────────────
-- Replaces review_excuse. The excuse is located by joining to its event and is
-- only visible when the event's chapter matches p_chapter_id. On approval, any
-- matching UNPAID fine invoice is voided via tr_void_invoice (D3) — this restores
-- the documented "approving an excuse waives the fine" behavior against the
-- invoice model that replaced the frozen `fines` table. Paid invoices are never
-- touched (refunds stay a human treasury action).

CREATE OR REPLACE FUNCTION at_review_excuse(
    p_chapter_id UUID,
    p_excuse_id UUID,
    p_status TEXT,
    p_actor_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_excuse excuses%ROWTYPE;
    v_invoice_id UUID;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id AND operation = 'at_review_excuse' AND key = p_idempotency_key;
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF p_status NOT IN ('approved', 'denied') THEN
        RAISE EXCEPTION 'status must be approved or denied';
    END IF;

    SELECT e.* INTO v_excuse
      FROM excuses e
      JOIN events ev ON ev.id = e.event_id
     WHERE e.id = p_excuse_id AND ev.chapter_id = p_chapter_id
     FOR UPDATE OF e;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'excuse % not found in chapter %', p_excuse_id, p_chapter_id;
    END IF;

    UPDATE excuses
       SET status = p_status, reviewed_by = p_actor_id, reviewed_at = now()
     WHERE id = p_excuse_id
    RETURNING * INTO v_excuse;

    IF p_status = 'approved' THEN
        SELECT id INTO v_invoice_id FROM unpaid_invoices
         WHERE chapter_id = p_chapter_id
           AND kind = 'fine'
           AND source_event_id = v_excuse.event_id
           AND member_id = v_excuse.member_id
           AND status = 'unpaid'
         LIMIT 1;
        IF v_invoice_id IS NOT NULL THEN
            PERFORM tr_void_invoice(p_chapter_id, v_invoice_id, p_actor_id, 'excuse approved', NULL);
        END IF;
    END IF;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'EXCUSE_REVIEWED', p_actor_id, 'excuses', v_excuse.id,
            jsonb_build_object('decision', p_status,
                               'event_id', v_excuse.event_id,
                               'member_id', v_excuse.member_id));

    v_result := to_jsonb(v_excuse);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'at_review_excuse', p_idempotency_key, v_excuse.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

-- Recruitment stage changes behind an rc_* RPC (Tier-5 checklist item).
--
-- `recruits.stage` was mutated by a bare chapter-scoped UPDATE in
-- api/recruitment/services/pipeline.py, so a PNM could be advanced to
-- 'bid_extended' with no audit trail — even though 0082 has registered the
-- UPDATE_RECRUIT_STAGE audit action since the RBAC foundation landed. No rc_*
-- plpgsql function existed in any migration, which is why the service had a
-- standing TODO instead of a call_rpc.
--
-- This migration adds the missing function, modelled on the at_* guards in
-- 0146 (template: tk_commit_task, 0142): tenant guard on the recruit and the
-- actor, idempotency_keys replay, and one audit_logs row per stage change.
-- Append-only migration rule: new file, nothing in 0001..0150 is edited.

-- ── 1. audit action catalog (re-assert only; 0082 already registers it) ───────
-- UPDATE_RECRUIT_STAGE has been in the catalog since 0082, but the constraint
-- is rebuilt by regex-parsing its own definition (pattern 0100, most recently
-- in 0146), so a drifted database could have lost it. This block is the same
-- dual-format rebuild and is a no-op when the action is already present.

DO $$
DECLARE
    v_def TEXT;
    v_match TEXT[];
    v_actions TEXT[] := ARRAY[]::TEXT[];
    v_elem TEXT;
    v_list TEXT;
    v_new TEXT[] := ARRAY['UPDATE_RECRUIT_STAGE'];
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

-- ── 2. rc_update_recruit_stage — officer advances a recruit's stage ──────────
-- Replaces the Python UPDATE. The recruit is only visible when it belongs to
-- p_chapter_id, the stage is validated against the same list as the 0087
-- recruits_stage_check constraint (a bad stage must fail as an RPC exception
-- the API can map to 422, not as a raw constraint violation), and the change
-- is recorded in audit_logs. Returns the updated recruit row plus the
-- old/new stage so callers keep the row shape the bare UPDATE returned.

CREATE OR REPLACE FUNCTION rc_update_recruit_stage(
    p_chapter_id UUID,
    p_recruit_id UUID,
    p_stage TEXT,
    p_actor_member_id UUID,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing JSONB;
    v_recruit recruits%ROWTYPE;
    v_old_stage TEXT;
    v_result JSONB;
BEGIN
    IF p_idempotency_key IS NOT NULL THEN
        SELECT result INTO v_existing FROM idempotency_keys
         WHERE chapter_id = p_chapter_id
           AND operation = 'rc_update_recruit_stage'
           AND key = p_idempotency_key;
        -- Replay returns the first result verbatim: no second UPDATE, and no
        -- second audit_logs row for one logical stage change.
        IF FOUND THEN RETURN v_existing; END IF;
    END IF;

    IF p_stage IS NULL OR p_stage NOT IN
       ('lead', 'contacted', 'attended_event', 'bid_extended', 'bid_accepted', 'dropped') THEN
        RAISE EXCEPTION 'invalid recruit stage %', coalesce(p_stage, '(null)');
    END IF;

    SELECT * INTO v_recruit
      FROM recruits
     WHERE id = p_recruit_id AND chapter_id = p_chapter_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'recruit % not found in chapter %', p_recruit_id, p_chapter_id;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM members
                    WHERE id = p_actor_member_id AND chapter_id = p_chapter_id AND status = 'active') THEN
        RAISE EXCEPTION 'actor % is not an active member of chapter %', p_actor_member_id, p_chapter_id;
    END IF;

    v_old_stage := v_recruit.stage;

    UPDATE recruits
       SET stage = p_stage, updated_at = now()
     WHERE id = p_recruit_id AND chapter_id = p_chapter_id
    RETURNING * INTO v_recruit;

    INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
    VALUES (p_chapter_id, 'UPDATE_RECRUIT_STAGE', p_actor_member_id, 'recruits', v_recruit.id,
            jsonb_build_object('old_stage', v_old_stage, 'new_stage', p_stage));

    v_result := to_jsonb(v_recruit)
             || jsonb_build_object('old_stage', v_old_stage, 'new_stage', p_stage);

    IF p_idempotency_key IS NOT NULL THEN
        INSERT INTO idempotency_keys (chapter_id, operation, key, result_id, result)
        VALUES (p_chapter_id, 'rc_update_recruit_stage', p_idempotency_key, v_recruit.id, v_result);
    END IF;

    RETURN v_result;
END;
$$;

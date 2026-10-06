-- F-006: roster import writes members.role = officer only for a real officer.
-- admin and president cannot be handed out by a CSV (that bypasses the admin tier).

CREATE OR REPLACE FUNCTION ch_import_roster(
    p_chapter_id UUID,
    p_rows       JSONB   -- [{name, email, phone, role_key|null, sms_consent|null}, ...]
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_row     JSONB;
    v_id      UUID;
    v_created JSONB := '[]'::jsonb;
BEGIN
    FOR v_row IN SELECT * FROM jsonb_array_elements(p_rows)
    LOOP
        IF v_row->>'role_key' IN ('admin', 'president') THEN
            RAISE EXCEPTION 'rbac_ceiling: top roles cannot be set by roster import';
        END IF;

        INSERT INTO members (chapter_id, name, email, phone, role, status, sms_consent_at)
        VALUES (
            p_chapter_id,
            v_row->>'name',
            lower(v_row->>'email'),
            v_row->>'phone',
            -- members.role is the two-value legacy column; the real grant is
            -- the member_roles row below.
            CASE WHEN v_row->>'role_key' = 'officer' THEN 'officer' ELSE 'member' END,
            'invited',
            -- Absent or false stays NULL: silence is never consent.
            CASE WHEN (v_row->>'sms_consent')::boolean THEN now() END
        )
        RETURNING id INTO v_id;

        IF v_row->>'role_key' IS NOT NULL THEN
            INSERT INTO member_roles (chapter_id, member_id, role_key)
            VALUES (p_chapter_id, v_id, v_row->>'role_key')
            ON CONFLICT DO NOTHING;
        END IF;

        v_created := v_created || jsonb_build_object(
            'member_id', v_id,
            'email',     lower(v_row->>'email')
        );
    END LOOP;

    RETURN v_created;
END;
$$;

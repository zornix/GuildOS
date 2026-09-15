-- Chapter onboarding (#74) — the two multi-row writes behind POST /api/chapters
-- and POST /api/chapters/{id}/roster.
--
-- Both are trust-boundary mutations that must not half-apply, so they are
-- plpgsql (CLAUDE.md hard rule) rather than a loop of client inserts:
--   * ch_create_chapter  — chapters + first officer + member_roles, or nothing.
--     Same three rows scripts/provision_chapter.py writes, which keeps working.
--   * ch_import_roster   — every CSV row or none. The API validates the whole
--     file first, so the only thing this transaction protects against is a
--     mid-file database error (a racing insert on the global members.email
--     unique index).
--
-- No audit_logs row: the action CHECK is frozen (CLAUDE.md) and has no value
-- for "chapter created" / "member invited". POST /api/auth/invite sets the
-- precedent — member creation is not audited today.
--
-- Setup codes are NOT issued here. They need a bcrypt hash, which only Python
-- has; the API issues them right after with the same _issue_setup_code() the
-- invite endpoint uses.

CREATE OR REPLACE FUNCTION ch_create_chapter(
    p_name          TEXT,
    p_organization  TEXT,
    p_school        TEXT,
    p_officer_name  TEXT,
    p_officer_email TEXT,
    p_officer_phone TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_chapter_id UUID;
    v_member_id  UUID;
BEGIN
    -- Never upsert: an existing chapter or member is a 409, not a merge.
    IF EXISTS (SELECT 1 FROM chapters WHERE lower(name) = lower(p_name)) THEN
        RAISE EXCEPTION 'chapter_name_taken';
    END IF;
    IF EXISTS (SELECT 1 FROM members WHERE lower(email) = lower(p_officer_email)) THEN
        RAISE EXCEPTION 'officer_email_taken';
    END IF;

    INSERT INTO chapters (name, organization, school)
    VALUES (p_name, p_organization, p_school)
    RETURNING id INTO v_chapter_id;

    -- status='invited', no password_hash: the officer claims the account by
    -- redeeming the setup code, so knowing the address is not enough to take it.
    INSERT INTO members (chapter_id, name, email, phone, role, status)
    VALUES (v_chapter_id, p_officer_name, lower(p_officer_email), p_officer_phone,
            'officer', 'invited')
    RETURNING id INTO v_member_id;

    -- Mirror into RBAC when the catalog is present (provision_chapter.py skips
    -- it on databases that predate 0083; same tolerance here).
    INSERT INTO member_roles (chapter_id, member_id, role_key)
    SELECT v_chapter_id, v_member_id, 'officer'
     WHERE EXISTS (SELECT 1 FROM roles WHERE key = 'officer')
    ON CONFLICT DO NOTHING;

    RETURN jsonb_build_object(
        'chapter_id',    v_chapter_id,
        'officer_id',    v_member_id,
        'officer_email', lower(p_officer_email)
    );
END;
$$;


CREATE OR REPLACE FUNCTION ch_import_roster(
    p_chapter_id UUID,
    p_rows       JSONB   -- [{name, email, phone, role_key|null}, ...]
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
        INSERT INTO members (chapter_id, name, email, phone, role, status)
        VALUES (
            p_chapter_id,
            v_row->>'name',
            lower(v_row->>'email'),
            v_row->>'phone',
            -- members.role is the two-value legacy column; the real grant is
            -- the member_roles row below.
            CASE WHEN v_row->>'role_key' = 'member' OR v_row->>'role_key' IS NULL
                 THEN 'member' ELSE 'officer' END,
            'invited'
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


-- Same exposure rule as every other RPC (0153): backend connection only.
REVOKE ALL ON FUNCTION ch_create_chapter(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION ch_import_roster(UUID, JSONB) FROM PUBLIC;

DO $$
DECLARE
    v_roles TEXT;
    v_fn    TEXT;
BEGIN
    SELECT string_agg(quote_ident(rolname), ', ')
      INTO v_roles
      FROM pg_roles
     WHERE rolname IN ('anon', 'authenticated');

    IF v_roles IS NULL THEN
        RETURN;
    END IF;

    FOREACH v_fn IN ARRAY ARRAY[
        'ch_create_chapter(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT)',
        'ch_import_roster(UUID, JSONB)'
    ]
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %s', v_fn, v_roles);
    END LOOP;
END
$$;

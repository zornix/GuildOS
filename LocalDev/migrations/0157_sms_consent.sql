-- SMS consent and opt-out (#57, follows the #54 delivery decision).
--
-- Twilio (and the carriers) require prior express consent before an application
-- texts a person, and an honored opt-out afterwards. Two nullable timestamps on
-- `members` carry both facts — no new table, because consent is one attribute of
-- a member, not a history we query:
--
--     consented  ==  sms_consent_at IS NOT NULL AND sms_opted_out_at IS NULL
--
-- Both are timestamps rather than booleans so the record answers "when, and is
-- it still current", which is what a carrier complaint asks.
--
-- Everything already in the table is NULL = no consent on file. That is the
-- honest state: the roster import that created those rows never asked.

ALTER TABLE members
    ADD COLUMN IF NOT EXISTS sms_consent_at   TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS sms_opted_out_at TIMESTAMPTZ NULL;

COMMENT ON COLUMN members.sms_consent_at IS
    'When this member gave express consent to receive SMS. NULL = never asked.';
COMMENT ON COLUMN members.sms_opted_out_at IS
    'When this member last replied STOP (or opted out in-app). Overrides consent.';


-- ch_import_roster gains an optional per-row `sms_consent` flag: the roster CSV
-- may carry a `consent` column recording the signed opt-in the chapter collected
-- before import. Same signature as 0156, so the REVOKEs there still apply.
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
        INSERT INTO members (chapter_id, name, email, phone, role, status, sms_consent_at)
        VALUES (
            p_chapter_id,
            v_row->>'name',
            lower(v_row->>'email'),
            v_row->>'phone',
            -- members.role is the two-value legacy column; the real grant is
            -- the member_roles row below.
            CASE WHEN v_row->>'role_key' = 'member' OR v_row->>'role_key' IS NULL
                 THEN 'member' ELSE 'officer' END,
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

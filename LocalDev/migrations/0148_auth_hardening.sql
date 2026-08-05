-- Auth hardening — imp-one-gate.md D2 ("everyone uses a password", 2026-07-11)
-- plus the invite-claim hole and the session-revocation gap found alongside it.
--
--   1. members.token_version — server-side session revocation. Member tokens now
--      carry a "ver" claim and api/dependencies.py rejects any token whose ver
--      disagrees with the member row, so setting a password or issuing a reset
--      code invalidates every outstanding session for that member.
--   2. members.status gains 'invited'. Invitees are created not-yet-active and
--      /login filters on status='active', so an unclaimed invite can no longer
--      be claimed by whoever knows the email first — the exposure imp-one-gate.md
--      D2 explicitly flagged as a follow-up for the invite flow.
--   3. member_setup_codes — single-use, bcrypt-hashed, 7-day codes. Backs both
--      the invite claim path and the officer-assisted password reset.
--   4. login_attempts — sliding-window rate limiting for /login and
--      /redeem-setup-code, which are the two unauthenticated surfaces.
--   5. au_* RPCs for the three mutations the psycopg shim (api/postgres_client.py)
--      cannot express atomically: it has no expression updates (token_version =
--      token_version + 1) and no IS NULL filter (the single-use code claim).
--      Trust-boundary mutations go through plpgsql per CLAUDE.md.
--
-- Append-only migration rule: new file, nothing in 0001..0147 is edited.

-- ── 1. members.token_version ─────────────────────────────────────────────────

ALTER TABLE members ADD COLUMN IF NOT EXISTS token_version INT NOT NULL DEFAULT 0;

COMMENT ON COLUMN members.token_version IS
    'Session epoch. Bumped by au_set_password / au_bump_token_version; tokens '
    'carrying a stale "ver" claim are rejected by get_current_user.';

-- ── 2. members.status catalog gains ''invited'' ───────────────────────────────
-- Dynamic drop/re-add (pattern: 0131) so the rebuild preserves any value another
-- migration may have added and stays idempotent on re-run.

DO $$
DECLARE
    v_def  TEXT;
    v_vals TEXT[];
    v_list TEXT;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_def
      FROM pg_constraint
     WHERE conrelid = 'members'::regclass
       AND conname = 'members_status_check';

    IF v_def IS NULL THEN
        -- Baseline from 0001.
        v_vals := ARRAY['active', 'inactive', 'alumni'];
    ELSE
        SELECT array_agg(DISTINCT m[1]) INTO v_vals
          FROM regexp_matches(v_def, '''([^'']+)''', 'g') AS m;
    END IF;

    IF NOT ('invited' = ANY (v_vals)) THEN
        v_vals := array_append(v_vals, 'invited');
    END IF;

    SELECT string_agg(quote_literal(v), ', ') INTO v_list FROM unnest(v_vals) AS v;

    EXECUTE 'ALTER TABLE members DROP CONSTRAINT IF EXISTS members_status_check';
    EXECUTE format(
        'ALTER TABLE members ADD CONSTRAINT members_status_check CHECK (status IN (%s))',
        v_list
    );
END $$;

-- ── 3. member_setup_codes ────────────────────────────────────────────────────
-- Only the bcrypt hash is stored; the plaintext is returned to the issuing
-- officer exactly once and handed to the member out of band.

CREATE TABLE IF NOT EXISTS member_setup_codes (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    member_id  UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    code_hash  TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_member_setup_codes_member_id ON member_setup_codes(member_id);
CREATE INDEX IF NOT EXISTS ix_member_setup_codes_chapter_id ON member_setup_codes(chapter_id);

-- RLS: schema parity with the other tenant tables (mirrors 0084/0146). Per
-- ADR-0002 the runtime psycopg/service-role path bypasses RLS; the enforcement
-- layer here is au_consume_setup_code's chapter guard, with RLS as
-- defense-in-depth for any non-privileged access.
ALTER TABLE member_setup_codes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS member_setup_codes_select_chapter ON member_setup_codes;
CREATE POLICY member_setup_codes_select_chapter ON member_setup_codes
    FOR SELECT USING (chapter_id = rbac_request_chapter_id());

-- ── 4. login_attempts ────────────────────────────────────────────────────────
-- Deliberately carries no chapter_id: attempts are recorded for emails that may
-- match no member at all, so there is no tenant to scope a row to. RLS is
-- enabled with no policy, i.e. deny-all for every non-privileged role — this is
-- a security log, not chapter-visible data.

CREATE TABLE IF NOT EXISTS login_attempts (
    id         BIGSERIAL PRIMARY KEY,
    email      TEXT NOT NULL,
    ip         TEXT,
    success    BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_login_attempts_email_created ON login_attempts(email, created_at);
CREATE INDEX IF NOT EXISTS ix_login_attempts_ip_created    ON login_attempts(ip, created_at);

ALTER TABLE login_attempts ENABLE ROW LEVEL SECURITY;

-- ── 5. au_set_password ───────────────────────────────────────────────────────
-- Password write + session epoch bump in one statement, so a caller can never
-- observe a new password with an old token_version. No p_chapter_id: the subject
-- is the authenticated caller's own account (identified by an already verified
-- token) and no cross-row reference is dereferenced.

CREATE OR REPLACE FUNCTION au_set_password(
    p_member_id UUID,
    p_password_hash TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_version INT;
BEGIN
    UPDATE members
       SET password_hash = p_password_hash,
           token_version = token_version + 1
     WHERE id = p_member_id
    RETURNING token_version INTO v_version;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'member % not found', p_member_id;
    END IF;

    RETURN jsonb_build_object('member_id', p_member_id, 'token_version', v_version);
END;
$$;

-- ── 6. au_bump_token_version ─────────────────────────────────────────────────
-- Revokes every outstanding session for a member. Tenant-guarded: the officer
-- issuing a reset code may only touch members of their own chapter.

CREATE OR REPLACE FUNCTION au_bump_token_version(
    p_chapter_id UUID,
    p_member_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_version INT;
BEGIN
    UPDATE members
       SET token_version = token_version + 1
     WHERE id = p_member_id AND chapter_id = p_chapter_id
    RETURNING token_version INTO v_version;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'member % not found in chapter %', p_member_id, p_chapter_id;
    END IF;

    RETURN jsonb_build_object('member_id', p_member_id, 'token_version', v_version);
END;
$$;

-- ── 7. au_consume_setup_code ─────────────────────────────────────────────────
-- Single-use claim. The conditional UPDATE is the concurrency control: only one
-- caller can move used_at from NULL, so a replayed or raced code loses. Claiming
-- also completes the invite by flipping 'invited' → 'active'. Never raises on a
-- lost race — the caller maps claimed=false onto the same generic 401 as every
-- other redeem failure, so the endpoint reveals nothing.

CREATE OR REPLACE FUNCTION au_consume_setup_code(
    p_chapter_id UUID,
    p_code_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_member_id UUID;
BEGIN
    UPDATE member_setup_codes
       SET used_at = now()
     WHERE id = p_code_id
       AND chapter_id = p_chapter_id
       AND used_at IS NULL
       AND expires_at > now()
    RETURNING member_id INTO v_member_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('claimed', false, 'member_id', NULL);
    END IF;

    UPDATE members
       SET status = 'active'
     WHERE id = v_member_id
       AND chapter_id = p_chapter_id
       AND status = 'invited';

    RETURN jsonb_build_object('claimed', true, 'member_id', v_member_id);
END;
$$;

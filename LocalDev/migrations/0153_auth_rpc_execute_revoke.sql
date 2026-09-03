-- Issue #25 — auth RPCs were executable by PUBLIC.
--
-- A fresh Postgres function is created with EXECUTE granted to PUBLIC, and no
-- migration in 0001–0152 ever revoked it. On a Supabase project that is only
-- latent while the Data API is off; the moment it is on, the public anon key can
-- POST /rest/v1/rpc/au_set_password with any p_member_id and take over that
-- account (au_bump_token_version and au_consume_setup_code take p_chapter_id
-- from the caller, so their "tenant guard" is attacker-supplied too).
--
-- The backend is unaffected: it connects as the owning role over the pooler
-- (ADR-0002), and an owner keeps EXECUTE on its own functions regardless of what
-- is revoked from PUBLIC.

-- ── 1. The three auth RPCs from 0148, named explicitly ───────────────────────

REVOKE ALL ON FUNCTION au_set_password(UUID, TEXT)       FROM PUBLIC;
REVOKE ALL ON FUNCTION au_bump_token_version(UUID, UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION au_consume_setup_code(UUID, UUID) FROM PUBLIC;

-- Supabase pre-grants EXECUTE on public functions to anon/authenticated, so the
-- PUBLIC revoke alone is not enough there. Guarded on pg_roles: neither role
-- exists on a bare Postgres (CI). Section 2 subsumes this, but the auth three
-- are named here so the fix stays legible if that loop is ever narrowed.

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
        'au_set_password(UUID, TEXT)',
        'au_bump_token_version(UUID, UUID)',
        'au_consume_setup_code(UUID, UUID)'
    ]
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %s', v_fn, v_roles);
    END LOOP;
END
$$;

-- ── 2. Every function this repo created, not just the auth three ─────────────
-- The gap is repo-wide, so ev_*, rbac_*, treasury_* et al. get the same
-- treatment. Extension-owned functions (pgcrypto) are left alone — their grants
-- belong to the extension, and stripping them breaks callers we do not own.
--
-- anon/authenticated are Supabase roles that do not exist on a bare Postgres
-- (CI), hence the pg_roles guard rather than a hard-coded role list.

DO $$
DECLARE
    v_roles TEXT;
    v_fn    TEXT;
BEGIN
    SELECT string_agg(quote_ident(rolname), ', ')
      INTO v_roles
      FROM pg_roles
     WHERE rolname IN ('anon', 'authenticated');

    FOR v_fn IN
        SELECT p.oid::REGPROCEDURE::TEXT
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND NOT EXISTS (
               SELECT 1 FROM pg_depend d
                WHERE d.objid = p.oid AND d.deptype = 'e'
           )
    LOOP
        EXECUTE format('REVOKE ALL ON ROUTINE %s FROM PUBLIC', v_fn);
        IF v_roles IS NOT NULL THEN
            EXECUTE format('REVOKE ALL ON ROUTINE %s FROM %s', v_fn, v_roles);
        END IF;
    END LOOP;
END
$$;

-- ── 3. Default-deny for functions created from here on ──────────────────────
-- ALTER DEFAULT PRIVILEGES only affects objects created by the role that runs
-- it, so this covers functions created by the migration role — which is every
-- function in migrations/.
--
-- Caveat, measured on PG 16.13: the FROM PUBLIC half records nothing. A
-- function's PUBLIC EXECUTE comes from the built-in default ACL rather than a
-- stored grant, so there is no entry to revoke and pg_default_acl stays empty —
-- a function created after this statement is still PUBLIC-executable. It is kept
-- because the roles half is not a no-op where it matters: on Supabase,
-- anon/authenticated ARE reachable through a real pg_default_acl row, and this
-- strips them from it.
--
-- The actual backstop for future functions is therefore the repo-wide assertion
-- in tests/auth/test_rpc_privileges.py, which fails the suite as soon as any
-- non-extension function in public is executable by PUBLIC.

ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

DO $$
DECLARE
    v_roles TEXT;
BEGIN
    SELECT string_agg(quote_ident(rolname), ', ')
      INTO v_roles
      FROM pg_roles
     WHERE rolname IN ('anon', 'authenticated');

    IF v_roles IS NULL THEN
        RETURN;
    END IF;

    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM %s',
        v_roles
    );
END
$$;

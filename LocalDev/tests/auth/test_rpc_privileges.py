"""Issue #25 — the auth RPCs must not be executable by PUBLIC.

A function created without an explicit REVOKE carries EXECUTE for PUBLIC, which
on a Supabase project with the Data API on means the anon key can call it over
PostgREST. Migration 0153 revokes it; this test fails if anything reintroduces
the grant.

has_function_privilege() cannot be asked about PUBLIC, so the check reads
pg_proc.proacl directly:
  * proacl IS NULL  — no ACL was ever set, i.e. the built-in default: PUBLIC has
    EXECUTE.
  * an ACL entry with an empty grantee (it starts with '=') is a PUBLIC grant;
    '=X/owner' is an explicit PUBLIC EXECUTE.
"""

from __future__ import annotations

import pytest

from tests.treasury.conftest import *  # noqa: F401,F403

AUTH_RPCS = [
    "au_set_password(uuid, text)",
    "au_bump_token_version(uuid, uuid)",
    "au_consume_setup_code(uuid, uuid)",
]


@pytest.mark.parametrize("signature", AUTH_RPCS)
def test_auth_rpc_is_not_public_executable(cursor, signature):
    cursor.execute(
        """
        SELECT proacl IS NULL AS default_acl,
               COALESCE(
                   EXISTS (
                       SELECT 1
                       FROM unnest(proacl) AS acl
                       WHERE left(acl::TEXT, 1) = '='
                   ),
                   false
               ) AS public_grant
        FROM pg_proc
        WHERE oid = %s::REGPROCEDURE
        """,
        (signature,),
    )
    row = cursor.fetchone()
    assert row is not None, f"{signature} does not exist"

    assert not row["default_acl"], (
        f"{signature} has default privileges (proacl IS NULL) — PUBLIC can EXECUTE it"
    )
    assert not row["public_grant"], f"{signature} has an explicit PUBLIC EXECUTE grant"


def test_no_repo_function_in_public_is_public_executable(cursor):
    """The same gap repo-wide: 0153 revokes every non-extension function too."""
    cursor.execute(
        """
        SELECT p.oid::REGPROCEDURE::TEXT AS signature
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND NOT EXISTS (
              SELECT 1 FROM pg_depend d
              WHERE d.objid = p.oid AND d.deptype = 'e'
          )
          AND (
              p.proacl IS NULL
              OR EXISTS (
                  SELECT 1 FROM unnest(p.proacl) AS acl WHERE left(acl::TEXT, 1) = '='
              )
          )
        ORDER BY 1
        """
    )
    leaked = [r["signature"] for r in cursor.fetchall()]
    assert leaked == [], f"functions executable by PUBLIC: {leaked}"

"""Guards that keep test data and stray migrations out of prod.

Pure string checks — no I/O, no psycopg2, no reading of .env. Every writer
entry point (pytest conftest, scripts/seed.py, scripts/migrate_db.py) imports
from here, so the project-ref lists live in exactly one place. The refs are
checked in deliberately: the guard must work even when a mispointed `.env`
is the bug. A project ref is an identifier, not a credential.

Spec: docs/superpowers/specs/2026-07-11-prod-db-write-guards-design.md
"""

from __future__ import annotations

from urllib.parse import urlsplit

# The demo Supabase project's ref (the username in a pooler URL is
# `postgres.<project-ref>`).
DEMO_PROJECT_REF = "kikzdpfpprfkkbmcwnhm"

# ── HUMAN ACTION REQUIRED ─────────────────────────────────────────────────
# Fill in the production project ref(s) from the Supabase dashboard
# (production project → Settings → General → Reference ID), e.g.
#   PROD_PROJECT_REFS: frozenset[str] = frozenset({"abcdefghijklmnopqrst"})
# Until this is filled, `npm run migrate:prod` refuses to run at all; the
# fail-closed demo guards already protect prod (any URL that is not the demo
# ref or a local host is refused).
PROD_PROJECT_REFS: frozenset[str] = frozenset()

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})


class ProdGuardError(RuntimeError):
    """A command tried to touch a database it must not. Message is redacted."""


def project_ref(url: str) -> str | None:
    """The `<ref>` of a `postgres.<ref>` pooler username, else None."""
    try:
        username = urlsplit(url).username
    except ValueError:
        return None
    if username and username.startswith("postgres."):
        return username.partition(".")[2] or None
    return None


def redact(url: str) -> str:
    """Username + host + port only — never the password, never the full URL."""
    try:
        parts = urlsplit(url)
        user = parts.username or "?"
        host = parts.hostname or "?"
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return "<unparseable database URL>"
    return f"{user}@{host}{port}"


def classify_url(url: str) -> str:
    """Classify a connection URL: 'local' | 'demo' | 'prod' | 'unknown'.

    Pure string match, most dangerous first: a URL containing a known prod
    ref is 'prod' regardless of anything else about it.
    """
    if any(ref in url for ref in PROD_PROJECT_REFS):
        return "prod"
    if DEMO_PROJECT_REF in url:
        return "demo"
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return "unknown"
    if host in _LOCAL_HOSTS:
        return "local"
    return "unknown"


def require_demo(url: str, *, context: str) -> None:
    """Allow demo/local; refuse prod AND unknown (fail closed).

    Used by pytest, seed, and the ordinary migrate path. Anything that is not
    recognizably the demo or a local database — a mistyped ref, a brand-new
    prod, a teammate's database — is treated as unsafe.
    """
    kind = classify_url(url)
    if kind in ("demo", "local"):
        return
    raise ProdGuardError(
        f"{context}: refusing to touch {kind} database at {redact(url)} — "
        f"only the demo project ({DEMO_PROJECT_REF}) or a local database "
        "is allowed. Check DATABASE_URL/TEST_DATABASE_URL in LocalDev/.env."
    )


def require_prod(url: str) -> None:
    """Refuse anything that is not a known prod ref.

    Used only by `migrate_db.py --prod`, so migrate:prod cannot silently
    target the demo (or anything else) either.
    """
    if not PROD_PROJECT_REFS:
        raise ProdGuardError(
            "PROD_PROJECT_REFS in scripts/db_guard.py is empty — a human must "
            "fill in the production project ref before migrate:prod can run."
        )
    if classify_url(url) != "prod":
        raise ProdGuardError(
            f"migrate:prod: {redact(url)} is not a known prod database — "
            "check PROD_DATABASE_URL against PROD_PROJECT_REFS in scripts/db_guard.py."
        )


def confirmation_matches(typed: str, url: str) -> bool:
    """True iff the operator typed exactly the project ref of `url`.

    The typed-confirmation gate for migrate:prod, factored out pure so it is
    testable without a TTY.
    """
    ref = project_ref(url)
    return ref is not None and typed.strip() == ref

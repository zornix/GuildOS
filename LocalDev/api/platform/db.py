"""The one database accessor.

ADR-0002: there is a single Postgres client in every environment, selected by
`DATABASE_URL`. Domains call `get_db()`; nothing else acquires a client.
"""

from __future__ import annotations

from api.config import settings

_client = None


def get_db():
    """Return the process-wide PostgresClient, building it on first use."""
    global _client
    if _client is None:
        if not settings.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is unset — the backend has one database path "
                "(ADR-0002). Set it in LocalDev/.env or the deploy environment."
            )
        if not settings.JWT_SECRET:
            raise RuntimeError("JWT_SECRET is unset — it is the token verifier key.")
        from api.platform.postgres import PostgresClient

        _client = PostgresClient(settings.DATABASE_URL, settings.JWT_SECRET)
    return _client

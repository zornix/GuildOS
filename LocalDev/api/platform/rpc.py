"""Single sanctioned path for atomic multi-row mutations (plpgsql RPCs)."""

from __future__ import annotations

from api.platform.db import get_db


def call_rpc(name: str, params: dict, *, sb=None):
    """Call one plpgsql RPC.

    Multi-write operations must be expressed as one database function; Postgres
    executes that function body in a single server-side transaction.
    """
    client = sb or get_db()
    return client.rpc(name, params).execute()

"""Single sanctioned path for atomic Treasury mutations."""

from __future__ import annotations

from api.db import get_supabase_admin


def call_rpc(name: str, params: dict, *, sb=None):
    """Call one plpgsql RPC.

    Multi-write Treasury operations must be expressed as one database function;
    Postgres executes that function body in a single server-side transaction.
    """
    client = sb or get_supabase_admin()
    return client.rpc(name, params).execute()

"""Single sanctioned path for atomic Tasks mutations (tk_* plpgsql RPCs)."""

from __future__ import annotations

from api.db import get_supabase_admin


def call_rpc(name: str, params: dict, *, sb=None):
    client = sb or get_supabase_admin()
    return client.rpc(name, params).execute()

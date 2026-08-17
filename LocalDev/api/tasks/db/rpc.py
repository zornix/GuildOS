"""Single sanctioned path for atomic Tasks mutations (tk_* plpgsql RPCs)."""

from __future__ import annotations

from api.platform.db import get_db


def call_rpc(name: str, params: dict, *, sb=None):
    client = sb or get_db()
    return client.rpc(name, params).execute()

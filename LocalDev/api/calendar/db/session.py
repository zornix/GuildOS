"""Calendar database session helpers."""

from __future__ import annotations

from api.db import get_supabase_admin

def get_calendar_db():
    return get_supabase_admin()

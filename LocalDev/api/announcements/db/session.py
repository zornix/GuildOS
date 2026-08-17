"""Announcements database session helpers."""

from __future__ import annotations

from api.platform.db import get_db


def get_announcements_db():
    return get_db()

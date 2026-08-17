"""Recruitment database session helpers."""

from __future__ import annotations

from api.platform.db import get_db


def get_recruitment_db():
    return get_db()

"""Outbound message delivery mode."""

from __future__ import annotations

from api.config import settings


def delivery_mode() -> str:
    """Single source of truth: api/config.py settings, never os.environ."""
    return settings.MESSAGE_DELIVERY_MODE or "dry_run"

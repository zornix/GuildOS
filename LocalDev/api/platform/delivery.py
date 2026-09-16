"""Outbound delivery modes — one per channel (ADR-0005)."""

from __future__ import annotations

from api.config import settings


def delivery_mode() -> str:
    """Single source of truth: api/config.py settings, never os.environ."""
    return settings.MESSAGE_DELIVERY_MODE or "dry_run"


def email_delivery_mode() -> str:
    """"dry_run" (nothing leaves the process) or "smtp". Settings, not env."""
    return settings.EMAIL_DELIVERY_MODE or "dry_run"

"""Retired response DTOs should not remain public schema exports."""

from __future__ import annotations

from api.treasury.api import schemas


def test_retired_treasury_message_is_removed():
    assert not hasattr(schemas, "TreasuryMessage")

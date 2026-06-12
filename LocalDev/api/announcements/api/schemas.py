"""Announcements API schemas (domain-local, Pydantic v2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    # members_with_balance is the treasury→announcements audience seam.
    audience: str = Field(
        default="chapter", pattern="^(chapter|officers|members_with_balance)$"
    )


class SmsSendConfirm(BaseModel):
    """Two-phase confirm: the recipient count the sender saw on the preview."""

    confirmed_recipient_count: int = Field(ge=0)

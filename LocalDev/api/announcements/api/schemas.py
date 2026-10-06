"""Announcements API schemas (domain-local, Pydantic v2)."""

from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, Field, model_validator


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    # members_with_balance is the treasury→announcements audience seam.
    audience: str = Field(
        default="chapter", pattern="^(chapter|officers|members_with_balance)$"
    )
    # Calendar presence, not a scheduled send. Twilio still fires on
    # POST /{id}/send-sms; a dated announcement simply also shows on the calendar.
    calendar_date: date | None = None
    calendar_time: time | None = None

    @model_validator(mode="after")
    def _time_needs_a_date(self):
        if self.calendar_time is not None and self.calendar_date is None:
            raise ValueError("calendar_time requires calendar_date")
        return self


class SmsSendConfirm(BaseModel):
    """Two-phase confirm: the recipient count the sender saw on the preview."""

    confirmed_recipient_count: int = Field(ge=0)

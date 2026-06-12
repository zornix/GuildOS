"""Attendance API schemas (domain-local, Pydantic v2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    event_id: str
    mode: str = Field(default="short_link", pattern="^(qr|short_link|manual)$")
    closes_at: datetime | None = None

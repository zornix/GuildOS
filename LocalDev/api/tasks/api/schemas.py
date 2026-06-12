"""Tasks API schemas (domain-local, Pydantic v2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    assigned_member_id: str | None = None
    group_id: str | None = None
    event_id: str | None = None
    required: bool = False
    due_at: datetime | None = None


class TaskStatusUpdate(BaseModel):
    status: str = Field(pattern="^(open|committed|in_progress|done|cancelled)$")


class CommitRequest(BaseModel):
    """member_id may only differ from the caller when they hold tasks:assign."""

    member_id: str | None = None


class UncommitRequest(BaseModel):
    """member_id may only differ from the caller when they hold tasks:review."""

    reason: str | None = None
    member_id: str | None = None

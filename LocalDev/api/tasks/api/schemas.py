"""Tasks API schemas (domain-local, Pydantic v2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    assigned_member_id: str | None = None
    group_id: str | None = None
    required: bool = False
    due_at: datetime | None = None


class TaskStatusUpdate(BaseModel):
    status: str = Field(pattern="^(open|in_progress|done|cancelled)$")

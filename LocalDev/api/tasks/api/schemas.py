"""Tasks API schemas (domain-local, Pydantic v2).

User-facing layer says "job"; storage/RPCs/routes stay tasks/tk_* (decision D1).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TaskCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    assigned_member_id: str | None = None
    group_id: str | None = None
    event_id: str | None = None
    people_needed: int = Field(default=1, ge=1)
    required: bool = False
    due_at: datetime | None = None


class TaskStatusUpdate(BaseModel):
    # done_reported/approved are set only via the report/approve RPCs — rejected here.
    status: str = Field(pattern="^(open|committed|in_progress|done|cancelled)$")


class RejectIn(BaseModel):
    """Rejecting a reported job requires a non-empty reason (spec §2.4)."""

    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must not be blank")
        return v.strip()


class CommitRequest(BaseModel):
    """member_id may only differ from the caller when they hold tasks:assign."""

    member_id: str | None = None


class UncommitRequest(BaseModel):
    """member_id may only differ from the caller when they hold tasks:review."""

    reason: str | None = None
    member_id: str | None = None

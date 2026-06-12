from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UsageTrack(BaseModel):
    event_name: str
    metadata: dict[str, Any] | None = Field(default_factory=dict)

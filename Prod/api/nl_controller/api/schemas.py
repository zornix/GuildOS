"""NL controller API schemas (domain-local, Pydantic v2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CommandSubmit(BaseModel):
    input_text: str = Field(min_length=1)


class CommandReview(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")

"""Base Treasury API schemas.

Domain-specific DTOs live in per-domain modules as chunks are implemented.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TreasuryMessage(BaseModel):
    message: str = Field(min_length=1)

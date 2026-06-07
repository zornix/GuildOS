"""Shared list response envelope for Treasury APIs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Page(BaseModel):
    data: list[Any]
    next_cursor: str | None = None
    total: int | None = None

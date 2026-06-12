"""Bylaws API schemas (domain-local, Pydantic v2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BylawsDocumentCreate(BaseModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)


class BylawsQuery(BaseModel):
    question: str = Field(min_length=1)

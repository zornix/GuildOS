"""Initiatives domain-local Pydantic schemas (never shared across domains)."""

from __future__ import annotations

from datetime import date, time
from typing import Optional

from pydantic import BaseModel


class InitiativeCreate(BaseModel):
    title: str
    description: Optional[str] = None
    date: date
    time: time
    end_date: Optional[date] = None  # defaults to `date` when only end_time given
    end_time: Optional[time] = None
    chair_member_ids: Optional[list[str]] = None


class InitiativeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    date: Optional[date] = None
    time: Optional[time] = None
    end_date: Optional[date] = None
    end_time: Optional[time] = None


class ChairOut(BaseModel):
    member_id: str
    is_creator: bool = False
    name: Optional[str] = None


class ChairAdd(BaseModel):
    member_id: str

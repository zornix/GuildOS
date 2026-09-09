"""Attendance summary read — derived attendance % (spec §3).

Officer-or-self semantics: any member can read their own summary; reading the
whole chapter (or another member) requires calendar:officer:view or one of the
attendance officer permissions.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.attendance.auth import (
    ATTENDANCE_OVERRIDE,
    CALENDAR_OFFICER_VIEW,
    EXCUSE_REVIEW,
)
from api.attendance.services.signals import attendance_summary
from api.platform.db import get_db
from api.dependencies import get_current_user
from api.rbac.services.permissions import get_member_permissions

router = APIRouter()

_VIEW_ALL_PERMS = (CALENDAR_OFFICER_VIEW, ATTENDANCE_OVERRIDE, EXCUSE_REVIEW)


@router.get("/summary")
async def get_attendance_summary(
    member_id: str | None = None, user=Depends(get_current_user)
):
    sb = get_db()
    granted = get_member_permissions(user, sb=sb)
    can_view_all = any(p in granted for p in _VIEW_ALL_PERMS)

    if member_id and member_id != user["id"] and not can_view_all:
        raise HTTPException(403, "You may only view your own attendance summary")
    if not member_id and not can_view_all:
        member_id = user["id"]

    return attendance_summary(sb, chapter_id=user["chapter_id"], member_id=member_id)

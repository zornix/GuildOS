"""Member balance HTTP surface."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user
from api.rbac.services.permissions import has_permission
from api.platform.db import get_db
from api.treasury.services import balance as svc
from api.treasury.services.member_dashboard import get_member_dashboard as dashboard_svc

# Catalog permission key gating this surface (ADR-0001; 0147). Reading ANOTHER
# member's financial record is row-level treasury access → treasury:audit:view.
RECORD_VIEW = "treasury:audit:view"

router = APIRouter()


@router.get("/members/{member_id}/balance")
async def get_member_balance(member_id: str, user=Depends(get_current_user)):
    """A member's cached balance.

    Access: the member themself, OR any `treasury:audit:view` holder IN THE SAME
    CHAPTER. A non-existent member, or one outside the requester's chapter,
    returns 404 so cross-chapter existence is never leaked. Mirrors the
    /statement guard exactly — an earlier `role == "officer"` check both bypassed
    the permission model and let an officer read balances in *other* chapters.
    """
    sb = get_db()

    if str(user["id"]) != str(member_id) and not has_permission(user, RECORD_VIEW):
        raise HTTPException(403, f"Missing permission: {RECORD_VIEW}")

    member = (
        sb.table("members")
        .select("chapter_id")
        .eq("id", member_id)
        .maybe_single()
        .execute()
    ).data
    if not member or str(member["chapter_id"]) != str(user["chapter_id"]):
        raise HTTPException(404, "Member not found")

    return svc.get_member_balance(sb, member_id=member_id)


@router.get("/members/{member_id}/dashboard")
async def get_member_treasury_dashboard(member_id: str, user=Depends(get_current_user)):
    """V1 member treasury dashboard (decision #3: overdue invoices stay visible).

    Access: the member themself, OR a `treasury:audit:view` holder, OR a
    `treasury:payment:verify` holder (Finance Board reviewers) — all scoped
    to the requester's own chapter (404 on cross-chapter probes).
    """
    sb = get_db()

    if str(user["id"]) != str(member_id):
        if not has_permission(user, RECORD_VIEW) and not has_permission(
            user, "treasury:payment:verify"
        ):
            raise HTTPException(403, "Not allowed to view this member's treasury dashboard")

    member = (
        sb.table("members")
        .select("chapter_id")
        .eq("id", member_id)
        .maybe_single()
        .execute()
    ).data
    if not member or str(member["chapter_id"]) != str(user["chapter_id"]):
        raise HTTPException(404, "Member not found")

    return dashboard_svc(sb, chapter_id=user["chapter_id"], member_id=member_id)

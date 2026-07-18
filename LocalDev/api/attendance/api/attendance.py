from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user
from api.attendance.auth import ATTENDANCE_OVERRIDE, require_permission
from api.attendance.db.rpc import call_rpc
from .schemas import PhoneCheckIn, ManualAttendance
from api.attendance.services.checkin_links import validate_checkin_link
from api.db import get_supabase

router = APIRouter()


def _rpc_http_error(exc: Exception) -> HTTPException:
    """Map at_* RPC exceptions onto HTTP statuses (mirrors the ev_* handlers)."""
    msg = str(exc)
    if "not found" in msg:
        return HTTPException(404, msg)
    if "not an active member" in msg or "not authorized" in msg:
        return HTTPException(403, msg)
    return HTTPException(400, msg)


@router.post("/checkin/{short_code}")
async def checkin_via_link(short_code: str, user=Depends(get_current_user)):
    """
    Check in using a short link code.
    Validates: link exists, not expired, not already used by this member.
    """
    link_data = await validate_checkin_link(short_code)

    if not link_data:
        raise HTTPException(410, "Check-in link is expired or invalid")

    event = link_data["events"]

    if event["chapter_id"] != user["chapter_id"]:
        raise HTTPException(403, "Wrong chapter")

    sb = get_supabase()
    existing = (
        sb.table("attendance")
        .select("id")
        .eq("event_id", event["id"])
        .eq("member_id", user["id"])
        .execute()
    )
    if existing.data and existing.data[0].get("checked_in"):
        raise HTTPException(409, "Already checked in")

    sb.table("attendance").upsert({
        "event_id": event["id"],
        "member_id": user["id"],
        "checked_in": True,
        "checked_in_at": datetime.now(timezone.utc).isoformat(),
        "method": "link",
    }, on_conflict="event_id,member_id").execute()

    return {
        "status": "checked_in",
        "event_title": event["title"],
        "checked_in_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/checkin/{short_code}/phone")
async def checkin_via_phone(short_code: str, body: PhoneCheckIn):
    """
    Check in using phone number only — no auth required.
    The check-in link + matching phone number is sufficient verification.
    """
    link_data = await validate_checkin_link(short_code)

    if not link_data:
        raise HTTPException(410, "Check-in link is expired or invalid")

    event = link_data["events"]
    sb = get_supabase()

    member_result = (
        sb.table("members")
        .select("id, chapter_id")
        .eq("phone", body.phone)
        .eq("chapter_id", event["chapter_id"])
        .eq("status", "active")
        .execute()
    )

    if not member_result.data:
        raise HTTPException(404, "No member found with that phone number")

    member = member_result.data[0]

    existing = (
        sb.table("attendance")
        .select("id, checked_in")
        .eq("event_id", event["id"])
        .eq("member_id", member["id"])
        .execute()
    )
    if existing.data and existing.data[0].get("checked_in"):
        raise HTTPException(409, "Already checked in")

    sb.table("attendance").upsert({
        "event_id": event["id"],
        "member_id": member["id"],
        "checked_in": True,
        "checked_in_at": datetime.now(timezone.utc).isoformat(),
        "method": "link",
    }, on_conflict="event_id,member_id").execute()

    return {
        "status": "checked_in",
        "event_title": event["title"],
        "checked_in_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/event/{event_id}")
async def get_attendance(event_id: str, user=Depends(get_current_user)):
    """Get attendance roster for an event. All authenticated members can view."""
    sb = get_supabase()

    event = (
        sb.table("events")
        .select("id, chapter_id")
        .eq("id", event_id)
        .eq("chapter_id", user["chapter_id"])
        .single()
        .execute()
    )
    if not event.data:
        raise HTTPException(404, "Event not found")

    members = (
        sb.table("members")
        .select("id, name, email")
        .eq("chapter_id", user["chapter_id"])
        .eq("status", "active")
        .execute()
    ).data

    checked_in = (
        sb.table("attendance")
        .select("member_id, checked_in, checked_in_at, method")
        .eq("event_id", event_id)
        .execute()
    ).data

    excuses = (
        sb.table("excuses")
        .select("member_id, status")
        .eq("event_id", event_id)
        .execute()
    ).data

    checkin_map = {a["member_id"]: a for a in checked_in}
    excuse_map = {e["member_id"]: e for e in excuses}

    roster = []
    for m in members:
        att = checkin_map.get(m["id"])
        exc = excuse_map.get(m["id"])
        roster.append({
            "member_id": m["id"],
            "name": m["name"],
            "checked_in": bool(att and att["checked_in"]),
            "checked_in_at": att["checked_in_at"] if att else None,
            "method": att["method"] if att else None,
            "excuse_status": exc["status"] if exc else None,
        })

    return roster


@router.post("/event/{event_id}/manual/{member_id}")
async def manual_checkin(
    event_id: str,
    member_id: str,
    body: ManualAttendance,
    officer=Depends(require_permission(ATTENDANCE_OVERRIDE)),
):
    """Officer manually marks a member as present, excused, or absent."""
    try:
        result = call_rpc("at_set_attendance", {
            "p_chapter_id": officer["chapter_id"],
            "p_event_id": event_id,
            "p_member_id": member_id,
            "p_status": body.status,
            "p_reason": body.reason,
            "p_actor_id": officer["id"],
            "p_idempotency_key": None,
        })
    except HTTPException:
        raise
    except Exception as exc:
        raise _rpc_http_error(exc) from exc

    return result.data

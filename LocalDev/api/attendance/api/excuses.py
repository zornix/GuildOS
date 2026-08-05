from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user
from api.attendance.auth import EXCUSE_REVIEW, require_permission
from api.attendance.db.rpc import call_rpc
from api.rbac.services.permissions import has_permission
from .schemas import ExcuseCreate, ExcuseReview
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


@router.post("/event/{event_id}")
async def submit_excuse(event_id: str, body: ExcuseCreate, user=Depends(get_current_user)):
    """Submit an excuse for missing an event."""
    sb = get_supabase()

    event = (
        sb.table("events")
        .select("id, chapter_id")
        .eq("id", event_id)
        .single()
        .execute()
    )
    if not event.data:
        raise HTTPException(404, "Event not found")
    if event.data["chapter_id"] != user["chapter_id"]:
        raise HTTPException(403, "Event does not belong to your chapter")

    existing = (
        sb.table("excuses")
        .select("id, status")
        .eq("event_id", event_id)
        .eq("member_id", user["id"])
        .in_("status", ["pending", "approved"])
        .execute()
    )
    if existing.data:
        raise HTTPException(409, "Excuse already submitted for this event")

    # Delete any previously denied excuse so the new insert succeeds
    # against the unique(event_id, member_id) constraint
    sb.table("excuses") \
        .delete() \
        .eq("event_id", event_id) \
        .eq("member_id", user["id"]) \
        .eq("status", "denied") \
        .execute()

    result = sb.table("excuses").insert({
        "event_id": event_id,
        "member_id": user["id"],
        "reason": body.reason,
        "status": "pending",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    if not result.data:
        raise HTTPException(500, "Failed to submit excuse")

    return result.data[0]


@router.get("/")
async def list_excuses(status: str = None, user=Depends(get_current_user)):
    """
    List excuses.
    `attendance:excuse:review` holders: all excuses for their chapter
    (filterable by status) — the same key that gates the review action itself.
    Everyone else: only their own.
    """
    sb = get_supabase()

    if has_permission(user, EXCUSE_REVIEW):
        query = (
            sb.table("excuses")
            .select("*, members(name, email), events(title, date)")
            .eq("events.chapter_id", user["chapter_id"])
        )
        if status:
            query = query.eq("status", status)
        query = query.order("submitted_at", desc=True)
    else:
        query = (
            sb.table("excuses")
            .select("*, events(title, date)")
            .eq("member_id", user["id"])
            .order("submitted_at", desc=True)
        )

    return query.execute().data


@router.put("/{excuse_id}/review")
async def review_excuse(
    excuse_id: str,
    body: ExcuseReview,
    officer=Depends(require_permission(EXCUSE_REVIEW)),
):
    """Approve or deny an excuse. Approving voids any matching unpaid fine invoice."""
    try:
        result = call_rpc("at_review_excuse", {
            "p_chapter_id": officer["chapter_id"],
            "p_excuse_id": excuse_id,
            "p_status": body.status,
            "p_actor_id": officer["id"],
            "p_idempotency_key": None,
        })
    except HTTPException:
        raise
    except Exception as exc:
        raise _rpc_http_error(exc) from exc

    return result.data

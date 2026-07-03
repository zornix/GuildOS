"""Events HTTP surface. Mounted at `/api/events` by router.py.

Handlers are thin (parse → service → respond); business logic and
authorization details live in api/events/services/events.py.
Legacy paths and response shapes are preserved — V1 only ADDS fields.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi import APIRouter, Depends, Header, HTTPException

from api.attendance.services.checkin_links import (
    create_checkin_link,
    deactivate_checkin_link,
    get_active_link_for_event,
)
from api.dependencies import get_current_user, require_officer
from api.events.auth import (
    EVENT_CREATE,
    EVENT_DELETE,
    EVENT_UPDATE,
    require_permission,
)
from api.events.db.session import get_events_db
from api.events.services import events as svc

from .schemas import (
    CheckInLinkResponse,
    EventCreate,
    EventUpdate,
    OrganizerAdd,
    SupervisorAdd,
    SupervisorSet,
)

router = APIRouter()


@contextmanager
def _map_domain_errors():
    try:
        yield
    except svc.EventNotFound as exc:
        raise HTTPException(404, str(exc) or "Event not found")
    except svc.NotPermitted as exc:
        raise HTTPException(403, str(exc))
    except svc.SupervisorRuleViolation as exc:
        raise HTTPException(409, str(exc))
    except (svc.NotEligible, svc.InvalidTimeRange) as exc:
        raise HTTPException(422, str(exc))


# NOTE: fixed paths (/types) are declared before /{event_id} so they are not
# captured by the path parameter.

@router.get("/types")
async def list_event_types(user=Depends(get_current_user)):
    """List the chapter's event types (seeding defaults on first use)."""
    return svc.list_event_types(get_events_db(), chapter_id=user["chapter_id"])


@router.get("/")
async def list_events(upcoming: bool = True, user=Depends(get_current_user)):
    """List events for the user's chapter (visibility-enforced)."""
    return svc.list_events(get_events_db(), user=user, upcoming=upcoming)


@router.post("/")
async def create_event(
    body: EventCreate,
    user=Depends(require_permission(EVENT_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Create a new event (audience list + group handled atomically in the RPC)."""
    with _map_domain_errors():
        return svc.create_event(
            get_events_db(),
            actor=user,
            title=body.title,
            description=body.description,
            date=body.date.isoformat(),
            time=body.time.isoformat(),
            end_date=body.end_date.isoformat() if body.end_date else None,
            end_time=body.end_time.isoformat() if body.end_time else None,
            invite_link=body.invite_link,
            location=body.location,
            required=body.required,
            finable=body.finable,
            fine_amount=body.fine_amount,
            event_type=body.event_type,
            event_type_name=body.event_type_name,
            visibility=body.visibility,
            audience=body.audience,
            audience_member_ids=body.audience_member_ids,
            event_group_id=body.event_group_id,
            group_with_event_id=body.group_with_event_id,
            idempotency_key=idempotency_key,
        )


@router.get("/{event_id}")
async def get_event(event_id: str, user=Depends(get_current_user)):
    """Event details with attendance summary, organizers, and group siblings."""
    with _map_domain_errors():
        return svc.get_event(get_events_db(), user=user, event_id=event_id)


@router.put("/{event_id}")
async def update_event(
    event_id: str,
    body: EventUpdate,
    user=Depends(require_permission(EVENT_UPDATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Update an event."""
    with _map_domain_errors():
        return svc.update_event(
            get_events_db(),
            actor=user,
            event_id=event_id,
            updates=body.model_dump(exclude_none=True),
            idempotency_key=idempotency_key,
        )


@router.delete("/{event_id}")
async def delete_event(event_id: str, user=Depends(require_permission(EVENT_DELETE))):
    """Delete an event."""
    sb = get_events_db()
    event = (
        sb.table("events")
        .select("id")
        .eq("id", event_id)
        .eq("chapter_id", user["chapter_id"])
        .maybe_single()
        .execute()
    )
    if not event.data:
        raise HTTPException(404, "Event not found")
    sb.table("events") \
        .delete() \
        .eq("id", event_id) \
        .eq("chapter_id", user["chapter_id"]) \
        .execute()
    return {"deleted": True}


@router.post("/{event_id}/supervisor")
async def set_supervisor(
    event_id: str,
    body: SupervisorSet,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """DEPRECATED (see CONFORM_TODO.md): now adds a co-supervisor. Use
    POST /{event_id}/supervisors."""
    with _map_domain_errors():
        return svc.set_supervisor(
            get_events_db(),
            actor=user,
            event_id=event_id,
            member_id=body.member_id,
            idempotency_key=idempotency_key,
        )


@router.post("/{event_id}/supervisors")
async def add_supervisor(
    event_id: str,
    body: SupervisorAdd,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Add a co-supervisor (a current supervisor or calendar:event:update)."""
    with _map_domain_errors():
        return svc.add_supervisor(
            get_events_db(),
            actor=user,
            event_id=event_id,
            member_id=body.member_id,
            idempotency_key=idempotency_key,
        )


@router.delete("/{event_id}/supervisors/{member_id}")
async def remove_supervisor(
    event_id: str,
    member_id: str,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Remove a co-supervisor (creator/min-1 violations surface as 409)."""
    with _map_domain_errors():
        return svc.remove_supervisor(
            get_events_db(),
            actor=user,
            event_id=event_id,
            member_id=member_id,
            idempotency_key=idempotency_key,
        )


@router.post("/{event_id}/organizers")
async def add_organizer(
    event_id: str,
    body: OrganizerAdd | None = None,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Self-volunteer (no special permission) or assign (calendar:event:update)."""
    with _map_domain_errors():
        return svc.add_organizer(
            get_events_db(),
            actor=user,
            event_id=event_id,
            member_id=body.member_id if body else None,
            idempotency_key=idempotency_key,
        )


@router.delete("/{event_id}/organizers/{member_id}")
async def remove_organizer(
    event_id: str,
    member_id: str,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Self-leave or officer removal."""
    with _map_domain_errors():
        return svc.remove_organizer(
            get_events_db(),
            actor=user,
            event_id=event_id,
            member_id=member_id,
            idempotency_key=idempotency_key,
        )


# ── Check-in links (legacy surface, unchanged) ────────────────────────────────

@router.get("/{event_id}/checkin-link")
async def get_checkin_link(event_id: str, user=Depends(get_current_user)):
    """Get the currently active check-in link for an event, if any."""
    sb = get_events_db()
    event = (
        sb.table("events")
        .select("id")
        .eq("id", event_id)
        .eq("chapter_id", user["chapter_id"])
        .single()
        .execute()
    )
    if not event.data:
        raise HTTPException(404, "Event not found")
    link = await get_active_link_for_event(event_id)
    return link or {}


@router.post("/{event_id}/checkin-link", response_model=CheckInLinkResponse)
async def generate_checkin_link(event_id: str, officer=Depends(require_officer)):
    """
    Generate a short-lived check-in link for an event.
    Officer shows this link (or its QR) to members in-person.
    Any previous active link for this event is deactivated.
    """
    sb = get_events_db()
    event = (
        sb.table("events")
        .select("id")
        .eq("id", event_id)
        .eq("chapter_id", officer["chapter_id"])
        .single()
        .execute()
    )
    if not event.data:
        raise HTTPException(404, "Event not found")

    link = await create_checkin_link(event_id, officer["id"])
    return link


@router.delete("/{event_id}/checkin-link")
async def kill_checkin_link(event_id: str, officer=Depends(require_officer)):
    """Manually deactivate the current check-in link."""
    await deactivate_checkin_link(event_id)
    return {"deactivated": True}

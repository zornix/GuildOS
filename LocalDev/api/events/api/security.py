"""Security assignments + swap requests HTTP surface (Phase 4).

Mounted at `/api/events` by router.py. Handlers are thin (parse → service →
respond); business logic + authorization live in
`api/events/services/security.py`. Manage (assign/remove) is supervisor-gated in
the service; the swap flow is identity-gated inside the RPCs, so those routes are
open to any authenticated member and rely on the RPC guards.

RPC-exception → HTTP mapping follows the `_rpc_http_error` style of
`api/tasks/api/jobs.py`.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi import APIRouter, Depends, Header, HTTPException

from api.dependencies import get_current_user
from api.platform.db import get_db
from api.events.services import security as svc
from api.events.services.events import EventNotFound, NotPermitted

from .schemas import SecurityAssignIn, SecurityAssignmentOut, SwapOut, SwapRequestIn

router = APIRouter()

# 409-mapped RPC guard failures (state/uniqueness conflicts).
_CONFLICT = (
    "security_preassigned",
    "security_no_unclaim",
    "swap_already_pending",
    "swap_wrong_state",
    "swap_stale",
    "target_already_assigned",
    "security_already_approved",
)
# 403-mapped RPC identity failures.
_FORBIDDEN = ("not_assigned", "not_swap_target")


def _rpc_http_error(exc: Exception) -> HTTPException:
    """Map ev_* security RPC exceptions onto HTTP statuses."""
    msg = str(exc)
    if "not found" in msg:
        return HTTPException(404, msg)
    if any(tok in msg for tok in _FORBIDDEN):
        return HTTPException(403, msg)
    if "swap_self" in msg:
        return HTTPException(422, "You cannot swap a security assignment with yourself")
    if any(tok in msg for tok in _CONFLICT):
        return HTTPException(409, msg)
    return HTTPException(400, msg)


@contextmanager
def _map_security_errors():
    try:
        yield
    except EventNotFound as exc:
        raise HTTPException(404, str(exc) or "Not found")
    except NotPermitted as exc:
        raise HTTPException(403, str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise _rpc_http_error(exc) from exc


# NOTE: the literal /security-swaps/mine is declared before the /{event_id}/...
# dynamic routes so it can never be captured by a path parameter (plan §3.1).

@router.get("/security-swaps/mine")
async def my_swaps(user=Depends(get_current_user)):
    """Pending swaps involving me: incoming (I'm the target) + outgoing."""
    return svc.list_my_swaps(
        get_db(), chapter_id=user["chapter_id"], member_id=user["id"]
    )


@router.get("/{event_id}/security", response_model=list[SecurityAssignmentOut])
async def list_security(event_id: str, user=Depends(get_current_user)):
    """Security roster for an event (read view). Any chapter member may view."""
    with _map_security_errors():
        return svc.list_security(
            get_db(), chapter_id=user["chapter_id"], event_id=event_id
        )


@router.post("/{event_id}/security", response_model=SecurityAssignmentOut, status_code=201)
async def assign_security(
    event_id: str,
    body: SecurityAssignIn,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Pre-assign a member to security (supervisor or calendar:event:update)."""
    with _map_security_errors():
        return svc.assign_security(
            get_db(),
            actor=user,
            event_id=event_id,
            member_id=body.member_id,
            idempotency_key=idempotency_key,
        )


@router.delete("/{event_id}/security/{task_id}")
async def remove_security(
    event_id: str,
    task_id: str,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Remove a security assignment (same gate as assign)."""
    with _map_security_errors():
        return svc.remove_security(
            get_db(),
            actor=user,
            event_id=event_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
        )


@router.post("/{event_id}/security/{task_id}/swap-request", response_model=SwapOut)
async def request_swap(
    event_id: str,
    task_id: str,
    body: SwapRequestIn,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """The assignment holder asks a target member to take over (RPC-gated)."""
    with _map_security_errors():
        return svc.request_swap(
            get_db(),
            actor=user,
            task_id=task_id,
            target_member_id=body.target_member_id,
            note=body.note,
            idempotency_key=idempotency_key,
        )


@router.post("/{event_id}/security/swaps/{swap_id}/accept", response_model=SwapOut)
async def accept_swap(
    event_id: str,
    swap_id: str,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """The swap target accepts — atomic handover (RPC enforces target identity)."""
    with _map_security_errors():
        return svc.accept_swap(
            get_db(), actor=user, swap_id=swap_id, idempotency_key=idempotency_key
        )


@router.post("/{event_id}/security/swaps/{swap_id}/decline", response_model=SwapOut)
async def decline_swap(
    event_id: str,
    swap_id: str,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """The swap target declines (RPC enforces target identity)."""
    with _map_security_errors():
        return svc.decline_swap(
            get_db(), actor=user, swap_id=swap_id, idempotency_key=idempotency_key
        )

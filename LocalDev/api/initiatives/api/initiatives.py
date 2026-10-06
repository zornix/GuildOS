"""Initiatives HTTP surface. Mounted at `/api/initiatives` by router.py.

Handlers are thin (parse → service → respond); business logic and
authorization details live in api/initiatives/services/initiatives.py.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi import APIRouter, Depends, Header, HTTPException, status

from api.dependencies import get_current_user
from api.initiatives.auth import INITIATIVE_CREATE
from api.rbac.auth import require_permission
from api.platform.db import get_db
from api.initiatives.services import initiatives as svc

from .schemas import ChairAdd, InitiativeCreate, InitiativeUpdate

router = APIRouter()


@contextmanager
def _map_domain_errors():
    try:
        yield
    except svc.InitiativeNotFound as exc:
        raise HTTPException(404, str(exc) or "Initiative not found")
    except svc.MemberNotInChapter:
        raise HTTPException(404, "Member not found")
    except svc.NotPermitted as exc:
        raise HTTPException(403, str(exc))
    except svc.ChairRuleViolation as exc:
        raise HTTPException(409, str(exc))
    except svc.InvalidTimeRange as exc:
        raise HTTPException(422, str(exc))


@router.get("/")
async def list_initiatives(user=Depends(get_current_user)):
    """List initiatives for the user's chapter."""
    return svc.list_initiatives(get_db(), chapter_id=user["chapter_id"])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_initiative(
    body: InitiativeCreate,
    user=Depends(require_permission(INITIATIVE_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Create an initiative (chair roles only); the actor is auto-added as creator chair."""
    with _map_domain_errors():
        return svc.create_initiative(
            get_db(),
            actor=user,
            title=body.title,
            description=body.description,
            date=body.date.isoformat(),
            time=body.time.isoformat(),
            end_date=body.end_date.isoformat() if body.end_date else None,
            end_time=body.end_time.isoformat() if body.end_time else None,
            chair_member_ids=body.chair_member_ids,
            idempotency_key=idempotency_key,
        )


@router.get("/{initiative_id}")
async def get_initiative(initiative_id: str, user=Depends(get_current_user)):
    """Initiative details: chairs, jobs, and job counts."""
    with _map_domain_errors():
        return svc.get_initiative(
            get_db(),
            chapter_id=user["chapter_id"],
            initiative_id=initiative_id,
        )


@router.patch("/{initiative_id}")
async def update_initiative(
    initiative_id: str,
    body: InitiativeUpdate,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Update an initiative (assigned chair only)."""
    with _map_domain_errors():
        return svc.update_initiative(
            get_db(),
            actor=user,
            initiative_id=initiative_id,
            updates=body.model_dump(exclude_none=True),
            idempotency_key=idempotency_key,
        )


@router.post("/{initiative_id}/chairs")
async def add_chair(
    initiative_id: str,
    body: ChairAdd,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Add a chair (assigned chair only)."""
    with _map_domain_errors():
        return svc.add_chair(
            get_db(),
            actor=user,
            initiative_id=initiative_id,
            member_id=body.member_id,
            idempotency_key=idempotency_key,
        )


@router.delete("/{initiative_id}/chairs/{member_id}")
async def remove_chair(
    initiative_id: str,
    member_id: str,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Remove a chair (assigned chair only); last_chair violation -> 409."""
    with _map_domain_errors():
        return svc.remove_chair(
            get_db(),
            actor=user,
            initiative_id=initiative_id,
            member_id=member_id,
            idempotency_key=idempotency_key,
        )

"""RBAC HTTP surface: catalog, my-permissions, and admin-gated assignment."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from api.dependencies import get_current_user
from api.rbac.api.schemas import MyPermissionsResponse, RoleAssign
from api.rbac.auth import require_permission
from api.rbac.db.repositories.member_roles import (
    list_member_role_keys,
    list_member_roles,
    list_role_catalog,
)
from api.platform.db import get_db
from api.rbac.services import assignments as svc
from api.rbac.services.permissions import get_member_permissions

router = APIRouter()


@router.get("/roles")
async def get_role_catalog(user=Depends(get_current_user)):
    """Role catalog — visible to any authenticated member."""
    return list_role_catalog(get_db())


@router.get("/me/permissions", response_model=MyPermissionsResponse)
async def get_my_permissions(user=Depends(get_current_user)):
    sb = get_db()
    return MyPermissionsResponse(
        permissions=sorted(get_member_permissions(user, sb=sb)),
        roles=sorted(
            list_member_role_keys(sb, chapter_id=user["chapter_id"], member_id=user["id"])
        ),
    )


@router.get("/members/{member_id}/roles")
async def get_member_roles(
    member_id: str,
    user=Depends(require_permission("roles:assign")),
):
    sb = get_db()
    return list_member_roles(sb, chapter_id=user["chapter_id"], member_id=member_id)


@router.post("/members/{member_id}/roles")
async def assign_member_role(
    member_id: str,
    body: RoleAssign,
    user=Depends(require_permission("roles:assign")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_db()
    return svc.assign_role(
        sb,
        chapter_id=user["chapter_id"],
        member_id=member_id,
        role_key=body.role_key,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )


@router.delete("/members/{member_id}/roles/{role_key}")
async def revoke_member_role(
    member_id: str,
    role_key: str,
    user=Depends(require_permission("roles:assign")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_db()
    return svc.revoke_role(
        sb,
        chapter_id=user["chapter_id"],
        member_id=member_id,
        role_key=role_key,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )

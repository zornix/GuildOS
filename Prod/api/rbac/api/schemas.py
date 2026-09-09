"""RBAC API schemas (domain-local, Pydantic v2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RoleAssign(BaseModel):
    role_key: str = Field(min_length=1)


class MemberRoleResponse(BaseModel):
    id: str
    chapter_id: str
    member_id: str
    role_key: str
    assigned_by: str | None = None
    assigned_at: str


class MyPermissionsResponse(BaseModel):
    permissions: list[str]
    roles: list[str]

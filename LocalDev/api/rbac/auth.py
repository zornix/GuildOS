"""require_permission — the one FastAPI authorization dependency.

Every domain's auth.py imports this; no inline role/permission checks anywhere.

    @router.post("/", dependencies=[Depends(require_permission("tasks:create"))])
    def create(...): ...

or, to receive the user:

    def create(user=Depends(require_permission("tasks:create"))): ...

Multiple permissions = ANY-of. Ownership-scoped checks (own vs any resource)
can't be expressed as a bare dependency — those routes load the resource and
call services.permissions.has_permission(member, perm, resource=...) directly.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException

from api.dependencies import get_current_user
from api.rbac.services.permissions import get_member_permissions


def require_permission(*permissions: str) -> Callable:
    if not permissions:
        raise ValueError("require_permission needs at least one permission")

    def dependency(user=Depends(get_current_user)):
        granted = get_member_permissions(user)
        if not any(p in granted for p in permissions):
            raise HTTPException(
                403, f"Missing permission: {' or '.join(permissions)}"
            )
        return user

    return dependency

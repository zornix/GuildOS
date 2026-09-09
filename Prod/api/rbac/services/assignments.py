"""Role assignment / revocation — delegated to the rbac_* RPCs (atomic path)."""

from __future__ import annotations

from api.platform.rpc import call_rpc


def assign_role(
    sb,
    *,
    chapter_id: str,
    member_id: str,
    role_key: str,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "rbac_assign_role",
        {
            "p_chapter_id": chapter_id,
            "p_member_id": member_id,
            "p_role_key": role_key,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data


def revoke_role(
    sb,
    *,
    chapter_id: str,
    member_id: str,
    role_key: str,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "rbac_revoke_role",
        {
            "p_chapter_id": chapter_id,
            "p_member_id": member_id,
            "p_role_key": role_key,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data

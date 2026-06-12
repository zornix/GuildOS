"""Read-side queries for role assignments and the permission matrix."""

from __future__ import annotations


def list_member_role_keys(sb, *, chapter_id: str, member_id: str) -> list[str]:
    rows = (
        sb.table("member_roles")
        .select("role_key")
        .eq("chapter_id", chapter_id)
        .eq("member_id", member_id)
        .execute()
    ).data or []
    return [r["role_key"] for r in rows]


def list_permissions_for_roles(sb, role_keys: list[str]) -> set[str]:
    if not role_keys:
        return set()
    rows = (
        sb.table("role_permissions")
        .select("role_key, permission_key")
        .in_("role_key", role_keys)
        .execute()
    ).data or []
    return {r["permission_key"] for r in rows}


def list_member_roles(sb, *, chapter_id: str, member_id: str) -> list[dict]:
    return (
        sb.table("member_roles")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("member_id", member_id)
        .order("assigned_at")
        .execute()
    ).data or []


def list_role_catalog(sb) -> list[dict]:
    return (sb.table("roles").select("*").order("key").execute()).data or []

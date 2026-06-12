"""Recruitment pipeline service.

Single-row, chapter-scoped writes via the table builder.
TODO(recruitment): move stage changes behind an rc_* RPC with an
UPDATE_RECRUIT_STAGE audit write once the pipeline grows multi-write effects
(the audit_logs action is already registered in 0082).
"""

from __future__ import annotations

from api.db import get_supabase_admin


def get_recruitment_db():
    return get_supabase_admin()


def _row(result) -> dict:
    data = result.data
    return data[0] if isinstance(data, list) else data


def create_recruit(
    sb,
    *,
    chapter_id: str,
    name: str,
    email: str | None,
    phone: str | None,
    notes: str | None,
    actor_id: str,
) -> dict:
    return _row(
        sb.table("recruits")
        .insert(
            {
                "chapter_id": chapter_id,
                "name": name,
                "email": email,
                "phone": phone,
                "notes": notes,
                "stage": "lead",
                "created_by": actor_id,
            }
        )
        .execute()
    )


def update_stage(sb, *, chapter_id: str, recruit_id: str, stage: str) -> dict | None:
    result = (
        sb.table("recruits")
        .update({"stage": stage})
        .eq("id", recruit_id)
        .eq("chapter_id", chapter_id)
        .execute()
    )
    data = result.data
    if not data:
        return None
    return data[0] if isinstance(data, list) else data


def list_recruits(sb, *, chapter_id: str, stage: str | None = None) -> list[dict]:
    query = sb.table("recruits").select("*").eq("chapter_id", chapter_id)
    if stage:
        query = query.eq("stage", stage)
    return query.order("created_at", desc=True).execute().data or []

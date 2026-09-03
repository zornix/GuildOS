"""Command request lifecycle: submit → review (approve/reject) → execute (stub)."""

from __future__ import annotations

from datetime import datetime, timezone

from api.platform.rows import unwrap_row


def submit_command(sb, *, chapter_id: str, input_text: str, actor_id: str) -> dict:
    # TODO(nl_controller): a real parser would populate proposed_actions with
    # typed action descriptors (e.g. {"service": "events", "op": "create", ...}).
    # Until then requests are recorded verbatim with no proposed actions.
    return unwrap_row(
        sb.table("command_requests")
        .insert(
            {
                "chapter_id": chapter_id,
                "requested_by": actor_id,
                "input_text": input_text,
                "proposed_actions": [],
                "status": "pending_approval",
            }
        )
        .execute()
    )


def review_command(
    sb, *, chapter_id: str, command_id: str, decision: str, actor_id: str
) -> dict | None:
    status = "approved" if decision == "approve" else "rejected"
    result = (
        sb.table("command_requests")
        .update(
            {
                "status": status,
                "reviewed_by": actor_id,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", command_id)
        .eq("chapter_id", chapter_id)
        .eq("status", "pending_approval")
        .execute()
    )
    if not result.data:
        return None
    row = unwrap_row(result)
    # TODO(nl_controller): on approval, execute proposed_actions by calling the
    # target services' public APIs (events/tasks/attendance/treasury/
    # announcements), then advance status to executed/failed. Deliberately not
    # implemented — no actions exist to execute yet.
    return row


def list_commands(sb, *, chapter_id: str, status: str | None = None) -> list[dict]:
    query = sb.table("command_requests").select("*").eq("chapter_id", chapter_id)
    if status:
        query = query.eq("status", status)
    return query.order("created_at", desc=True).execute().data or []

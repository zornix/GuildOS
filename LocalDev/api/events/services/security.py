"""Security assignments + swap requests — service layer (no FastAPI imports).

Spec §2.5 (Security), §2.7 (swap notifications), plan docs/imp-ev-ph4.md.

D12: a security assignment IS a `tasks` row (`kind='security'`) plus a
pre-created active commitment (the source of truth for the holder). D13: swaps
are `security_swap_requests` rows resolved by one atomic RPC. D14: the manage
gate reuses `_require_supervisor_manage` (supervisor OR calendar:event:update)
from `services/events.py`; swap request/accept/decline are identity-gated inside
the RPCs, so those service methods carry no permission check (any authenticated
member may be a swap target). Multi-row mutations go through the ev_* RPCs.
"""

from __future__ import annotations

from api.events.db.rpc import call_rpc
from api.events.services.events import (
    EventNotFound,  # noqa: F401  (re-exported for route error mapping)
    NotPermitted,   # noqa: F401  (re-exported for route error mapping)
    _get_event_row,
    _require_supervisor_manage,
)


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _swap_out(row: dict) -> dict:
    """Normalize a security_swap_requests DB row to the SwapOut shape."""
    return {
        "id": str(row["id"]),
        "task_id": str(row["task_id"]),
        "event_id": str(row["event_id"]),
        "requester_member_id": str(row["requester_member_id"]),
        "target_member_id": str(row["target_member_id"]),
        "note": row.get("note"),
        "status": row["status"],
        "created_at": _iso(row.get("created_at")),
    }


# ── Reads ────────────────────────────────────────────────────────────────────

def list_security(sb, *, chapter_id: str, event_id: str) -> list[dict]:
    """Security roster for an event (spec Screen 3 read view).

    Each non-cancelled security task decorated with its active-commitment holder,
    the task status/rejection_reason, and the pending swap (if any).
    """
    _get_event_row(sb, chapter_id=chapter_id, event_id=event_id)  # 404 on cross-tenant/missing

    tasks = (
        sb.table("tasks")
        .select("id, event_id, status, rejection_reason, kind")
        .eq("chapter_id", chapter_id)
        .eq("event_id", event_id)
        .eq("kind", "security")
        .execute()
    ).data or []

    roster = []
    for t in tasks:
        if t.get("status") == "cancelled":
            continue
        holder = (
            sb.table("task_commitments")
            .select("member_id")
            .eq("task_id", t["id"])
            .eq("status", "active")
            .execute()
        ).data or []
        pending = (
            sb.table("security_swap_requests")
            .select("*")
            .eq("task_id", t["id"])
            .eq("status", "pending")
            .execute()
        ).data or []
        roster.append({
            "task_id": str(t["id"]),
            "event_id": str(t["event_id"]),
            "member_id": str(holder[0]["member_id"]) if holder else None,
            "status": t["status"],
            "rejection_reason": t.get("rejection_reason"),
            "pending_swap": _swap_out(pending[0]) if pending else None,
        })
    return roster


def list_my_swaps(sb, *, chapter_id: str, member_id: str) -> dict:
    """Pending swaps involving `member_id`: incoming (I'm the target) and
    outgoing (I'm the requester). For the Phase 5 swap inbox."""
    incoming = (
        sb.table("security_swap_requests")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("status", "pending")
        .eq("target_member_id", member_id)
        .execute()
    ).data or []
    outgoing = (
        sb.table("security_swap_requests")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("status", "pending")
        .eq("requester_member_id", member_id)
        .execute()
    ).data or []
    return {
        "incoming": [_swap_out(r) for r in incoming],
        "outgoing": [_swap_out(r) for r in outgoing],
    }


# ── Supervisor-gated mutations (D14 manage gate) ─────────────────────────────

def assign_security(
    sb, *, actor: dict, event_id: str, member_id: str,
    idempotency_key: str | None = None,
) -> dict:
    """Pre-assign a member to security. Manage gate = supervisor of the event
    OR calendar:event:update (reused from services/events.py)."""
    chapter_id = actor["chapter_id"]
    _get_event_row(sb, chapter_id=chapter_id, event_id=event_id)  # 404 on missing
    _require_supervisor_manage(sb, actor=actor, event_id=event_id)

    result = call_rpc(
        "ev_assign_security",
        {
            "p_chapter_id": chapter_id,
            "p_event_id": event_id,
            "p_member_id": member_id,
            "p_actor_id": actor["id"],
            "p_title": None,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    ).data

    task = result["task"]
    commitment = result["commitment"]
    return {
        "task_id": str(task["id"]),
        "event_id": str(task["event_id"]),
        "member_id": str(commitment["member_id"]),
        "status": task["status"],
        "rejection_reason": task.get("rejection_reason"),
        "pending_swap": None,
    }


def remove_security(
    sb, *, actor: dict, event_id: str, task_id: str,
    idempotency_key: str | None = None,
) -> dict:
    """Remove a security assignment. Same manage gate as assign. 404 when the
    task is not a security assignment of this event."""
    chapter_id = actor["chapter_id"]
    _get_event_row(sb, chapter_id=chapter_id, event_id=event_id)
    _require_supervisor_manage(sb, actor=actor, event_id=event_id)

    task = (
        sb.table("tasks")
        .select("id, event_id, kind")
        .eq("id", task_id)
        .eq("chapter_id", chapter_id)
        .maybe_single()
        .execute()
    ).data
    if not task or task.get("kind") != "security" or str(task.get("event_id")) != str(event_id):
        raise EventNotFound("Security assignment not found for this event")

    return call_rpc(
        "ev_remove_security",
        {
            "p_chapter_id": chapter_id,
            "p_task_id": task_id,
            "p_actor_id": actor["id"],
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    ).data


# ── Identity-gated swap flow (guards live in the RPCs, no permission check) ───

def request_swap(
    sb, *, actor: dict, task_id: str, target_member_id: str,
    note: str | None = None, idempotency_key: str | None = None,
) -> dict:
    return call_rpc(
        "ev_request_security_swap",
        {
            "p_chapter_id": actor["chapter_id"],
            "p_task_id": task_id,
            "p_target_member_id": target_member_id,
            "p_actor_id": actor["id"],
            "p_note": note,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    ).data


def accept_swap(
    sb, *, actor: dict, swap_id: str, idempotency_key: str | None = None,
) -> dict:
    return call_rpc(
        "ev_accept_security_swap",
        {
            "p_chapter_id": actor["chapter_id"],
            "p_swap_id": swap_id,
            "p_actor_id": actor["id"],
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    ).data


def decline_swap(
    sb, *, actor: dict, swap_id: str, idempotency_key: str | None = None,
) -> dict:
    return call_rpc(
        "ev_decline_security_swap",
        {
            "p_chapter_id": actor["chapter_id"],
            "p_swap_id": swap_id,
            "p_actor_id": actor["id"],
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    ).data

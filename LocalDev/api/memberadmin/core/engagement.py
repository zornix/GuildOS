"""Shared attendance, excuse, and fine aggregates for MemberAdmin features."""

from __future__ import annotations

from dataclasses import dataclass

from api.platform.db import get_db


@dataclass(frozen=True)
class MemberEngagement:
    member_id: str
    name: str
    email: str
    role: str | None
    attended: int
    excused: int
    missed: int
    total_required: int
    unpaid_fines: int
    unpaid_amount_cents: int


async def load_member_engagement(
    chapter_id: str,
    *,
    include_role: bool = False,
) -> list[MemberEngagement]:
    sb = get_db()

    member_fields = "id, name, email" + (", role" if include_role else "")
    query = (
        sb.table("members")
        .select(member_fields)
        .eq("chapter_id", chapter_id)
        .eq("status", "active")
    )
    if include_role:
        query = query.order("name")
    members = query.execute().data

    required_events = (
        sb.table("events")
        .select("id")
        .eq("chapter_id", chapter_id)
        .eq("required", True)
        .lte("date", "now()")
        .execute()
    ).data

    if not required_events:
        return [
            MemberEngagement(
                member_id=m["id"],
                name=m["name"],
                email=m["email"],
                role=m.get("role") if include_role else None,
                attended=0,
                excused=0,
                missed=0,
                total_required=0,
                unpaid_fines=0,
                unpaid_amount_cents=0,
            )
            for m in members
        ]

    event_ids = [e["id"] for e in required_events]
    total_required = len(event_ids)

    attendance = (
        sb.table("attendance")
        .select("member_id, event_id")
        .in_("event_id", event_ids)
        .eq("checked_in", True)
        .execute()
    ).data

    excuses = (
        sb.table("excuses")
        .select("member_id, event_id")
        .in_("event_id", event_ids)
        .eq("status", "approved")
        .execute()
    ).data

    fines = (
        sb.table("unpaid_invoices")
        .select("member_id, amount_cents")
        .eq("chapter_id", chapter_id)
        .eq("kind", "fine")
        .eq("status", "unpaid")
        .execute()
    ).data

    att_by_member: dict[str, set[str]] = {}
    for row in attendance:
        att_by_member.setdefault(row["member_id"], set()).add(row["event_id"])

    exc_by_member: dict[str, set[str]] = {}
    for row in excuses:
        exc_by_member.setdefault(row["member_id"], set()).add(row["event_id"])

    fines_by_member: dict[str, list[dict]] = {}
    for row in fines:
        fines_by_member.setdefault(row["member_id"], []).append(row)

    results: list[MemberEngagement] = []
    for member in members:
        mid = member["id"]
        attended = att_by_member.get(mid, set())
        excused = exc_by_member.get(mid, set()) - attended
        missed = max(total_required - len(attended) - len(excused), 0)
        member_fines = fines_by_member.get(mid, [])

        results.append(
            MemberEngagement(
                member_id=mid,
                name=member["name"],
                email=member["email"],
                role=member.get("role") if include_role else None,
                attended=len(attended),
                excused=len(excused),
                missed=missed,
                total_required=total_required,
                unpaid_fines=len(member_fines),
                unpaid_amount_cents=sum(f["amount_cents"] for f in member_fines),
            )
        )

    return results

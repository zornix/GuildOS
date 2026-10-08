"""Shared attendance, excuse, and fine aggregates for MemberAdmin features."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from api.events.core.timing import chapter_timezone, has_started

from api.platform.db import get_db
from api.treasury.services.remaining import remaining_by_invoice


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


def load_member_engagement(
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

    now = datetime.now(timezone.utc)
    tz = chapter_timezone(sb, chapter_id)
    required_events = (
        sb.table("events")
        .select("id, date, time")
        .eq("chapter_id", chapter_id)
        .eq("required", True)
        .lte("date", (now + timedelta(days=1)).date().isoformat())
        .execute()
    ).data

    required_events = [e for e in required_events if has_started(e, tz, now)]

    event_ids = [e["id"] for e in required_events]
    total_required = len(event_ids)

    attendance = excuses = []
    if event_ids:
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
        .select("id, member_id, amount_cents")
        .eq("chapter_id", chapter_id)
        .eq("kind", "fine")
        .in_("status", ["unpaid", "partially_paid"])
        .execute()
    ).data

    remaining = remaining_by_invoice(sb, fines)
    fines = [f for f in fines if remaining[f["id"]] > 0]

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
                unpaid_amount_cents=sum(remaining[f["id"]] for f in member_fines),
            )
        )

    return results

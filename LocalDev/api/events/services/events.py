"""Events service layer — business logic, no FastAPI imports.

Multi-row trust-boundary mutations go through the ev_* plpgsql RPCs (0101);
single-row reads are plain queries. Authorization is decided here via
has_permission / CHAIR_ROLES so route handlers stay thin and role strings
never leak into them.
"""

from __future__ import annotations

from api.events.notifications import notify_event_created, notify_role_assigned
from api.events.auth import CHAIR_ROLES, EVENT_UPDATE, OFFICER_ROLES, OFFICER_VIEW
from api.events.core.rules import (
    DEFAULT_EVENT_TYPES,
    completeness,
    organizers_needed,
    resolve_visibility,
)
from api.platform.rpc import call_rpc
from api.rbac.services.permissions import get_member_permissions, has_permission


class EventsError(Exception):
    """Base class for events domain errors."""


class EventNotFound(EventsError):
    """Event missing — or not visible to the caller (no existence leak)."""


class NotPermitted(EventsError):
    """Caller lacks the permission for this mutation (HTTP 403)."""


class NotEligible(EventsError):
    """Target member fails an eligibility rule, e.g. supervisor chair (HTTP 422)."""


class InvalidTimeRange(EventsError):
    """Event end is not strictly after its start (HTTP 422)."""


class SupervisorRuleViolation(EventsError):
    """Creator/min-1 supervisor invariant would be violated (HTTP 409)."""


# ── Event types ────────────────────────────────────────────────────────────────

def ensure_default_event_types(sb, *, chapter_id: str) -> None:
    """Get-or-seed the default types for chapters created after migration 0100."""
    existing = (
        sb.table("event_types").select("id").eq("chapter_id", chapter_id).execute()
    ).data or []
    if existing:
        return
    for name in DEFAULT_EVENT_TYPES:
        sb.table("event_types").insert(
            {"chapter_id": chapter_id, "name": name}, ignore_conflict=True
        ).execute()


def list_event_types(sb, *, chapter_id: str) -> list[dict]:
    ensure_default_event_types(sb, chapter_id=chapter_id)
    return (
        sb.table("event_types")
        .select("*")
        .eq("chapter_id", chapter_id)
        .order("name")
        .execute()
    ).data or []


def resolve_event_type_id(
    sb, *, chapter_id: str, name: str, actor_id: str | None = None
) -> str:
    """Case-insensitive match against existing types, else create a new one."""
    wanted = name.strip()
    types = list_event_types(sb, chapter_id=chapter_id)
    for t in types:
        if t["name"].strip().lower() == wanted.lower():
            return t["id"]
    created = (
        sb.table("event_types")
        .insert(
            {"chapter_id": chapter_id, "name": wanted, "created_by": actor_id},
            ignore_conflict=True,
        )
        .execute()
    ).data
    if created:
        return created[0]["id"]
    # A skipped insert lost the race; re-read without aborting the transaction.
    for t in list_event_types(sb, chapter_id=chapter_id):
        if t["name"].strip().lower() == wanted.lower():
            return t["id"]
    raise EventsError("Event type could not be resolved")


# ── Reads & decoration ─────────────────────────────────────────────────────────

def _organizers_for_event(sb, event_id: str) -> list[dict]:
    return (
        sb.table("event_organizers")
        .select("id, member_id, source, created_at")
        .eq("event_id", event_id)
        .execute()
    ).data or []


def _supervisors_for_event(sb, event_id: str) -> list[dict]:
    """Supervisor rows for an event as SupervisorOut-shaped dicts (with names)."""
    rows = (
        sb.table("event_supervisors")
        .select("member_id, is_creator, created_at")
        .eq("event_id", event_id)
        .order("created_at")
        .execute()
    ).data or []
    names = _member_names(sb, [r["member_id"] for r in rows])
    return [
        {
            "member_id": str(r["member_id"]),
            "is_creator": bool(r["is_creator"]),
            "name": names.get(str(r["member_id"])),
        }
        for r in rows
    ]


def _member_names(sb, member_ids: list[str]) -> dict[str, str]:
    ids = [str(m) for m in member_ids if m]
    if not ids:
        return {}
    rows = (
        sb.table("members").select("id, name").in_("id", ids).execute()
    ).data or []
    return {str(r["id"]): r.get("name") for r in rows}


def _decorate_supervisors(sb, event: dict) -> dict:
    event["supervisors"] = _supervisors_for_event(sb, event["id"])
    return event


_OPEN_JOB_STATUSES = {"open", "in_progress"}


def _job_counts_for_event(sb, event_id: str) -> tuple[int, int]:
    """(job_count, open_job_count) for an event's non-cancelled jobs (tasks).

    job_count feeds the notify-gate completeness check; jobs are
    part of the tasks domain — never a separate checklist.
    """
    rows = (
        sb.table("tasks")
        .select("status, kind")
        .eq("event_id", event_id)
        .execute()
    ).data or []
    # Security jobs (kind='security') are pre-assigned and not claimable —
    # they must not count toward the notify gate or the job decorations.
    non_cancelled = [
        r for r in rows
        if r.get("status") != "cancelled" and r.get("kind") != "security"
    ]
    open_count = sum(1 for r in non_cancelled if r.get("status") in _OPEN_JOB_STATUSES)
    return len(non_cancelled), open_count


def _last_notified_at(sb, event_id: str) -> str | None:
    """Most recent notify blast timestamp, or None if never notified.

    Derived from the append-only event_notification_sends log rather than a
    mutable column.
    """
    rows = (
        sb.table("event_notification_sends")
        .select("created_at")
        .eq("event_id", event_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data or []
    return rows[0]["created_at"] if rows else None


def _resolve_end_date(
    *, date: str, time: str, end_date: str | None, end_time: str | None
) -> str | None:
    """An end time at or before the start with no end date means "past midnight":
    the event ends the next day. The UI only ever sends an end time."""
    if end_date or not end_time:
        return end_date
    from datetime import date as _date, time as _time, timedelta

    if _time.fromisoformat(end_time) <= _time.fromisoformat(time):
        return (_date.fromisoformat(date) + timedelta(days=1)).isoformat()
    return None


def _validate_time_range(
    *, date: str, time: str, end_date: str | None, end_time: str | None
) -> None:
    """end must be strictly after start when provided; end_date defaults to date."""
    if end_time is None and end_date is None:
        return
    from datetime import date as _date, datetime as _dt, time as _time

    start = _dt.combine(_date.fromisoformat(date), _time.fromisoformat(time))
    e_date = _date.fromisoformat(end_date) if end_date else _date.fromisoformat(date)
    e_time = _time.fromisoformat(end_time) if end_time else _time(0, 0)
    if _dt.combine(e_date, e_time) <= start:
        raise InvalidTimeRange("Event end must be after its start")


def _decorate_counts(event: dict, organizer_count: int) -> dict:
    event["organizer_count"] = organizer_count
    event["organizers_needed"] = organizers_needed(organizer_count)
    event["group_id"] = event.get("event_group_id")
    return event


def _can_view(sb, user: dict, event: dict, *, granted: set[str] | None = None) -> bool:
    if event.get("cancelled"):
        return False
    if event.get("visibility", "chapter") == "chapter":
        return True
    uid = user["id"]
    if uid == event.get("created_by"):
        return True
    supervisor = (
        sb.table("event_supervisors")
        .select("id")
        .eq("event_id", event["id"])
        .eq("member_id", uid)
        .execute()
    ).data
    if supervisor:
        return True
    if granted is None:
        granted = get_member_permissions(user, sb=sb)
    if OFFICER_VIEW in granted:
        return True
    organizer = (
        sb.table("event_organizers")
        .select("id")
        .eq("event_id", event["id"])
        .eq("member_id", uid)
        .execute()
    ).data
    if organizer:
        return True
    if event.get("visibility") == "custom":
        audience = (
            sb.table("event_audience_members")
            .select("id")
            .eq("event_id", event["id"])
            .eq("member_id", uid)
            .execute()
        ).data
        return bool(audience)
    return False


def list_events(sb, *, user: dict, upcoming: bool = True) -> list[dict]:
    """Chapter events the caller may see, with organizer flags (additive fields)."""
    rows = (
        sb.table("events")
        .select("*")
        .eq("chapter_id", user["chapter_id"])
        .eq("cancelled", False)
        .order("date", desc=not upcoming)
        .execute()
    ).data or []
    if not rows:
        return []

    granted = get_member_permissions(user, sb=sb)
    uid = user["id"]

    if OFFICER_VIEW in granted:
        visible = rows
    else:
        org_event_ids = {
            r["event_id"]
            for r in (
                sb.table("event_organizers")
                .select("event_id")
                .eq("chapter_id", user["chapter_id"])
                .eq("member_id", uid)
                .execute()
            ).data
            or []
        }
        sup_event_ids = {
            r["event_id"]
            for r in (
                sb.table("event_supervisors")
                .select("event_id")
                .eq("chapter_id", user["chapter_id"])
                .eq("member_id", uid)
                .execute()
            ).data
            or []
        }
        aud_event_ids = {
            r["event_id"]
            for r in (
                sb.table("event_audience_members")
                .select("event_id")
                .eq("chapter_id", user["chapter_id"])
                .eq("member_id", uid)
                .execute()
            ).data
            or []
        }
        visible = [
            e
            for e in rows
            if e.get("visibility", "chapter") == "chapter"
            or uid == e.get("created_by")
            or e["id"] in sup_event_ids
            or e["id"] in org_event_ids
            or (e.get("visibility") == "custom" and e["id"] in aud_event_ids)
        ]

    counts: dict[str, int] = {}
    sup_counts: dict[str, int] = {}
    job_counts: dict[str, int] = {}
    open_job_counts: dict[str, int] = {}
    event_ids = [e["id"] for e in visible]
    if event_ids:
        organizer_rows = (
            sb.table("event_organizers")
            .select("event_id")
            .in_("event_id", event_ids)
            .execute()
        ).data or []
        for r in organizer_rows:
            counts[r["event_id"]] = counts.get(r["event_id"], 0) + 1

        supervisor_rows = (
            sb.table("event_supervisors")
            .select("event_id")
            .in_("event_id", event_ids)
            .execute()
        ).data or []
        for r in supervisor_rows:
            sup_counts[r["event_id"]] = sup_counts.get(r["event_id"], 0) + 1

        task_rows = (
            sb.table("tasks")
            .select("event_id, status, kind")
            .in_("event_id", event_ids)
            .execute()
        ).data or []
        for r in task_rows:
            if r.get("status") == "cancelled" or r.get("kind") == "security":
                continue
            job_counts[r["event_id"]] = job_counts.get(r["event_id"], 0) + 1
            # The "N open jobs" claim lure — same filter as
            # job_count, narrowed to the claimable statuses.
            if r.get("status") in _OPEN_JOB_STATUSES:
                open_job_counts[r["event_id"]] = open_job_counts.get(r["event_id"], 0) + 1

    decorated = []
    for e in visible:
        organizer_count = counts.get(e["id"], 0)
        _decorate_counts(e, organizer_count)
        job_count = job_counts.get(e["id"], 0)
        e["job_count"] = job_count
        e["open_job_count"] = open_job_counts.get(e["id"], 0)
        e["completeness"] = completeness(
            supervisor_count=sup_counts.get(e["id"], 0),
            organizer_count=organizer_count,
            job_count=job_count,
        )
        decorated.append(e)
    return decorated


def get_event(sb, *, user: dict, event_id: str) -> dict:
    """Single event with attendance count, organizers, and group siblings.

    Raises EventNotFound both for missing and for not-visible events.
    """
    event = (
        sb.table("events")
        .select("*")
        .eq("id", event_id)
        .eq("chapter_id", user["chapter_id"])
        .eq("cancelled", False)
        .maybe_single()
        .execute()
    ).data
    if not event:
        raise EventNotFound(f"Event {event_id} not found")
    if not _can_view(sb, user, event):
        raise EventNotFound(f"Event {event_id} not found")

    att = (
        sb.table("attendance")
        .select("id", count="exact")
        .eq("event_id", event_id)
        .eq("checked_in", True)
        .execute()
    )
    event["attendance_count"] = att.count

    organizers = _organizers_for_event(sb, event_id)
    event["organizers"] = organizers
    _decorate_counts(event, len(organizers))
    _decorate_supervisors(sb, event)

    job_count, open_job_count = _job_counts_for_event(sb, event_id)
    event["job_count"] = job_count
    event["open_job_count"] = open_job_count
    event["completeness"] = completeness(
        supervisor_count=len(event["supervisors"]),
        organizer_count=len(organizers),
        job_count=job_count,
    )
    event["last_notified_at"] = _last_notified_at(sb, event_id)

    event["group_events"] = []
    if event.get("event_group_id"):
        siblings = (
            sb.table("events")
            .select("id, title, date")
            .eq("event_group_id", event["event_group_id"])
            .eq("chapter_id", user["chapter_id"])
            .eq("cancelled", False)
            .order("date")
            .execute()
        ).data or []
        event["group_events"] = [s for s in siblings if s["id"] != event_id]

    return event


def list_upcoming_details(sb, *, user: dict) -> dict:
    """Detail, security roster and check-in link for every upcoming event the
    caller may see, in a fixed number of queries (F-044).

    Each part matches its single-event route (get_event, list_security,
    GET /{id}/checkin-link) for the same caller; visibility is list_events'.
    """
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    from api.attendance.auth import CHECKIN_LINK_MANAGE
    from api.config import settings
    from api.events.core.timing import chapter_timezone

    chapter_id = user["chapter_id"]
    today = datetime.now(ZoneInfo(chapter_timezone(sb, chapter_id))).date().isoformat()
    events = [e for e in list_events(sb, user=user) if str(e["date"]) >= today]
    if not events:
        return {"events": []}
    ids = [e["id"] for e in events]

    def rows(table: str, columns: str, column: str, values: list, **eq) -> list[dict]:
        q = sb.table(table).select(columns).in_(column, values)
        for k, v in eq.items():
            q = q.eq(k, v)
        return q.execute().data or []

    def group(items: list[dict], key: str) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for r in items:
            out.setdefault(str(r[key]), []).append(r)
        return out

    checked_in = group(rows("attendance", "event_id", "event_id", ids, checked_in=True), "event_id")
    organizers = group(
        rows("event_organizers", "id, member_id, source, created_at, event_id", "event_id", ids),
        "event_id",
    )
    sup_rows = (
        sb.table("event_supervisors")
        .select("event_id, member_id, is_creator, created_at")
        .in_("event_id", ids)
        .order("created_at")
        .execute()
    ).data or []
    names = _member_names(sb, [r["member_id"] for r in sup_rows])
    supervisors = group(sup_rows, "event_id")
    sends = (
        sb.table("event_notification_sends")
        .select("event_id, created_at")
        .in_("event_id", ids)
        .order("created_at", desc=True)
        .execute()
    ).data or []
    last_sent: dict[str, str] = {}
    for r in sends:
        last_sent.setdefault(str(r["event_id"]), r["created_at"])
    group_ids = list({e["event_group_id"] for e in events if e.get("event_group_id")})
    siblings = group(
        (
            sb.table("events")
            .select("id, title, date, event_group_id")
            .in_("event_group_id", group_ids)
            .eq("chapter_id", chapter_id)
            .eq("cancelled", False)
            .order("date")
            .execute()
        ).data or [] if group_ids else [],
        "event_group_id",
    )

    # Security roster: same filters and shape as services/security.list_security.
    from api.events.services.security import _swap_out

    sec_tasks = [
        t for t in rows(
            "tasks", "id, event_id, status, rejection_reason, kind", "event_id", ids,
            chapter_id=chapter_id, kind="security",
        )
        if t.get("status") != "cancelled"
    ]
    task_ids = [t["id"] for t in sec_tasks]
    holders = group(
        rows("task_commitments", "task_id, member_id", "task_id", task_ids, status="active")
        if task_ids else [],
        "task_id",
    )
    swaps = group(
        rows("security_swap_requests", "*", "task_id", task_ids, status="pending")
        if task_ids else [],
        "task_id",
    )
    security = group(
        [
            {
                "task_id": str(t["id"]),
                "event_id": str(t["event_id"]),
                "member_id": str(holders[str(t["id"])][0]["member_id"]) if str(t["id"]) in holders else None,
                "status": t["status"],
                "rejection_reason": t.get("rejection_reason"),
                "pending_swap": _swap_out(swaps[str(t["id"])][0]) if str(t["id"]) in swaps else None,
            }
            for t in sec_tasks
        ],
        "event_id",
    )

    # Match the attendance service's bound-session and legacy unbound gates.
    # Duplicate this small predicate here to avoid importing a private service helper.
    now = datetime.now(timezone.utc)
    sessions = rows("attendance_sessions", "id, event_id, checkin_link_id, closes_at", "event_id", ids)

    def open_link(row: dict) -> bool:
        event_sessions = [s for s in sessions if str(s["event_id"]) == str(row["event_id"])]
        bound = [s for s in event_sessions if str(s.get("checkin_link_id") or "") == str(row["id"])]
        def closed(session: dict) -> bool:
            value = session.get("closes_at")
            if isinstance(value, str):
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if value is not None and value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value is not None and now > value
        if bound:
            return len(bound) == 1 and not closed(bound[0])
        unbound = [s for s in event_sessions if not s.get("checkin_link_id") and not closed(s)]
        return len(unbound) <= 1

    links = group(
        [row for row in (
            sb.table("checkin_links")
            .select("id, event_id, short_code, expires_at, active")
            .in_("event_id", ids)
            .eq("active", True)
            .gte("expires_at", now.isoformat())
            .execute()
        ).data or [] if open_link(row)],
        "event_id",
    )
    can_manage = bool(links) and has_permission(user, CHECKIN_LINK_MANAGE, sb=sb)

    def link_for(eid: str) -> dict:
        if eid not in links:
            return {}
        row = links[eid][0]
        if not can_manage:
            return {"event_id": row["event_id"], "active": True, "expires_at": row["expires_at"]}
        return {
            "short_code": row["short_code"],
            "url": f"{settings.BASE_URL}/c/{row['short_code']}",
            "expires_at": row["expires_at"],
            "event_id": row["event_id"],
        }

    out = []
    for e in events:
        eid = str(e["id"])
        e["attendance_count"] = len(checked_in.get(eid, []))
        e["organizers"] = [
            {k: r[k] for k in ("id", "member_id", "source", "created_at")}
            for r in organizers.get(eid, [])
        ]
        e["supervisors"] = [
            {
                "member_id": str(r["member_id"]),
                "is_creator": bool(r["is_creator"]),
                "name": names.get(str(r["member_id"])),
            }
            for r in supervisors.get(eid, [])
        ]
        e["last_notified_at"] = last_sent.get(eid)
        e["group_events"] = [
            {k: s[k] for k in ("id", "title", "date")}
            for s in siblings.get(str(e.get("event_group_id")), [])
            if str(s["id"]) != eid
        ] if e.get("event_group_id") else []
        out.append({
            "event_id": eid,
            "detail": e,
            "security": security.get(eid, []),
            "checkin_link": link_for(eid),
        })
    return {"events": out}


def _get_event_row(sb, *, chapter_id: str, event_id: str) -> dict:
    event = (
        sb.table("events")
        .select("*")
        .eq("id", event_id)
        .eq("chapter_id", chapter_id)
        .eq("cancelled", False)
        .maybe_single()
        .execute()
    ).data
    if not event:
        raise EventNotFound(f"Event {event_id} not found")
    return event


# ── Mutations (ev_* RPCs) ──────────────────────────────────────────────────────

def create_event(
    sb,
    *,
    actor: dict,
    title: str,
    date: str,
    time: str,
    location: str,
    end_date: str | None = None,
    end_time: str | None = None,
    invite_link: str | None = None,
    description: str | None = None,
    required: bool = False,
    finable: bool = False,
    fine_amount: float = 0.0,
    event_type: str | None = None,
    event_type_name: str | None = None,
    visibility: str | None = None,
    audience: str | None = None,
    audience_member_ids: list[str] | None = None,
    event_group_id: str | None = None,
    group_with_event_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    chapter_id = actor["chapter_id"]
    end_date = _resolve_end_date(
        date=str(date), time=str(time),
        end_date=str(end_date) if end_date else None,
        end_time=str(end_time) if end_time else None,
    )
    _validate_time_range(
        date=str(date), time=str(time),
        end_date=end_date,
        end_time=str(end_time) if end_time else None,
    )
    resolved_visibility = resolve_visibility(audience=audience, visibility=visibility)

    event_type_id = None
    if event_type_name:
        event_type_id = resolve_event_type_id(
            sb, chapter_id=chapter_id, name=event_type_name, actor_id=actor["id"]
        )

    result = call_rpc(
        "ev_create_event",
        {
            "p_chapter_id": chapter_id,
            "p_title": title,
            "p_description": description,
            "p_date": str(date),
            "p_time": str(time),
            "p_location": location,
            "p_required": required,
            "p_finable": finable,
            "p_fine_amount": fine_amount,
            "p_event_type": event_type or event_type_name,
            "p_event_type_id": event_type_id,
            "p_visibility": resolved_visibility,
            "p_event_group_id": event_group_id,
            "p_group_with_event_id": group_with_event_id,
            "p_audience_member_ids": audience_member_ids,
            "p_actor_id": actor["id"],
            "p_idempotency_key": idempotency_key,
            "p_end_date": str(end_date) if end_date else None,
            "p_end_time": str(end_time) if end_time else None,
            "p_invite_link": invite_link,
        },
        sb=sb,
    )
    event = _decorate_counts(result.data, 0)
    notify_event_created(sb, chapter_id=chapter_id, event=result.data)
    return _decorate_supervisors(sb, event)


def update_event(
    sb,
    *,
    actor: dict,
    event_id: str,
    updates: dict,
    idempotency_key: str | None = None,
) -> dict:
    """Commit event fields, event type, and custom audience together."""
    chapter_id = actor["chapter_id"]
    existing = _get_event_row(sb, chapter_id=chapter_id, event_id=event_id)

    updates = dict(updates)
    audience = updates.pop("audience", None)
    audience_member_ids = updates.pop("audience_member_ids", None)
    event_type_name = updates.pop("event_type_name", None)

    with sb.transaction() as tx:
        if event_type_name:
            updates["event_type_id"] = resolve_event_type_id(
                tx, chapter_id=chapter_id, name=event_type_name, actor_id=actor["id"]
            )
            updates.setdefault("event_type", event_type_name)
        if audience:
            updates["visibility"] = resolve_visibility(audience=audience, visibility=None)
        for key in ("date", "time", "end_date", "end_time"):
            if key in updates and updates[key] is not None:
                updates[key] = str(updates[key])

        # Validate the effective range (merge incoming fields over the stored row).
        def _eff(field: str):
            val = updates.get(field, existing.get(field))
            return str(val) if val is not None else None

        if any(k in updates for k in ("date", "time", "end_date", "end_time")):
            eff_date, eff_time = _eff("date"), _eff("time")
            if eff_date and eff_time:
                # An end date the caller didn't send is recomputed, so a stored
                # next-day date follows the event when it moves.
                updates["end_date"] = _resolve_end_date(
                    date=eff_date, time=eff_time,
                    end_date=updates.get("end_date"), end_time=_eff("end_time"),
                )
                _validate_time_range(
                    date=eff_date, time=eff_time,
                    end_date=updates["end_date"], end_time=_eff("end_time"),
                )

        if updates:
            (
                tx.table("events")
                .update(updates)
                .eq("id", event_id)
                .eq("chapter_id", chapter_id)
                .execute()
            )

        if audience == "custom" and audience_member_ids is not None:
            call_rpc(
                "ev_set_audience",
                {
                    "p_chapter_id": chapter_id,
                    "p_event_id": event_id,
                    "p_audience_member_ids": audience_member_ids,
                    "p_actor_id": actor["id"],
                    "p_idempotency_key": idempotency_key,
                },
                sb=tx,
            )

    event = _get_event_row(sb, chapter_id=chapter_id, event_id=event_id)
    _decorate_counts(event, len(_organizers_for_event(sb, event_id)))
    return _decorate_supervisors(sb, event)


def _actor_is_supervisor(sb, *, event_id: str, member_id: str) -> bool:
    return bool(
        (
            sb.table("event_supervisors")
            .select("id")
            .eq("event_id", event_id)
            .eq("member_id", member_id)
            .execute()
        ).data
    )


def _require_supervisor_manage(sb, *, actor: dict, event_id: str) -> None:
    """Managing supervisors: be a current supervisor OR hold calendar:event:update."""
    if _actor_is_supervisor(sb, event_id=event_id, member_id=actor["id"]):
        return
    if has_permission(actor, EVENT_UPDATE, sb=sb):
        return
    raise NotPermitted(
        "Managing supervisors requires being a supervisor of this event "
        "or holding calendar:event:update"
    )


def add_supervisor(sb, *, actor: dict, event_id: str, member_id: str,
                   idempotency_key: str | None = None) -> dict:
    """Add a co-supervisor. Target must hold an officer role."""
    chapter_id = actor["chapter_id"]
    event = _get_event_row(sb, chapter_id=chapter_id, event_id=event_id)
    _require_supervisor_manage(sb, actor=actor, event_id=event_id)

    officer_rows = (
        sb.table("member_roles")
        .select("role_key")
        .eq("chapter_id", chapter_id)
        .eq("member_id", member_id)
        .in_("role_key", list(OFFICER_ROLES))
        .execute()
    ).data or []
    if not officer_rows:
        raise NotEligible("Co-supervisor must hold an officer role")

    result = call_rpc(
        "ev_add_supervisor",
        {
            "p_chapter_id": chapter_id,
            "p_event_id": event_id,
            "p_member_id": member_id,
            "p_required_role_keys": list(OFFICER_ROLES),
            "p_actor_id": actor["id"],
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    notify_role_assigned(
        sb, chapter_id=chapter_id, event=event, member_id=member_id, role="supervisor",
        assignment_id=str(result.data.get("id") or result.data["created_at"])
    )
    _decorate_counts(event, len(_organizers_for_event(sb, event_id)))
    return _decorate_supervisors(sb, event)


def remove_supervisor(sb, *, actor: dict, event_id: str, member_id: str,
                      idempotency_key: str | None = None) -> dict:
    """Remove a co-supervisor. Creator/min-1 violations surface from the RPC."""
    chapter_id = actor["chapter_id"]
    event = _get_event_row(sb, chapter_id=chapter_id, event_id=event_id)
    _require_supervisor_manage(sb, actor=actor, event_id=event_id)

    try:
        call_rpc(
            "ev_remove_supervisor",
            {
                "p_chapter_id": chapter_id,
                "p_event_id": event_id,
                "p_member_id": member_id,
                "p_actor_id": actor["id"],
                "p_idempotency_key": idempotency_key,
            },
            sb=sb,
        )
    except Exception as exc:  # creator/min-1 guard violations
        msg = str(exc)
        if "creator_supervisor_locked" in msg:
            raise SupervisorRuleViolation("The creator supervisor cannot be removed") from exc
        if "last_supervisor_locked" in msg:
            raise SupervisorRuleViolation("An event must keep at least one supervisor") from exc
        raise
    _decorate_counts(event, len(_organizers_for_event(sb, event_id)))
    return _decorate_supervisors(sb, event)


def add_organizer(sb, *, actor: dict, event_id: str, member_id: str | None = None,
                  idempotency_key: str | None = None) -> dict:
    """Self-volunteer (any member) or assign (calendar:event:update)."""
    chapter_id = actor["chapter_id"]
    # Existence + tenant check, and the row the assignment notice reads below —
    # adding an organizer does not touch the event row, so one fetch is enough.
    event = _get_event_row(sb, chapter_id=chapter_id, event_id=event_id)

    target = member_id or actor["id"]
    source = "volunteer" if target == actor["id"] else "assigned"
    if source == "assigned" and not has_permission(actor, EVENT_UPDATE, sb=sb):
        raise NotPermitted(
            "Assigning organizers requires calendar:event:update; "
            "members may only volunteer themselves"
        )

    result = call_rpc(
        "ev_add_organizer",
        {
            "p_chapter_id": chapter_id,
            "p_event_id": event_id,
            "p_member_id": target,
            "p_source": source,
            "p_actor_id": actor["id"],
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    if source == "assigned":
        # A volunteer already knows; only an assignment is news.
        notify_role_assigned(
            sb,
            chapter_id=chapter_id,
            event=event,
            member_id=target,
            role="organizer",
            assignment_id=str(result.data.get("id") or result.data["created_at"]),
        )
    return result.data


def remove_organizer(sb, *, actor: dict, event_id: str, member_id: str,
                     idempotency_key: str | None = None) -> dict:
    """Self-leave (any member) or officer removal (calendar:event:update)."""
    chapter_id = actor["chapter_id"]
    _get_event_row(sb, chapter_id=chapter_id, event_id=event_id)

    if member_id != actor["id"] and not has_permission(actor, EVENT_UPDATE, sb=sb):
        raise NotPermitted(
            "Removing another organizer requires calendar:event:update"
        )

    result = call_rpc(
        "ev_remove_organizer",
        {
            "p_chapter_id": chapter_id,
            "p_event_id": event_id,
            "p_member_id": member_id,
            "p_actor_id": actor["id"],
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data

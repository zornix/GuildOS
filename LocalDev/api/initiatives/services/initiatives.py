"""Initiatives service layer — business logic, no FastAPI imports.

Multi-row trust-boundary mutations go through the in_* plpgsql RPCs (0144);
single-row reads are plain queries. Per-initiative authority is
initiative_chairs membership (is_assigned_chair), never a role string
comparison. The RPCs re-check the same membership at the trust boundary
(defense in depth) — this layer's checks exist to return clean 403s before
hitting the database mutation.
"""

from __future__ import annotations

from api.initiatives.auth import is_assigned_chair
from api.platform.rpc import call_rpc


class InitiativesError(Exception):
    """Base class for initiatives domain errors."""


class InitiativeNotFound(InitiativesError):
    """Initiative missing — or not in the caller's chapter (no existence leak)."""


class NotPermitted(InitiativesError):
    """Caller is not an assigned chair of this initiative (HTTP 403)."""


class InvalidTimeRange(InitiativesError):
    """Initiative end is not strictly after its start (HTTP 422)."""


# ponytail: the existing route maps InvalidTimeRange to 422; add a shared
# validation-error base when the initiatives route mapper can be changed.
class MemberNotActive(InvalidTimeRange):
    """Member status prevents chair assignment (HTTP 422)."""


class ChairRuleViolation(InitiativesError):
    """Min-1 chair invariant would be violated (HTTP 409)."""


class MemberNotInChapter(InitiativesError):
    """Member not in the caller's chapter (HTTP 404)."""


# ── Reads & decoration ──────────────────────────────────────────────────────

def _member_names(sb, member_ids: list[str]) -> dict[str, str]:
    ids = [str(m) for m in member_ids if m]
    if not ids:
        return {}
    rows = (
        sb.table("members").select("id, name").in_("id", ids).execute()
    ).data or []
    return {str(r["id"]): r.get("name") for r in rows}


def _chairs_for_initiative(sb, initiative_id: str) -> list[dict]:
    """Chair rows for an initiative as decorated dicts (with names)."""
    rows = (
        sb.table("initiative_chairs")
        .select("member_id, is_creator, created_at")
        .eq("initiative_id", initiative_id)
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


def _decorate_chairs(sb, initiative: dict) -> dict:
    initiative["chairs"] = _chairs_for_initiative(sb, initiative["id"])
    initiative["chair_member_ids"] = [c["member_id"] for c in initiative["chairs"]]
    return initiative


_OPEN_JOB_STATUSES = {"open", "in_progress"}


def _job_counts_for_initiative(sb, initiative_id: str) -> tuple[int, int]:
    """(job_count, open_job_count) for an initiative's non-cancelled jobs (tasks)."""
    rows = (
        sb.table("tasks")
        .select("status")
        .eq("initiative_id", initiative_id)
        .execute()
    ).data or []
    non_cancelled = [r for r in rows if r.get("status") != "cancelled"]
    open_count = sum(1 for r in non_cancelled if r.get("status") in _OPEN_JOB_STATUSES)
    return len(non_cancelled), open_count


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
        raise InvalidTimeRange("Initiative end must be after its start")


def list_initiatives(sb, *, chapter_id: str) -> list[dict]:
    """Chapter initiatives, decorated with chair ids and batched job counts."""
    rows = (
        sb.table("initiatives")
        .select("*")
        .eq("chapter_id", chapter_id)
        .order("date")
        .execute()
    ).data or []
    if not rows:
        return []

    initiative_ids = [r["id"] for r in rows]

    chairs_by_initiative: dict[str, list[str]] = {}
    chair_rows = (
        sb.table("initiative_chairs")
        .select("initiative_id, member_id")
        .in_("initiative_id", initiative_ids)
        .execute()
    ).data or []
    for r in chair_rows:
        chairs_by_initiative.setdefault(r["initiative_id"], []).append(r["member_id"])

    job_counts: dict[str, int] = {}
    open_job_counts: dict[str, int] = {}
    task_rows = (
        sb.table("tasks")
        .select("initiative_id, status")
        .in_("initiative_id", initiative_ids)
        .execute()
    ).data or []
    for r in task_rows:
        if r.get("status") == "cancelled":
            continue
        iid = r["initiative_id"]
        job_counts[iid] = job_counts.get(iid, 0) + 1
        if r.get("status") in _OPEN_JOB_STATUSES:
            open_job_counts[iid] = open_job_counts.get(iid, 0) + 1

    for row in rows:
        row["chair_member_ids"] = chairs_by_initiative.get(row["id"], [])
        row["job_count"] = job_counts.get(row["id"], 0)
        row["open_job_count"] = open_job_counts.get(row["id"], 0)
    return rows


def _get_initiative_row(sb, *, chapter_id: str, initiative_id: str) -> dict:
    initiative = (
        sb.table("initiatives")
        .select("*")
        .eq("id", initiative_id)
        .eq("chapter_id", chapter_id)
        .maybe_single()
        .execute()
    ).data
    if not initiative:
        raise InitiativeNotFound(f"Initiative {initiative_id} not found")
    return initiative


def get_initiative(sb, *, chapter_id: str, initiative_id: str) -> dict:
    """Single initiative with chairs, jobs (tasks), and job counts.

    Raises InitiativeNotFound both for missing and cross-chapter ids.
    """
    initiative = _get_initiative_row(
        sb, chapter_id=chapter_id, initiative_id=initiative_id
    )
    _decorate_chairs(sb, initiative)

    jobs = (
        sb.table("tasks")
        .select("*")
        .eq("initiative_id", initiative_id)
        .execute()
    ).data or []
    initiative["jobs"] = jobs

    job_count, open_job_count = _job_counts_for_initiative(sb, initiative_id)
    initiative["job_count"] = job_count
    initiative["open_job_count"] = open_job_count
    return initiative


# ── Mutations (in_* RPCs) ────────────────────────────────────────────────────

def create_initiative(
    sb,
    *,
    actor: dict,
    title: str,
    description: str | None = None,
    date: str,
    time: str,
    end_date: str | None = None,
    end_time: str | None = None,
    chair_member_ids: list[str] | None = None,
    idempotency_key: str | None = None,
) -> dict:
    chapter_id = actor["chapter_id"]
    _validate_time_range(
        date=str(date), time=str(time),
        end_date=str(end_date) if end_date else None,
        end_time=str(end_time) if end_time else None,
    )

    try:
        result = call_rpc(
            "in_create_initiative",
            {
                "p_chapter_id": chapter_id,
                "p_title": title,
                "p_description": description,
                "p_date": str(date),
                "p_time": str(time),
                "p_end_date": str(end_date) if end_date else None,
                "p_end_time": str(end_time) if end_time else None,
                "p_chair_member_ids": chair_member_ids or [],
                "p_actor_id": actor["id"],
                "p_idempotency_key": idempotency_key,
            },
            sb=sb,
        )
    except Exception as exc:
        if "is not an active member" in str(exc):
            raise MemberNotActive("Member must be active") from exc
        if "member_not_in_chapter" in str(exc):
            raise MemberNotInChapter("Member not found in chapter") from exc
        raise
    initiative = result.data
    return _decorate_chairs(sb, initiative)


def update_initiative(
    sb,
    *,
    actor: dict,
    initiative_id: str,
    updates: dict,
    idempotency_key: str | None = None,
) -> dict:
    """Single-row-ish update via in_update_initiative; date/time never NULL."""
    chapter_id = actor["chapter_id"]
    existing = _get_initiative_row(
        sb, chapter_id=chapter_id, initiative_id=initiative_id
    )
    if not is_assigned_chair(sb, initiative_id=initiative_id, member_id=actor["id"]):
        raise NotPermitted(
            "Updating this initiative requires being an assigned chair"
        )

    updates = dict(updates)
    for key in ("date", "time", "end_date", "end_time"):
        if key in updates and updates[key] is not None:
            updates[key] = str(updates[key])

    def _eff(field: str):
        val = updates.get(field, existing.get(field))
        return str(val) if val is not None else None

    if any(k in updates for k in ("date", "time", "end_date", "end_time")):
        eff_date, eff_time = _eff("date"), _eff("time")
        if eff_date and eff_time:
            _validate_time_range(
                date=eff_date, time=eff_time,
                end_date=_eff("end_date"), end_time=_eff("end_time"),
            )

    try:
        result = call_rpc(
            "in_update_initiative",
            {
                "p_chapter_id": chapter_id,
                "p_initiative_id": initiative_id,
                "p_title": updates.get("title"),
                "p_description": updates.get("description"),
                "p_date": updates.get("date"),
                "p_time": updates.get("time"),
                "p_end_date": updates.get("end_date"),
                "p_end_time": updates.get("end_time"),
                "p_actor_id": actor["id"],
                "p_idempotency_key": idempotency_key,
            },
            sb=sb,
        )
    except Exception as exc:  # RPC-side membership re-check (defense in depth)
        if "not_assigned_chair" in str(exc):
            raise NotPermitted(
                "Updating this initiative requires being an assigned chair"
            ) from exc
        raise
    initiative = result.data
    return _decorate_chairs(sb, initiative)


def add_chair(
    sb, *, actor: dict, initiative_id: str, member_id: str,
    idempotency_key: str | None = None,
) -> dict:
    """Add a chair. Idempotent on the UNIQUE constraint (RPC-side no-op)."""
    chapter_id = actor["chapter_id"]
    _get_initiative_row(sb, chapter_id=chapter_id, initiative_id=initiative_id)
    if not is_assigned_chair(sb, initiative_id=initiative_id, member_id=actor["id"]):
        raise NotPermitted("Managing chairs requires being an assigned chair")

    try:
        call_rpc(
            "in_add_chair",
            {
                "p_chapter_id": chapter_id,
                "p_initiative_id": initiative_id,
                "p_member_id": member_id,
                "p_actor_id": actor["id"],
                "p_idempotency_key": idempotency_key,
            },
            sb=sb,
        )
    except Exception as exc:
        msg = str(exc)
        if "is not an active member" in msg:
            raise MemberNotActive("Member must be active") from exc
        if "not_assigned_chair" in msg:
            raise NotPermitted(
                "Managing chairs requires being an assigned chair"
            ) from exc
        if "member_not_in_chapter" in msg:
            raise MemberNotInChapter("Member not found in chapter") from exc
        raise
    initiative = _get_initiative_row(
        sb, chapter_id=chapter_id, initiative_id=initiative_id
    )
    return _decorate_chairs(sb, initiative)


def remove_chair(
    sb, *, actor: dict, initiative_id: str, member_id: str,
    idempotency_key: str | None = None,
) -> dict:
    """Remove a chair. last_chair violations surface from the RPC as 409."""
    chapter_id = actor["chapter_id"]
    _get_initiative_row(sb, chapter_id=chapter_id, initiative_id=initiative_id)
    if not is_assigned_chair(sb, initiative_id=initiative_id, member_id=actor["id"]):
        raise NotPermitted("Managing chairs requires being an assigned chair")

    try:
        call_rpc(
            "in_remove_chair",
            {
                "p_chapter_id": chapter_id,
                "p_initiative_id": initiative_id,
                "p_member_id": member_id,
                "p_actor_id": actor["id"],
                "p_idempotency_key": idempotency_key,
            },
            sb=sb,
        )
    except Exception as exc:  # min-1 guard violation
        msg = str(exc)
        if "not_assigned_chair" in msg:
            raise NotPermitted(
                "Managing chairs requires being an assigned chair"
            ) from exc
        if "is not a chair" in msg:
            raise MemberNotInChapter("Chair not found") from exc
        if "last_chair" in msg:
            raise ChairRuleViolation(
                "An initiative must keep at least one chair"
            ) from exc
        raise
    initiative = _get_initiative_row(
        sb, chapter_id=chapter_id, initiative_id=initiative_id
    )
    return _decorate_chairs(sb, initiative)

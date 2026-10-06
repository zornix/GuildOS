"""Events domain rules — pure, no I/O."""

from __future__ import annotations

# Soft minimum of organizers per event. NEVER blocks creation; events
# below the minimum are publicly flagged "needs N more organizers".
# The "Organizers Needed" badge fires at 0 organizers and the notify gate needs >=1.
ORGANIZER_SOFT_MIN = 1

# Notify-gate completeness thresholds.
SUPERVISORS_COMPLETE_MIN = 1
ORGANIZERS_COMPLETE_MIN = 1
JOBS_COMPLETE_MIN = 3

# Seeded for every chapter (migration 0100 for existing chapters; the service
# layer get-or-seeds for chapters created later).
DEFAULT_EVENT_TYPES: tuple[str, ...] = (
    "Chapter Meeting",
    "Philanthropy",
    "Brotherhood",
    "Social",
)

# API audience values map onto the stored visibility.
AUDIENCE_TO_VISIBILITY: dict[str, str] = {
    "all": "chapter",
    "officers": "officer",
    "custom": "custom",
}

VISIBILITY_VALUES: tuple[str, ...] = (
    "chapter", "officer", "role_specific", "private", "custom",
)


def organizers_needed(organizer_count: int) -> int:
    return max(0, ORGANIZER_SOFT_MIN - organizer_count)


def completeness(*, supervisor_count: int, organizer_count: int, job_count: int) -> dict:
    """Notify-gate completeness: >=1 supervisor, >=1 organizer,
    >=3 jobs. Pure — the RPC (`ev_notify_event`) re-checks this server-side."""
    items = [
        {"key": "supervisors", "required": SUPERVISORS_COMPLETE_MIN, "current": supervisor_count},
        {"key": "organizers", "required": ORGANIZERS_COMPLETE_MIN, "current": organizer_count},
        {"key": "jobs", "required": JOBS_COMPLETE_MIN, "current": job_count},
    ]
    for item in items:
        item["met"] = item["current"] >= item["required"]
    return {"is_complete": all(i["met"] for i in items), "items": items}


def resolve_visibility(*, audience: str | None, visibility: str | None) -> str:
    """`audience` (all|officers|custom) wins over a raw legacy `visibility`."""
    if audience:
        return AUDIENCE_TO_VISIBILITY[audience]
    return visibility or "chapter"

"""Events domain rules — pure, no I/O."""

from __future__ import annotations

# Soft minimum of organizers per event (spec §3). NEVER blocks creation; events
# below the minimum are publicly flagged "needs N more organizers".
ORGANIZER_SOFT_MIN = 2

# Seeded for every chapter (migration 0100 for existing chapters; the service
# layer get-or-seeds for chapters created later).
DEFAULT_EVENT_TYPES: tuple[str, ...] = (
    "Chapter Meeting",
    "Philanthropy",
    "Brotherhood",
    "Social",
    "Recruitment",
)

# Resolved decision #4: API audience values map onto the stored visibility.
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


def resolve_visibility(*, audience: str | None, visibility: str | None) -> str:
    """`audience` (all|officers|custom) wins over a raw legacy `visibility`."""
    if audience:
        return AUDIENCE_TO_VISIBILITY[audience]
    return visibility or "chapter"

"""Initiatives domain permissions and per-initiative chair authority.

Chapter-level chair gating (`calendar:initiative:create` / `:update`) is a
seeded permission key granted to the six chair roles; per-initiative
authority is `initiative_chairs` membership, checked via `is_assigned_chair`
below — never a `user["role"] == ...` string comparison (hard rule).
"""

from __future__ import annotations

INITIATIVE_CREATE = "calendar:initiative:create"
INITIATIVE_UPDATE = "calendar:initiative:update"


def is_assigned_chair(sb, *, initiative_id: str, member_id: str) -> bool:
    """True when `member_id` holds an `initiative_chairs` row for `initiative_id`."""
    return bool(
        (
            sb.table("initiative_chairs")
            .select("id")
            .eq("initiative_id", initiative_id)
            .eq("member_id", member_id)
            .execute()
        ).data
    )

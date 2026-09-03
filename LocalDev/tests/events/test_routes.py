"""Route registration — new events/attendance paths are mounted (import-only)."""

from __future__ import annotations

from api.index import app


def _paths() -> set[str]:
    return {r.path for r in app.routes if hasattr(r, "path")}


def test_new_event_paths_registered():
    paths = _paths()
    for p in [
        "/api/events/types",
        "/api/events/{event_id}/supervisors",
        "/api/events/{event_id}/supervisors/{member_id}",
        "/api/events/{event_id}/organizers",
        "/api/events/{event_id}/organizers/{member_id}",
        "/api/attendance/summary",
    ]:
        assert p in paths, f"missing path: {p}"


def test_legacy_event_paths_survive():
    paths = _paths()
    for p in [
        "/api/events/",
        "/api/events/{event_id}",
        "/api/events/{event_id}/checkin-link",
    ]:
        assert p in paths, f"legacy path lost: {p}"


def test_deprecated_set_supervisor_path_is_gone():
    # Removed in #33: it added then pruned in a bare loop, so a supervisor
    # without calendar:event:update could 403 mid-loop on a half-updated event.
    assert "/api/events/{event_id}/supervisor" not in _paths()

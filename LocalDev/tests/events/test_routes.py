"""Route registration — new events/attendance paths are mounted (import-only)."""

from __future__ import annotations

from api.index import app


def _paths() -> set[str]:
    return {r.path for r in app.routes if hasattr(r, "path")}


def test_new_event_paths_registered():
    paths = _paths()
    for p in [
        "/api/events/types",
        "/api/events/{event_id}/supervisor",
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

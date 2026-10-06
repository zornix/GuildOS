"""Regression: legacy API paths survive the domain-package conformance, and the
new domain routers are mounted. Import-only — no DB needed."""

from __future__ import annotations

from api.index import app


def _paths() -> set[str]:
    return set(app.openapi()["paths"])


LEGACY_PATHS = [
    "/api/events/",
    "/api/events/{event_id}",
    "/api/events/{event_id}/checkin-link",
    "/api/attendance/checkin/{short_code}",
    "/api/attendance/event/{event_id}",
    "/api/attendance/event/{event_id}/manual/{member_id}",
    "/api/excuses/",
    "/api/excuses/{excuse_id}/review",
    "/api/fines/",
    "/api/fines/{invoice_id}/waive",
    "/api/members/",
    "/api/members/{member_id}/role",
    "/api/standing/",
    "/api/checkin-links/active",
    "/c/{short_code}",
    "/api/treasury/invoices",
]

NEW_PATHS = [
    "/api/rbac/roles",
    "/api/rbac/me/permissions",
    "/api/rbac/members/{member_id}/roles",
    "/api/attendance/sessions",
    "/api/tasks/",
    "/api/tasks/{task_id}/status",
    "/api/announcements/",
    "/api/announcements/{announcement_id}/send",
    "/api/bylaws/documents",
    "/api/bylaws/query",
    "/api/nl-controller/commands",
]


def test_legacy_paths_still_registered():
    paths = _paths()
    missing = [p for p in LEGACY_PATHS if p not in paths]
    assert not missing, f"legacy paths lost in conformance: {missing}"


def test_new_domain_paths_registered():
    paths = _paths()
    missing = [p for p in NEW_PATHS if p not in paths]
    assert not missing, f"new domain paths not mounted: {missing}"


def test_operations_api_is_unmounted():
    assert not any(path.startswith("/api/operations") for path in _paths())

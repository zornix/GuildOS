"""Initiatives HTTP-level tests (docs/imp-ev-ph3.md §5.1 items 6-8).

Mounts the real app (api.index.app) with DB access redirected to the test DB
(tests/initiatives/conftest.py::app_on_test_db), exercising route-level
require_permission gating that the RPC-level tests do not cover.
"""

from __future__ import annotations

import uuid

import pytest


# ── 6. create ─────────────────────────────────────────────────────────────────


def test_create_by_plain_member_is_403(as_member, member_factory, chapter_id):
    plain = member_factory()
    client = as_member(plain)
    resp = client.post(
        "/api/initiatives/",
        json={"title": "Bake Sale", "date": "2026-07-18", "time": "12:00"},
    )
    assert resp.status_code == 403


def test_create_by_chair_role_member_is_201_with_chairs(
    as_member, member_factory, assign_role, chapter_id
):
    chair = member_factory()
    assign_role(chair, "risk_chair")  # holds calendar:initiative:create

    client = as_member(chair)
    resp = client.post(
        "/api/initiatives/",
        json={"title": "Bake Sale", "date": "2026-07-18", "time": "12:00"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Bake Sale"
    assert chair in body["chair_member_ids"]


# ── 7. get ────────────────────────────────────────────────────────────────────


def test_get_initiative_returns_chairs_jobs_and_counts(
    as_member, member_factory, assign_role, chapter_id, cursor
):
    chair = member_factory()
    assign_role(chair, "risk_chair")
    client = as_member(chair)

    created = client.post(
        "/api/initiatives/",
        json={"title": "Canned Food Drive", "date": "2026-07-19", "time": "14:00"},
    ).json()

    cursor.execute(
        "INSERT INTO tasks (chapter_id, title, status, initiative_id) "
        "VALUES (%s, 'Load truck', 'open', %s)",
        (chapter_id, created["id"]),
    )

    resp = client.get(f"/api/initiatives/{created['id']}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chair_member_ids"] == [chair]
    assert body["job_count"] == 1
    assert body["open_job_count"] == 1
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["title"] == "Load truck"


def test_get_initiative_in_other_chapter_is_404(as_member, member_factory, cursor):
    cursor.execute(
        "INSERT INTO chapters (name, organization, school) VALUES ('other-get', 'o', 's') RETURNING id"
    )
    other_chapter = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO members (chapter_id, name, email, role, status) "
        "VALUES (%s, 'Foreign Chair', %s, 'member', 'active') RETURNING id",
        (other_chapter, f"{uuid.uuid4()}@test.local"),
    )
    foreign_chair = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO member_roles (chapter_id, member_id, role_key) VALUES (%s, %s, 'risk_chair')",
        (other_chapter, foreign_chair),
    )
    cursor.execute(
        "INSERT INTO initiatives (chapter_id, title, date, time, created_by) "
        "VALUES (%s, 'Foreign Initiative', '2026-07-01', '10:00', %s) RETURNING id",
        (other_chapter, foreign_chair),
    )
    foreign_initiative = str(cursor.fetchone()["id"])

    home_member = member_factory()
    client = as_member(home_member)
    resp = client.get(f"/api/initiatives/{foreign_initiative}")
    assert resp.status_code == 404


# ── 8. chair management ───────────────────────────────────────────────────────


def test_add_chair_by_non_assigned_chair_is_403(
    as_member, member_factory, assign_role, chapter_id
):
    chair = member_factory()
    assign_role(chair, "risk_chair")
    client = as_member(chair)
    created = client.post(
        "/api/initiatives/",
        json={"title": "Winter Formal", "date": "2026-07-22", "time": "20:00"},
    ).json()

    outsider = member_factory()
    target = member_factory()
    outsider_client = as_member(outsider)
    resp = outsider_client.post(
        f"/api/initiatives/{created['id']}/chairs", json={"member_id": target}
    )
    assert resp.status_code == 403


def test_remove_last_chair_is_409(as_member, member_factory, assign_role, chapter_id):
    chair = member_factory()
    assign_role(chair, "risk_chair")
    client = as_member(chair)
    created = client.post(
        "/api/initiatives/",
        json={"title": "Spring Fling", "date": "2026-07-23", "time": "17:00"},
    ).json()

    resp = client.delete(f"/api/initiatives/{created['id']}/chairs/{chair}")
    assert resp.status_code == 409

"""Security assignments + swaps — HTTP layer (plan §5.2, items 12-17).

RPC-level guards/atomicity live in tests/events/test_security.py; this file
covers request/response-shaped behavior (status codes, auth gates, route
resolution) via the real app + TestClient. Runs in dry_run (app_on_test_db).
"""

from __future__ import annotations

import uuid


def _assign_http(client, event_id, member_id):
    return client.post(f"/api/events/{event_id}/security", json={"member_id": member_id})


# ── 12. read roster ──────────────────────────────────────────────────────────

def test_get_security_roster_and_cross_chapter_404(
    as_member, create_event, user_factory
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    member = user_factory()
    _assign_http(as_member(officer["id"]), ev["id"], member["id"])

    plain = user_factory()
    resp = as_member(plain["id"]).get(f"/api/events/{ev['id']}/security")
    assert resp.status_code == 200
    roster = resp.json()
    assert len(roster) == 1
    assert roster[0]["member_id"] == member["id"]
    assert roster[0]["status"] == "in_progress"

    missing = as_member(plain["id"]).get(f"/api/events/{uuid.uuid4()}/security")
    assert missing.status_code == 404


# ── 13. assign auth ──────────────────────────────────────────────────────────

def test_assign_permission_matrix(as_member, create_event, user_factory, assign_role):
    officer = user_factory(role="officer")
    ev = create_event(officer)

    plain = user_factory()
    resp = _assign_http(as_member(plain["id"]), ev["id"], user_factory()["id"])
    assert resp.status_code == 403

    supervised = _assign_http(as_member(officer["id"]), ev["id"], user_factory()["id"])
    assert supervised.status_code == 201, supervised.text
    assert supervised.json()["status"] == "in_progress"

    secretary = user_factory()
    assign_role(secretary["id"], "secretary")  # holds calendar:event:update
    by_perm = _assign_http(as_member(secretary["id"]), ev["id"], user_factory()["id"])
    assert by_perm.status_code == 201, by_perm.text


# ── 14. remove auth ──────────────────────────────────────────────────────────

def test_remove_by_supervisor_and_plain_member(as_member, create_event, user_factory):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    member = user_factory()
    task_id = _assign_http(as_member(officer["id"]), ev["id"], member["id"]).json()["task_id"]

    plain = user_factory()
    forbidden = as_member(plain["id"]).delete(f"/api/events/{ev['id']}/security/{task_id}")
    assert forbidden.status_code == 403

    removed = as_member(officer["id"]).delete(f"/api/events/{ev['id']}/security/{task_id}")
    assert removed.status_code == 200, removed.text
    assert removed.json()["status"] == "cancelled"


# ── 15. swap round-trip ──────────────────────────────────────────────────────

def test_swap_round_trip_http(as_member, create_event, user_factory):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder = user_factory()
    target = user_factory()
    task_id = _assign_http(as_member(officer["id"]), ev["id"], holder["id"]).json()["task_id"]

    holder_client = as_member(holder["id"])
    base = f"/api/events/{ev['id']}/security"

    # swap_self -> 422
    self_swap = holder_client.post(
        f"{base}/{task_id}/swap-request", json={"target_member_id": holder["id"]}
    )
    assert self_swap.status_code == 422

    # holder requests -> 200
    req = holder_client.post(
        f"{base}/{task_id}/swap-request", json={"target_member_id": target["id"]}
    )
    assert req.status_code == 200, req.text
    swap_id = req.json()["id"]

    # duplicate pending -> 409
    dup = holder_client.post(
        f"{base}/{task_id}/swap-request", json={"target_member_id": user_factory()["id"]}
    )
    assert dup.status_code == 409

    # non-target accept -> 403
    non_target = as_member(holder["id"]).post(f"{base}/swaps/{swap_id}/accept")
    assert non_target.status_code == 403

    # target accept -> 200
    ok = as_member(target["id"]).post(f"{base}/swaps/{swap_id}/accept")
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "accepted"


# ── 16. my-swaps inbox (also proves route isn't shadowed by /{event_id}) ─────

def test_my_swaps_inbox(as_member, create_event, user_factory):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder = user_factory()
    target = user_factory()
    task_id = _assign_http(as_member(officer["id"]), ev["id"], holder["id"]).json()["task_id"]
    req = as_member(holder["id"]).post(
        f"/api/events/{ev['id']}/security/{task_id}/swap-request",
        json={"target_member_id": target["id"]},
    )
    swap_id = req.json()["id"]

    target_view = as_member(target["id"]).get("/api/events/security-swaps/mine")
    assert target_view.status_code == 200, target_view.text
    tv = target_view.json()
    assert [s["id"] for s in tv["incoming"]] == [swap_id]
    assert tv["outgoing"] == []

    requester_view = as_member(holder["id"]).get("/api/events/security-swaps/mine").json()
    assert [s["id"] for s in requester_view["outgoing"]] == [swap_id]
    assert requester_view["incoming"] == []

    uninvolved = as_member(user_factory()["id"]).get("/api/events/security-swaps/mine").json()
    assert uninvolved["incoming"] == []
    assert uninvolved["outgoing"] == []


# ── 17. event detail job counts exclude security ─────────────────────────────

def test_event_detail_job_counts_exclude_security(
    as_member, create_event, create_job, user_factory
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    create_job(event_id=ev["id"])                      # standard, open
    create_job(event_id=ev["id"], status="in_progress")  # standard, open-ish
    _assign_http(as_member(officer["id"]), ev["id"], user_factory()["id"])  # security

    detail = as_member(officer["id"]).get(f"/api/events/{ev['id']}").json()
    assert detail["job_count"] == 2       # security excluded
    assert detail["open_job_count"] == 2  # security excluded


# ── 18. the LIST endpoint carries open_job_count too (B4FEND §5.1) ───────────

def test_event_list_carries_open_job_count(
    as_member, create_event, create_job, user_factory
):
    """Screen 1's "N open jobs" lure was event-detail-only; the list feeds it now."""
    officer = user_factory(role="officer")
    ev = create_event(officer)
    create_job(event_id=ev["id"])                        # open
    create_job(event_id=ev["id"], status="in_progress")  # open-ish
    create_job(event_id=ev["id"], status="approved")     # counted, not open
    _assign_http(as_member(officer["id"]), ev["id"], user_factory()["id"])  # security

    rows = as_member(officer["id"]).get("/api/events/").json()
    row = next(e for e in rows if e["id"] == ev["id"])
    assert row["job_count"] == 3       # security excluded
    assert row["open_job_count"] == 2  # approved and security excluded


# ── 19. requester cancels their own pending swap (B4FEND §5.4) ───────────────

def test_swap_cancel_http(as_member, create_event, user_factory):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder, target = user_factory(), user_factory()
    assigned = _assign_http(as_member(officer["id"]), ev["id"], holder["id"])
    task_id = assigned.json()["task_id"]

    swap = as_member(holder["id"]).post(
        f"/api/events/{ev['id']}/security/{task_id}/swap-request",
        json={"target_member_id": target["id"]},
    )
    assert swap.status_code == 200, swap.text
    swap_id = swap.json()["id"]
    cancel_url = f"/api/events/{ev['id']}/security/swaps/{swap_id}/cancel"

    # The target is not the requester — 403, and the swap survives.
    denied = as_member(target["id"]).post(cancel_url)
    assert denied.status_code == 403, denied.text
    assert "not_swap_requester" in denied.text

    ok = as_member(holder["id"]).post(cancel_url)
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "cancelled"

    # It leaves both swap inboxes (the listing is pending-only).
    assert as_member(holder["id"]).get("/api/events/security-swaps/mine").json()["outgoing"] == []
    assert as_member(target["id"]).get("/api/events/security-swaps/mine").json()["incoming"] == []

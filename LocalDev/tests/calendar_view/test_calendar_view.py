"""GET /api/calendar — the aggregation VIEW (spec §2, resolved decision #3)."""

from __future__ import annotations

RANGE = {"start": "2026-06-01", "end": "2026-08-01"}


def _items(body, kind):
    return [i for i in body["items"] if i["kind"] == kind]


# ── events ───────────────────────────────────────────────────────────────────


def test_event_appears_with_understaffed_flag(harness, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer, required=True, finable=True)

    resp = harness.login(officer).get("/api/calendar", params=RANGE)
    assert resp.status_code == 200, resp.text
    events = _items(resp.json(), "event")
    mine = [e for e in events if e["id"] == ev["id"]]
    assert len(mine) == 1
    item = mine[0]
    assert item["title"] == "Test Event"
    assert item["date"] == "2026-07-01"
    assert item["required"] is True and item["finable"] is True
    assert item["organizer_count"] == 0
    # D3 (docs/imp-ev-ph2.md): ORGANIZER_SOFT_MIN dropped 2 -> 1.
    assert item["organizers_needed"] == 1  # soft min, "needs N more organizers"
    assert item["understaffed"] is True
    assert "supervisor_member_id" in item and "event_type" in item


def test_staffed_event_not_understaffed(harness, user_factory, create_event, sb_client):
    from api.events.services import events as ev_svc

    officer = user_factory(role="officer")
    helper1, helper2 = user_factory(), user_factory()
    ev = create_event(officer)
    ev_svc.add_organizer(sb_client, actor=officer, event_id=ev["id"], member_id=helper1["id"])
    ev_svc.add_organizer(sb_client, actor=officer, event_id=ev["id"], member_id=helper2["id"])

    body = harness.login(officer).get("/api/calendar", params=RANGE).json()
    item = next(e for e in _items(body, "event") if e["id"] == ev["id"])
    assert item["organizer_count"] == 2
    assert item["organizers_needed"] == 0
    assert item["understaffed"] is False


def test_member_does_not_see_officer_event(harness, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer, audience="officers")
    plain = user_factory()

    body = harness.login(plain).get("/api/calendar", params=RANGE).json()
    assert ev["id"] not in {e["id"] for e in _items(body, "event")}

    body = harness.login(officer).get("/api/calendar", params=RANGE).json()
    assert ev["id"] in {e["id"] for e in _items(body, "event")}


def test_event_outside_range_excluded(harness, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer, date="2026-09-15")

    body = harness.login(officer).get("/api/calendar", params=RANGE).json()
    assert ev["id"] not in {e["id"] for e in _items(body, "event")}


# ── event groups ─────────────────────────────────────────────────────────────


def test_groups_map_links_grouped_events(harness, user_factory, create_event):
    officer = user_factory(role="officer")
    setup = create_event(officer, title="Setup", date="2026-07-04")
    main = create_event(
        officer, title="Main", date="2026-07-05", group_with_event_id=setup["id"]
    )

    body = harness.login(officer).get("/api/calendar", params=RANGE).json()
    group_id = main["group_id"]
    assert group_id, "grouping should have assigned a group id"
    assert set(body["groups"][group_id]) == {setup["id"], main["id"]}

    items = {e["id"]: e for e in _items(body, "event")}
    assert items[setup["id"]]["group_id"] == group_id
    assert items[main["id"]]["group_id"] == group_id


# ── invoice dues ─────────────────────────────────────────────────────────────


def test_member_sees_only_own_invoice_dues(harness, user_factory, invoice_factory):
    me, other = user_factory(), user_factory()
    mine = invoice_factory(member_id=me["id"], due_in_days=20, amount_cents=5000)
    theirs = invoice_factory(member_id=other["id"], due_in_days=20)

    body = harness.login(me).get("/api/calendar", params=RANGE).json()
    dues = _items(body, "invoice_due")
    ids = {d["invoice_id"] for d in dues}
    assert mine in ids and theirs not in ids
    item = next(d for d in dues if d["invoice_id"] == mine)
    assert item["amount_cents"] == 5000
    assert item["remaining_cents"] == 5000
    assert item["source"] == "dues"
    assert item["overdue"] is False


def test_verifier_sees_other_members_invoice_dues(
    harness, user_factory, invoice_factory, assign_role
):
    member = user_factory()
    inv = invoice_factory(member_id=member["id"], due_in_days=15)

    treasurer = user_factory()
    assign_role(treasurer["id"], "treasurer")  # holds treasury:payment:verify

    body = harness.login(treasurer).get("/api/calendar", params=RANGE).json()
    dues = {d["invoice_id"]: d for d in _items(body, "invoice_due")}
    assert inv in dues
    assert dues[inv]["member_id"] == member["id"]
    assert dues[inv]["member_name"]


def test_treasury_read_grant_sees_other_members_invoice_dues(
    harness, user_factory, invoice_factory, grant_treasury_read
):
    member = user_factory()
    inv = invoice_factory(member_id=member["id"], due_in_days=15)

    reader = user_factory()
    grant_treasury_read(reader["id"])

    body = harness.login(reader).get("/api/calendar", params=RANGE).json()
    assert inv in {d["invoice_id"] for d in _items(body, "invoice_due")}


def test_paid_invoice_never_on_calendar(harness, user_factory, invoice_factory):
    me = user_factory()
    paid = invoice_factory(member_id=me["id"], due_in_days=10, status="paid")

    body = harness.login(me).get("/api/calendar", params=RANGE).json()
    assert paid not in {d["invoice_id"] for d in _items(body, "invoice_due")}
    assert paid not in {d["invoice_id"] for d in body["overdue_invoices"]}


# ── decision #3: overdue invoices never scroll into the past ─────────────────


def test_overdue_invoice_outside_range_still_surfaces(
    harness, user_factory, invoice_factory
):
    me = user_factory()
    overdue = invoice_factory(member_id=me["id"], due_in_days=-30)  # last month

    body = harness.login(me).get(
        "/api/calendar", params={"start": "2026-06-01", "end": "2026-06-30"}
    ).json()

    # not inline (its due date is outside the requested range)…
    assert overdue not in {d["invoice_id"] for d in _items(body, "invoice_due")}
    # …but ALWAYS in the dedicated overdue array, flagged, with days_overdue.
    flagged = {d["invoice_id"]: d for d in body["overdue_invoices"]}
    assert overdue in flagged
    assert flagged[overdue]["overdue"] is True
    assert 29 <= flagged[overdue]["days_overdue"] <= 31


def test_overdue_invoice_in_range_appears_inline_and_flagged(
    harness, user_factory, invoice_factory
):
    me = user_factory()
    overdue = invoice_factory(member_id=me["id"], due_in_days=-3)

    body = harness.login(me).get("/api/calendar", params=RANGE).json()
    inline = {d["invoice_id"]: d for d in _items(body, "invoice_due")}
    assert overdue in inline and inline[overdue]["overdue"] is True
    assert overdue in {d["invoice_id"] for d in body["overdue_invoices"]}


def test_overdue_array_is_own_invoices_only(
    harness, user_factory, invoice_factory, assign_role
):
    member = user_factory()
    invoice_factory(member_id=member["id"], due_in_days=-5)

    treasurer = user_factory()
    assign_role(treasurer["id"], "treasurer")
    body = harness.login(treasurer).get("/api/calendar", params=RANGE).json()
    assert body["overdue_invoices"] == []


# ── task dues ────────────────────────────────────────────────────────────────


def test_task_due_appears(harness, user_factory, task_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    task = task_factory(title="Buy supplies", due_on="2026-07-10", event_id=ev["id"])

    body = harness.login(user_factory()).get("/api/calendar", params=RANGE).json()
    tasks = {t["task_id"]: t for t in _items(body, "task_due")}
    assert task in tasks
    assert tasks[task]["title"] == "Buy supplies"
    assert tasks[task]["status"] == "open"
    assert tasks[task]["event_id"] == ev["id"]
    assert tasks[task]["date"] == "2026-07-10"


def test_task_without_due_date_not_on_calendar(harness, user_factory, task_factory):
    undated = task_factory(due_on=None)
    body = harness.login(user_factory()).get("/api/calendar", params=RANGE).json()
    assert undated not in {t["task_id"] for t in _items(body, "task_due")}


# ── aggregation behavior ─────────────────────────────────────────────────────


def test_items_sorted_by_date(
    harness, user_factory, create_event, invoice_factory, task_factory
):
    officer = user_factory(role="officer")
    create_event(officer, date="2026-07-20")
    create_event(officer, date="2026-06-15")
    invoice_factory(member_id=officer["id"], due_in_days=25)
    task_factory(due_on="2026-07-02")

    body = harness.login(officer).get("/api/calendar", params=RANGE).json()
    dates = [i["date"] for i in body["items"]]
    assert len(dates) >= 4
    assert dates == sorted(dates)


def test_default_range_and_validation(harness, user_factory):
    user = user_factory()
    client = harness.login(user)

    resp = client.get("/api/calendar")  # defaults: 1st of month → +60 days
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["start"] <= body["end"]
    assert body["start"].endswith("-01")

    bad = client.get("/api/calendar", params={"start": "2026-07-01", "end": "2026-06-01"})
    assert bad.status_code == 422

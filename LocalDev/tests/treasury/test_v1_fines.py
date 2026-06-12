"""TREASURY V1 — fines: flat $25, never automatic, ≥24h gate (spec §5).

System surfaces who missed (GET /api/fines/missed/{event_id}); Finance Board
issues fine invoices by hand (POST /api/fines/issue). The auto-fine cron is a
disabled no-op.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from api.treasury.core.fines import FLAT_FINE_CENTS
from api.treasury.services import invoices as inv_svc
from tests.treasury.test_v1_helpers import api, assign_role, make_user  # noqa: F401

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _stub_recompute(monkeypatch):
    monkeypatch.setattr(inv_svc, "recompute_member_balance", lambda sb, member_id: None)


def _make_event(cursor, chapter_id, *, hours_ago: float, required: bool = True) -> str:
    start = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    cursor.execute(
        """INSERT INTO events (chapter_id, title, description, date, time, location, required, fine_amount)
           VALUES (%s, 'Chapter Meeting', '', %s, %s, 'Hall', %s, 0) RETURNING id""",
        (chapter_id, start.date(), start.time(), required),
    )
    return str(cursor.fetchone()["id"])


def _check_in(cursor, event_id, member_id):
    cursor.execute(
        "INSERT INTO attendance (event_id, member_id, checked_in) VALUES (%s,%s,true)",
        (event_id, member_id),
    )


def test_flat_fine_constant_is_25_dollars():
    assert FLAT_FINE_CENTS == 2500


def test_missed_endpoint_surfaces_unexcused_and_already_fined(
    api, sb_client, cursor, chapter_id, member_factory
):
    treasurer = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")
    attended = member_factory()
    missed = member_factory()
    event_id = _make_event(cursor, chapter_id, hours_ago=30)
    _check_in(cursor, event_id, attended)

    client = api(make_user(treasurer, chapter_id))
    resp = client.get(f"/api/fines/missed/{event_id}", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200, resp.text
    rows = resp.json()["missed"]
    ids = {r["member_id"] for r in rows}
    assert missed in ids and treasurer in ids
    assert attended not in ids
    assert all(r["already_fined"] is False for r in rows)

    # issue a fine to `missed`, then the flag flips
    issue = client.post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [missed]},
        headers={"Authorization": "Bearer x"},
    )
    assert issue.status_code == 200, issue.text
    rows = client.get(
        f"/api/fines/missed/{event_id}", headers={"Authorization": "Bearer x"}
    ).json()["missed"]
    flags = {r["member_id"]: r["already_fined"] for r in rows}
    assert flags[missed] is True


def test_missed_endpoint_requires_fines_issue_permission(
    api, sb_client, cursor, chapter_id, member_factory
):
    officer = member_factory(role="officer")
    event_id = _make_event(cursor, chapter_id, hours_ago=30)
    resp = api(make_user(officer, chapter_id, role="officer")).get(
        f"/api/fines/missed/{event_id}", headers={"Authorization": "Bearer x"}
    )
    assert resp.status_code == 403


def test_issue_rejected_before_24h(api, sb_client, cursor, chapter_id, member_factory):
    treasurer = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")
    missed = member_factory()
    event_id = _make_event(cursor, chapter_id, hours_ago=2)  # too recent

    resp = api(make_user(treasurer, chapter_id)).post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [missed]},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 422
    assert "24" in resp.json()["detail"]


def test_issue_creates_flat_2500_fines_for_unexcused_only(
    api, sb_client, cursor, chapter_id, member_factory
):
    finance = member_factory()
    assign_role(cursor, chapter_id, finance, "finance_board")  # finance_board may issue
    attended = member_factory()
    missed_1 = member_factory()
    missed_2 = member_factory()
    event_id = _make_event(cursor, chapter_id, hours_ago=26)
    _check_in(cursor, event_id, attended)

    client = api(make_user(finance, chapter_id))
    resp = client.post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [attended, missed_1, missed_2]},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["issued_member_ids"]) == {missed_1, missed_2}
    assert attended in body["skipped_member_ids"]

    cursor.execute(
        "SELECT member_id, amount_cents, kind, issued_by FROM unpaid_invoices WHERE source_event_id=%s",
        (event_id,),
    )
    rows = cursor.fetchall()
    assert len(rows) == 2
    assert {str(r["member_id"]) for r in rows} == {missed_1, missed_2}
    assert all(r["amount_cents"] == 2500 for r in rows)
    assert all(r["kind"] == "fine" for r in rows)
    assert all(str(r["issued_by"]) == finance for r in rows)

    # re-issuing skips the already-fined members
    resp = client.post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [missed_1, missed_2]},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200
    assert resp.json()["issued_member_ids"] == []
    cursor.execute(
        "SELECT count(*) AS n FROM unpaid_invoices WHERE source_event_id=%s", (event_id,)
    )
    assert cursor.fetchone()["n"] == 2


def test_issue_refused_for_non_required_event(api, sb_client, cursor, chapter_id, member_factory):
    treasurer = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")
    missed = member_factory()
    event_id = _make_event(cursor, chapter_id, hours_ago=30, required=False)
    resp = api(make_user(treasurer, chapter_id)).post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [missed]},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 422


def test_issue_requires_permission(api, sb_client, cursor, chapter_id, member_factory):
    officer = member_factory(role="officer")
    missed = member_factory()
    event_id = _make_event(cursor, chapter_id, hours_ago=30)
    resp = api(make_user(officer, chapter_id, role="officer")).post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [missed]},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 403


# ── automatic fines are dead ──────────────────────────────────────────────────
def test_cron_process_fines_is_disabled(api, sb_client, chapter_id, member_factory):
    member = member_factory()
    resp = api(make_user(member, chapter_id)).get(
        "/api/cron/process-fines", headers={"Authorization": "Bearer x"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "disabled"


def test_vercel_json_has_no_process_fines_cron():
    config = json.loads((_REPO_ROOT / "vercel.json").read_text())
    for cron in config.get("crons", []):
        assert "process-fines" not in cron.get("path", "")

"""Security assignments + swaps — RPC-level tests (plan §5.1).

Superuser connection bypasses RLS (treasury-test pattern). RPCs are exercised
directly via sb_client.rpc(...) so the guards, atomic swap, catalog, and
append-only triggers are tested independent of the HTTP auth layer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

from api.events.services import events as events_svc


# ── helpers ──────────────────────────────────────────────────────────────────

def _future(hours: float) -> tuple[str, str]:
    dt = datetime.now(timezone.utc) + timedelta(hours=hours)
    return dt.date().isoformat(), dt.strftime("%H:%M")


def _assign(sb, chapter_id, event_id, member_id, actor_id, key=None):
    return sb.rpc(
        "ev_assign_security",
        {
            "p_chapter_id": chapter_id,
            "p_event_id": event_id,
            "p_member_id": member_id,
            "p_actor_id": actor_id,
            "p_title": None,
            "p_idempotency_key": key,
        },
    ).execute().data


def _remove(sb, chapter_id, task_id, actor_id, key=None):
    return sb.rpc(
        "ev_remove_security",
        {"p_chapter_id": chapter_id, "p_task_id": task_id,
         "p_actor_id": actor_id, "p_idempotency_key": key},
    ).execute().data


def _request(sb, chapter_id, task_id, target_id, actor_id, note=None, key=None):
    return sb.rpc(
        "ev_request_security_swap",
        {"p_chapter_id": chapter_id, "p_task_id": task_id,
         "p_target_member_id": target_id, "p_actor_id": actor_id,
         "p_note": note, "p_idempotency_key": key},
    ).execute().data


def _accept(sb, chapter_id, swap_id, actor_id, key=None):
    return sb.rpc(
        "ev_accept_security_swap",
        {"p_chapter_id": chapter_id, "p_swap_id": swap_id,
         "p_actor_id": actor_id, "p_idempotency_key": key},
    ).execute().data


def _decline(sb, chapter_id, swap_id, actor_id, key=None):
    return sb.rpc(
        "ev_decline_security_swap",
        {"p_chapter_id": chapter_id, "p_swap_id": swap_id,
         "p_actor_id": actor_id, "p_idempotency_key": key},
    ).execute().data


def _tk(sb, name, **params):
    return sb.rpc(name, params).execute().data


# ── 1. assign ────────────────────────────────────────────────────────────────

def test_assign_creates_task_commitment_log_audit_outbox(
    sb_client, cursor, chapter_id, user_factory, create_event
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    member = user_factory()

    result = _assign(sb_client, chapter_id, ev["id"], member["id"], officer["id"])
    task = result["task"]
    commitment = result["commitment"]

    assert task["kind"] == "security"
    assert task["status"] == "in_progress"
    assert task["people_needed"] == 1
    assert task["assigned_member_id"] is None  # commitment is the source of truth
    assert str(commitment["member_id"]) == member["id"]
    assert commitment["status"] == "active"

    cursor.execute(
        "SELECT action FROM task_commitment_log WHERE task_id = %s", (task["id"],)
    )
    assert [r["action"] for r in cursor.fetchall()] == ["commit"]

    cursor.execute(
        "SELECT * FROM audit_logs WHERE chapter_id = %s AND action = 'SECURITY_ASSIGNED'",
        (chapter_id,),
    )
    audits = cursor.fetchall()
    assert len(audits) == 1
    assert str(audits[0]["target_id"]) == task["id"]

    cursor.execute(
        "SELECT * FROM message_outbox WHERE chapter_id = %s AND event_type = 'SECURITY_ASSIGNED'",
        (chapter_id,),
    )
    outbox = cursor.fetchall()
    assert len(outbox) == 1
    assert str(outbox[0]["member_id"]) == member["id"]
    payload = outbox[0]["payload"]
    assert "score" not in payload  # neutral payload — never the delinquency score
    assert payload["task_id"] == task["id"]
    assert payload["event_id"] == ev["id"]


def test_assign_idempotency_key_replays(
    sb_client, cursor, chapter_id, user_factory, create_event
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    member = user_factory()

    first = _assign(sb_client, chapter_id, ev["id"], member["id"], officer["id"], key="k1")
    second = _assign(sb_client, chapter_id, ev["id"], member["id"], officer["id"], key="k1")
    assert first["task"]["id"] == second["task"]["id"]

    cursor.execute(
        "SELECT count(*) AS n FROM tasks WHERE event_id = %s AND kind = 'security'", (ev["id"],)
    )
    assert cursor.fetchone()["n"] == 1
    cursor.execute(
        "SELECT count(*) AS n FROM task_commitments WHERE task_id = %s", (first["task"]["id"],)
    )
    assert cursor.fetchone()["n"] == 1


# ── 2. one active security assignment per member per event ───────────────────

def test_assign_same_member_twice_rejected_but_other_event_ok(
    sb_client, chapter_id, user_factory, create_event
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    member = user_factory()

    _assign(sb_client, chapter_id, ev["id"], member["id"], officer["id"])
    with pytest.raises(Exception, match="target_already_assigned"):
        _assign(sb_client, chapter_id, ev["id"], member["id"], officer["id"])

    ev2 = create_event(officer)
    other = _assign(sb_client, chapter_id, ev2["id"], member["id"], officer["id"])
    assert other["task"]["kind"] == "security"


# ── 3. guards on the shared machinery ────────────────────────────────────────

def test_security_task_blocks_commit_uncommit_status(
    sb_client, chapter_id, user_factory, create_event
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    member = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], member["id"], officer["id"])["task"]["id"]

    other = user_factory()
    with pytest.raises(Exception, match="security_preassigned"):
        _tk(sb_client, "tk_commit_task", p_chapter_id=chapter_id, p_task_id=task_id,
            p_member_id=other["id"], p_actor_id=other["id"], p_idempotency_key=None)

    with pytest.raises(Exception, match="security_no_unclaim"):
        _tk(sb_client, "tk_uncommit_task", p_chapter_id=chapter_id, p_task_id=task_id,
            p_member_id=member["id"], p_actor_id=member["id"], p_reason=None,
            p_idempotency_key=None)

    with pytest.raises(Exception, match="security_no_status_change"):
        _tk(sb_client, "tk_update_task_status", p_chapter_id=chapter_id, p_task_id=task_id,
            p_status="open", p_actor_id=officer["id"], p_idempotency_key=None)


# ── 4. report/approve/reject lifecycle reuse ─────────────────────────────────

def test_security_task_reuses_report_approve_reject(
    sb_client, cursor, chapter_id, user_factory, create_event
):
    officer = user_factory(role="officer")  # creator = auto-supervisor (approver)
    ev = create_event(officer)
    member = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], member["id"], officer["id"])["task"]["id"]

    reported = _tk(sb_client, "tk_report_done", p_chapter_id=chapter_id, p_task_id=task_id,
                   p_member_id=member["id"], p_idempotency_key=None)
    assert reported["status"] == "done_reported"

    cursor.execute(
        "SELECT member_id FROM message_outbox WHERE chapter_id = %s AND event_type = 'JOB_REPORTED'",
        (chapter_id,),
    )
    approver_ids = {str(r["member_id"]) for r in cursor.fetchall()}
    assert officer["id"] in approver_ids  # supervisor got the approve notification

    approved = _tk(sb_client, "tk_approve_task", p_chapter_id=chapter_id, p_task_id=task_id,
                   p_actor_id=officer["id"], p_idempotency_key=None)
    assert approved["status"] == "approved"
    cursor.execute(
        "SELECT status FROM task_commitments WHERE task_id = %s AND member_id = %s",
        (task_id, member["id"]),
    )
    assert cursor.fetchone()["status"] == "completed"

    # A fresh assignment: report then reject returns it to in_progress with reason.
    ev2 = create_event(officer)
    m2 = user_factory()
    t2 = _assign(sb_client, chapter_id, ev2["id"], m2["id"], officer["id"])["task"]["id"]
    _tk(sb_client, "tk_report_done", p_chapter_id=chapter_id, p_task_id=t2,
        p_member_id=m2["id"], p_idempotency_key=None)
    rejected = _tk(sb_client, "tk_reject_task", p_chapter_id=chapter_id, p_task_id=t2,
                   p_actor_id=officer["id"], p_reason="Left early", p_idempotency_key=None)
    assert rejected["status"] == "in_progress"
    assert rejected["rejection_reason"] == "Left early"
    cursor.execute(
        "SELECT status FROM task_commitments WHERE task_id = %s AND member_id = %s",
        (t2, m2["id"]),
    )
    assert cursor.fetchone()["status"] == "active"  # claimant retained


# ── 5. remove ────────────────────────────────────────────────────────────────

def test_remove_cancels_swap_uncommits_and_cancels_task(
    sb_client, cursor, chapter_id, user_factory, create_event
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder = user_factory()
    target = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]
    swap = _request(sb_client, chapter_id, task_id, target["id"], holder["id"])

    removed = _remove(sb_client, chapter_id, task_id, officer["id"])
    assert removed["status"] == "cancelled"

    cursor.execute("SELECT status FROM security_swap_requests WHERE id = %s", (swap["id"],))
    assert cursor.fetchone()["status"] == "cancelled"

    cursor.execute(
        "SELECT status FROM task_commitments WHERE task_id = %s AND member_id = %s",
        (task_id, holder["id"]),
    )
    assert cursor.fetchone()["status"] == "uncommitted"

    cursor.execute(
        "SELECT reason FROM task_commitment_log WHERE task_id = %s AND action = 'uncommit'",
        (task_id,),
    )
    assert cursor.fetchone()["reason"] == "security_removed"

    cursor.execute(
        "SELECT count(*) AS n FROM audit_logs WHERE chapter_id = %s AND action = 'SECURITY_REMOVED'",
        (chapter_id,),
    )
    assert cursor.fetchone()["n"] == 1


def test_remove_approved_assignment_rejected(
    sb_client, chapter_id, user_factory, create_event
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    member = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], member["id"], officer["id"])["task"]["id"]
    _tk(sb_client, "tk_report_done", p_chapter_id=chapter_id, p_task_id=task_id,
        p_member_id=member["id"], p_idempotency_key=None)
    _tk(sb_client, "tk_approve_task", p_chapter_id=chapter_id, p_task_id=task_id,
        p_actor_id=officer["id"], p_idempotency_key=None)

    with pytest.raises(Exception, match="security_already_approved"):
        _remove(sb_client, chapter_id, task_id, officer["id"])


# ── 6. swap request guards + happy path ──────────────────────────────────────

def test_swap_request_guards(sb_client, chapter_id, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder = user_factory()
    target = user_factory()
    other = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]

    # non-holder cannot request
    with pytest.raises(Exception, match="not_assigned"):
        _request(sb_client, chapter_id, task_id, target["id"], other["id"])

    # target == requester
    with pytest.raises(Exception, match="swap_self"):
        _request(sb_client, chapter_id, task_id, holder["id"], holder["id"])

    # target already assigned to security on the same event
    _assign(sb_client, chapter_id, ev["id"], other["id"], officer["id"])
    with pytest.raises(Exception, match="target_already_assigned"):
        _request(sb_client, chapter_id, task_id, other["id"], holder["id"])


def test_swap_request_happy_and_double_pending(
    sb_client, cursor, chapter_id, user_factory, create_event
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder = user_factory()
    target = user_factory()
    third = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]

    swap = _request(sb_client, chapter_id, task_id, target["id"], holder["id"], note="cover me")
    assert swap["status"] == "pending"
    assert str(swap["target_member_id"]) == target["id"]

    cursor.execute(
        "SELECT * FROM message_outbox WHERE chapter_id = %s AND event_type = 'SECURITY_SWAP_REQUESTED'",
        (chapter_id,),
    )
    outbox = cursor.fetchall()
    assert len(outbox) == 1
    assert str(outbox[0]["member_id"]) == target["id"]
    assert outbox[0]["payload"]["note"] == "cover me"

    cursor.execute(
        "SELECT count(*) AS n FROM audit_logs WHERE chapter_id = %s AND action = 'SECURITY_SWAP_REQUESTED'",
        (chapter_id,),
    )
    assert cursor.fetchone()["n"] == 1

    # a second pending request on the same assignment is blocked
    with pytest.raises(Exception, match="swap_already_pending"):
        _request(sb_client, chapter_id, task_id, third["id"], holder["id"])


def test_swap_request_wrong_state(sb_client, chapter_id, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder = user_factory()
    target = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]
    _tk(sb_client, "tk_report_done", p_chapter_id=chapter_id, p_task_id=task_id,
        p_member_id=holder["id"], p_idempotency_key=None)  # -> done_reported

    with pytest.raises(Exception, match="swap_wrong_state"):
        _request(sb_client, chapter_id, task_id, target["id"], holder["id"])


# ── 7. accept ────────────────────────────────────────────────────────────────

def test_accept_non_target_rejected(sb_client, chapter_id, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder = user_factory()
    target = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]
    swap = _request(sb_client, chapter_id, task_id, target["id"], holder["id"])

    with pytest.raises(Exception, match="not_swap_target"):
        _accept(sb_client, chapter_id, swap["id"], holder["id"])  # requester != target


def test_accept_atomic_swap(sb_client, cursor, chapter_id, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder = user_factory()
    target = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]
    swap = _request(sb_client, chapter_id, task_id, target["id"], holder["id"])

    accepted = _accept(sb_client, chapter_id, swap["id"], target["id"])
    assert accepted["status"] == "accepted"

    cursor.execute(
        "SELECT status FROM task_commitments WHERE task_id = %s AND member_id = %s",
        (task_id, holder["id"]),
    )
    assert cursor.fetchone()["status"] == "uncommitted"
    cursor.execute(
        "SELECT status FROM task_commitments WHERE task_id = %s AND member_id = %s",
        (task_id, target["id"]),
    )
    assert cursor.fetchone()["status"] == "active"

    cursor.execute("SELECT status FROM tasks WHERE id = %s", (task_id,))
    assert cursor.fetchone()["status"] == "in_progress"  # task stays claimed

    cursor.execute(
        "SELECT action FROM task_commitment_log WHERE task_id = %s ORDER BY created_at", (task_id,)
    )
    actions = [r["action"] for r in cursor.fetchall()]
    assert actions == ["commit", "uncommit", "commit"]  # assign, swap-out, swap-in

    cursor.execute(
        "SELECT member_id FROM message_outbox WHERE chapter_id = %s AND event_type = 'SECURITY_SWAP_ACCEPTED'",
        (chapter_id,),
    )
    accepted_recipients = {str(r["member_id"]) for r in cursor.fetchall()}
    assert accepted_recipients == {holder["id"], target["id"], officer["id"]}


def test_accept_idempotent_replay(sb_client, cursor, chapter_id, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder = user_factory()
    target = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]
    swap = _request(sb_client, chapter_id, task_id, target["id"], holder["id"])

    _accept(sb_client, chapter_id, swap["id"], target["id"], key="acc1")

    def _outbox_count():
        cursor.execute(
            "SELECT count(*) AS n FROM message_outbox WHERE chapter_id = %s AND event_type = 'SECURITY_SWAP_ACCEPTED'",
            (chapter_id,),
        )
        return cursor.fetchone()["n"]

    before = _outbox_count()
    _accept(sb_client, chapter_id, swap["id"], target["id"], key="acc1")  # replay
    assert _outbox_count() == before


def test_accept_after_done_reported_wrong_state(
    sb_client, chapter_id, user_factory, create_event
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder = user_factory()
    target = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]
    swap = _request(sb_client, chapter_id, task_id, target["id"], holder["id"])
    _tk(sb_client, "tk_report_done", p_chapter_id=chapter_id, p_task_id=task_id,
        p_member_id=holder["id"], p_idempotency_key=None)  # -> done_reported

    with pytest.raises(Exception, match="swap_wrong_state"):
        _accept(sb_client, chapter_id, swap["id"], target["id"])


def test_new_request_allowed_after_swap_resolves(
    sb_client, chapter_id, user_factory, create_event
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder = user_factory()
    target = user_factory()
    third = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]
    swap = _request(sb_client, chapter_id, task_id, target["id"], holder["id"])
    _accept(sb_client, chapter_id, swap["id"], target["id"])  # holder is now target

    # partial unique index only covers pending, so a fresh request is allowed
    swap2 = _request(sb_client, chapter_id, task_id, third["id"], target["id"])
    assert swap2["status"] == "pending"


# ── 8. decline ───────────────────────────────────────────────────────────────

def test_decline_outbox_to_requester_only(
    sb_client, cursor, chapter_id, user_factory, create_event
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder = user_factory()
    target = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]
    swap = _request(sb_client, chapter_id, task_id, target["id"], holder["id"])

    declined = _decline(sb_client, chapter_id, swap["id"], target["id"])
    assert declined["status"] == "declined"

    cursor.execute(
        "SELECT member_id FROM message_outbox WHERE chapter_id = %s AND event_type = 'SECURITY_SWAP_DECLINED'",
        (chapter_id,),
    )
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert str(rows[0]["member_id"]) == holder["id"]  # requester only


# ── 9. no T-36h lock on swaps ────────────────────────────────────────────────

def test_swaps_have_no_t36h_lock(
    sb_client, chapter_id, user_factory, create_event, create_job
):
    officer = user_factory(role="officer")
    d, t = _future(12)  # event starts 12h out — inside the T-36h window
    ev = create_event(officer, date=d, time=t)
    holder = user_factory()
    target = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]

    # A sibling standard job on the same event IS locked against uncommit.
    sibling = create_job(event_id=ev["id"])
    claimant = user_factory()
    _tk(sb_client, "tk_commit_task", p_chapter_id=chapter_id, p_task_id=sibling,
        p_member_id=claimant["id"], p_actor_id=claimant["id"], p_idempotency_key=None)
    with pytest.raises(Exception, match="unclaim_locked"):
        _tk(sb_client, "tk_uncommit_task", p_chapter_id=chapter_id, p_task_id=sibling,
            p_member_id=claimant["id"], p_actor_id=claimant["id"], p_reason=None,
            p_idempotency_key=None)

    # The security swap, however, succeeds regardless of the T-36h window.
    swap = _request(sb_client, chapter_id, task_id, target["id"], holder["id"])
    accepted = _accept(sb_client, chapter_id, swap["id"], target["id"])
    assert accepted["status"] == "accepted"


# ── 10. notify-gate excludes security jobs ───────────────────────────────────

def _notify_rpc(sb, chapter_id, event_id, actor_id, recipient_ids, key=None):
    return sb.rpc(
        "ev_notify_event",
        {
            "p_chapter_id": chapter_id,
            "p_event_id": event_id,
            "p_actor_id": actor_id,
            "p_recipient_member_ids": recipient_ids,
            "p_body_snapshot": "test",
            "p_delivery_mode": "dry_run",
            "p_idempotency_key": key,
        },
    ).execute().data


def test_notify_gate_excludes_security_jobs(
    sb_client, chapter_id, user_factory, create_event, create_job
):
    officer = user_factory(role="officer")  # creator = auto-supervisor
    ev = create_event(officer)
    organizer = user_factory()
    events_svc.add_organizer(sb_client, actor=organizer, event_id=ev["id"])

    # 3 security assignments, 0 standard jobs -> gate still fails.
    for _ in range(3):
        _assign(sb_client, chapter_id, ev["id"], user_factory()["id"], officer["id"])
    with pytest.raises(Exception, match="event_incomplete"):
        _notify_rpc(sb_client, chapter_id, ev["id"], officer["id"], [officer["id"]])

    # Add 3 standard jobs -> gate passes regardless of the security rows.
    for _ in range(3):
        create_job(event_id=ev["id"])
    send = _notify_rpc(sb_client, chapter_id, ev["id"], officer["id"], [officer["id"]])
    assert send["status"] == "queued"


# ── 11. append-only / guard triggers ─────────────────────────────────────────

def test_swap_row_is_append_only(sb_client, cursor, chapter_id, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder = user_factory()
    target = user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]
    swap = _request(sb_client, chapter_id, task_id, target["id"], holder["id"])
    _decline(sb_client, chapter_id, swap["id"], target["id"])  # now resolved

    # A resolved row cannot be updated further.
    with pytest.raises(psycopg2.DatabaseError, match="resolved|append-only"):
        cursor.execute(
            "UPDATE security_swap_requests SET status = 'accepted' WHERE id = %s", (swap["id"],)
        )
    # Deletes are always blocked.
    with pytest.raises(psycopg2.DatabaseError, match="forbidden|append-only"):
        cursor.execute("DELETE FROM security_swap_requests WHERE id = %s", (swap["id"],))


# ── 12. cancel — the requester withdraws (B4FEND §5.4) ───────────────────────

def _cancel(sb, chapter_id, swap_id, actor_id, key=None):
    return sb.rpc(
        "ev_cancel_security_swap",
        {"p_chapter_id": chapter_id, "p_swap_id": swap_id,
         "p_actor_id": actor_id, "p_idempotency_key": key},
    ).execute().data


def test_requester_cancels_pending_swap(
    sb_client, cursor, chapter_id, user_factory, create_event
):
    """Audit only (no outbox — withdrawing your own ask is not news), and the
    one-pending-swap slot frees so a fresh request can go out."""
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder, target, third = user_factory(), user_factory(), user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]
    swap = _request(sb_client, chapter_id, task_id, target["id"], holder["id"])

    cancelled = _cancel(sb_client, chapter_id, swap["id"], holder["id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["resolved_by"] == holder["id"]

    cursor.execute(
        "SELECT count(*) AS n FROM audit_logs WHERE chapter_id = %s "
        "AND action = 'SECURITY_SWAP_CANCELLED' AND target_id = %s",
        (chapter_id, swap["id"]),
    )
    assert cursor.fetchone()["n"] == 1

    # The original SECURITY_SWAP_REQUESTED row stands; cancelling adds nothing.
    cursor.execute(
        "SELECT event_type FROM message_outbox WHERE chapter_id = %s AND target_id = %s",
        (chapter_id, swap["id"]),
    )
    assert [r["event_type"] for r in cursor.fetchall()] == ["SECURITY_SWAP_REQUESTED"]

    # The unique-partial pending slot is free again.
    assert _request(sb_client, chapter_id, task_id, third["id"], holder["id"])["status"] == "pending"


def test_only_the_requester_may_cancel(sb_client, chapter_id, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder, target, bystander = user_factory(), user_factory(), user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]
    swap = _request(sb_client, chapter_id, task_id, target["id"], holder["id"])

    with pytest.raises(Exception, match="not_swap_requester"):
        _cancel(sb_client, chapter_id, swap["id"], target["id"])
    with pytest.raises(Exception, match="not_swap_requester"):
        _cancel(sb_client, chapter_id, swap["id"], bystander["id"])


def test_cancel_after_accept_is_wrong_state(
    sb_client, chapter_id, user_factory, create_event
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    holder, target = user_factory(), user_factory()
    task_id = _assign(sb_client, chapter_id, ev["id"], holder["id"], officer["id"])["task"]["id"]
    swap = _request(sb_client, chapter_id, task_id, target["id"], holder["id"])
    _accept(sb_client, chapter_id, swap["id"], target["id"])

    with pytest.raises(Exception, match="swap_wrong_state"):
        _cancel(sb_client, chapter_id, swap["id"], holder["id"])

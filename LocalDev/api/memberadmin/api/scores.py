from fastapi import APIRouter, Depends, HTTPException

from api.platform.db import get_db
from api.memberadmin.services.member_detail import load_member_event_breakdown
from api.memberadmin.services.scoring import compute_engagement_scores
from api.rbac.auth import require_permission
from api.treasury.notifications import enqueue_payment_reminder
from api.treasury.services.remaining import remaining_by_invoice

STANDING_VIEW_ALL = "standing:view_all"
STANDING_REMIND = "standing:remind"

router = APIRouter()


@router.get("/scores")
def get_engagement_scores(officer=Depends(require_permission(STANDING_VIEW_ALL))):
    """Ranked member engagement scores — lowest (most delinquent) first."""
    return compute_engagement_scores(officer["chapter_id"])


@router.get("/member/{member_id}")
def get_member_detail(member_id: str, officer=Depends(require_permission(STANDING_VIEW_ALL))):
    """Per-event breakdown for a single member."""
    return load_member_event_breakdown(officer["chapter_id"], member_id)


@router.post("/remind/{member_id}")
def send_reminder(member_id: str, officer=Depends(require_permission(STANDING_REMIND))):
    """Queue a payment reminder for a member's outstanding charges.

    Reads the live receivable — every `unpaid_invoices` row still open (status
    'unpaid' or 'partially_paid') of any kind (dues, rent, utilities, fine,
    assessment, manual); the legacy `fines` table has been frozen since migration
    0012 — and enqueues a real PAYMENT_REMINDER row in `message_outbox`, which the
    drain worker delivers (GET /api/cron/drain-outbox).

    A partially paid invoice counts at its REMAINING balance: `unpaid_invoices`
    carries no paid-to-date column, so the balance is derived the same way the
    member dashboard derives it (amount - direct verified payments - net
    allocations). A row whose remaining balance is zero is not owed and is
    dropped, whatever its status says.

    Nothing outstanding means no enqueue at all, not an empty message. The
    dedup_key below is scoped to the calendar day, so a reminder for $0.00 would
    burn it and silently swallow the real reminder an officer sends an hour later
    after issuing an actual charge (issue #35).

    The reminder is deduplicated per member per calendar day: clicking twice
    today sends one message (`queued: false` on the second call), and an officer
    can remind again tomorrow.
    """
    sb = get_db()
    member = (
        sb.table("members")
        .select("id, name, email")
        .eq("id", member_id)
        .eq("chapter_id", officer["chapter_id"])
        .single()
        .execute()
    )
    if not member.data:
        raise HTTPException(404, "Member not found")

    open_invoices = (
        sb.table("unpaid_invoices")
        .select("id, amount_cents")
        .eq("chapter_id", officer["chapter_id"])
        .eq("member_id", member_id)
        .in_("status", ["unpaid", "partially_paid"])
        .execute()
    ).data or []

    remaining = remaining_by_invoice(sb, open_invoices)
    owed = [c for c in remaining.values() if c > 0]

    unpaid_count = len(owed)
    unpaid_total_cents = sum(owed)

    if unpaid_count == 0:
        # Deliberately no enqueue: today's dedup key stays unconsumed so a real
        # charge issued later today can still be reminded about.
        return {
            "sent_to": member.data["email"],
            "name": member.data["name"],
            "unpaid_count": 0,
            "unpaid_total_cents": 0,
            "queued": False,
            "message": "Nothing outstanding — no reminder sent.",
        }

    enqueued = enqueue_payment_reminder(
        chapter_id=officer["chapter_id"],
        member_id=member_id,
        unpaid_count=unpaid_count,
        unpaid_total_cents=unpaid_total_cents,
        sb=sb,
    )

    return {
        "sent_to": member.data["email"],
        "name": member.data["name"],
        "unpaid_count": unpaid_count,
        "unpaid_total_cents": unpaid_total_cents,
        # False when today's reminder was already queued — no second message.
        "queued": enqueued is not None,
        "message": "Reminder queued",
    }

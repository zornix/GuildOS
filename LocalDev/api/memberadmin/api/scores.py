from fastapi import APIRouter, Depends, HTTPException

from api.platform.db import get_db
from api.memberadmin.services.member_detail import load_member_event_breakdown
from api.memberadmin.services.scoring import compute_engagement_scores
from api.rbac.auth import require_permission
from api.treasury.notifications import enqueue_payment_reminder

STANDING_VIEW_ALL = "standing:view_all"
STANDING_REMIND = "standing:remind"

router = APIRouter()


@router.get("/scores")
async def get_engagement_scores(officer=Depends(require_permission(STANDING_VIEW_ALL))):
    """Ranked member engagement scores — lowest (most delinquent) first."""
    return await compute_engagement_scores(officer["chapter_id"])


@router.get("/member/{member_id}")
async def get_member_detail(member_id: str, officer=Depends(require_permission(STANDING_VIEW_ALL))):
    """Per-event breakdown for a single member."""
    return await load_member_event_breakdown(officer["chapter_id"], member_id)


@router.post("/remind/{member_id}")
async def send_reminder(member_id: str, officer=Depends(require_permission(STANDING_REMIND))):
    """Queue a payment reminder for a member's outstanding fines.

    Reads the live receivable (`unpaid_invoices` where kind='fine' and
    status='unpaid'; the legacy `fines` table has been frozen since migration
    0012) and enqueues a real PAYMENT_REMINDER row in `message_outbox`, which the
    drain worker delivers (GET /api/cron/drain-outbox). This replaces the
    placeholder that returned "Reminder queued" having queued nothing
    (GTMLarpChecklist 2.2).

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

    unpaid = (
        sb.table("unpaid_invoices")
        .select("id, amount_cents")
        .eq("chapter_id", officer["chapter_id"])
        .eq("member_id", member_id)
        .eq("kind", "fine")
        .eq("status", "unpaid")
        .execute()
    ).data or []

    unpaid_count = len(unpaid)
    unpaid_total_cents = sum(inv["amount_cents"] for inv in unpaid)

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

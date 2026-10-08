"""Review Queue HTTP surface.

GET /payments/submissions  — officer review queue, paginated.
Guarded by treasury:payment:verify. Chapter-scoped from the authed user.
All amounts are integer cents.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from api.dependencies import get_current_user
from api.rbac.auth import require_permission
from api.rbac.services.permissions import has_permission
from api.platform.db import get_db
from api.treasury.services import reports as svc

# Catalog permission keys gating this surface (ADR-0001; 0147). Chapter-level
# aggregates read on treasury:budget:view; anything row-level (another member's
# statement) or ledger-grained (the period CSV, whose `ledger` dataset dumps
# big_ledger) reads on treasury:audit:view.
PAYMENT_REVIEW = "treasury:payment:verify"
DASHBOARD_VIEW = "treasury:budget:view"
RECORD_VIEW = "treasury:audit:view"

router = APIRouter()


@router.get("/payments/submissions")
def list_payment_submissions(
    status: str = Query(default="pending"),
    member_id: str | None = Query(default=None),
    invoice_id: str | None = Query(default=None),
    method: str | None = Query(default=None),
    min_amount_cents: int | None = Query(default=None, gt=0),
    max_amount_cents: int | None = Query(default=None, gt=0),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    user=Depends(require_permission(PAYMENT_REVIEW)),
):
    """Return the paginated review queue for the authed officer's chapter.

    Query params:
        status            — pending|approved|rejected (default: pending)
        member_id         — filter by member
        invoice_id        — filter by invoice
        method            — filter by payment method
        min_amount_cents  — minimum claimed_amount_cents (inclusive, integer)
        max_amount_cents  — maximum claimed_amount_cents (inclusive, integer)
        limit             — page size (1–200, default 50)
        cursor            — offset as string (from next_cursor of previous page)

    Returns: {"data": [...], "next_cursor": str|null, "total": int}
    """
    offset = int(cursor) if cursor else 0
    sb = get_db()
    return svc.list_payment_submissions(
        sb,
        chapter_id=user["chapter_id"],
        status=status,
        member_id=member_id,
        invoice_id=invoice_id,
        method=method,
        min_amount_cents=min_amount_cents,
        max_amount_cents=max_amount_cents,
        limit=limit,
        offset=offset,
    )


# ════════════════════════════════════════════════════════════════════════════
# Dashboard / Statement / Period CSV exports
# ════════════════════════════════════════════════════════════════════════════
@router.get("/dashboard")
def treasury_dashboard(
    user=Depends(require_permission(DASHBOARD_VIEW)),
):
    """Single treasurer aggregate for the authed user's chapter (integer cents)."""
    sb = get_db()
    return svc.dashboard_summary(sb, chapter_id=user["chapter_id"])


@router.get("/members/{member_id}/statement")
def member_statement(
    member_id: str,
    user=Depends(get_current_user),
):
    """A member's chronological financial statement.

    Access: the member themself, OR any `treasury:audit:view` holder IN THE SAME
    CHAPTER. A non-existent member, or one outside the requester's chapter,
    returns 404 so cross-chapter existence is never leaked.
    """
    sb = get_db()

    if str(user["id"]) != str(member_id) and not has_permission(user, RECORD_VIEW):
        raise HTTPException(403, f"Missing permission: {RECORD_VIEW}")

    member = (
        sb.table("members")
        .select("chapter_id")
        .eq("id", member_id)
        .maybe_single()
        .execute()
    ).data
    if not member or str(member["chapter_id"]) != str(user["chapter_id"]):
        raise HTTPException(404, "Member not found")

    return svc.member_statement(sb, member_id=member_id)


@router.get("/report")
def period_report(
    period: str = Query(..., description="Reporting period as YYYY-MM"),
    dataset: str = Query(..., description="payments|invoices|expenses|member_balances|ledger"),
    user=Depends(require_permission(RECORD_VIEW)),
):
    """Return one chapter-scoped `dataset` for `period` as a CSV download."""
    sb = get_db()
    try:
        csv_text = svc.period_report_csv(
            sb, chapter_id=user["chapter_id"], period=period, dataset=dataset
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    filename = f"treasury_{dataset}_{period}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

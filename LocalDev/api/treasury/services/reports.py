"""Reports service — Chunk F-partial (Review Queue) + F-complete (Dashboard,
Statement, Exports).

Provides read-only query functions for officer review workflows, the treasurer
dashboard, member self-serve statements, and period CSV exports. All queries are
chapter-scoped; money is always integer cents. These are read surfaces only —
they never mutate finance state (invariant 7).
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from api.treasury.core.balance import BalanceEngine


def list_payment_submissions(
    sb,
    *,
    chapter_id: str,
    status: str = "pending",
    member_id: str | None = None,
    invoice_id: str | None = None,
    method: str | None = None,
    min_amount_cents: int | None = None,
    max_amount_cents: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Return a Page-shaped dict of payment_submissions for a chapter.

    Args:
        sb: supabase-style DB client (PostgresClient or supabase-py)
        chapter_id: always-required chapter scope
        status: filter by submission status (default "pending")
        member_id: optional member filter
        invoice_id: optional invoice filter
        method: optional payment method filter (venmo|zelle|cash|bank_transfer)
        min_amount_cents: optional minimum claimed_amount_cents (inclusive)
        max_amount_cents: optional maximum claimed_amount_cents (inclusive)
        limit: page size (default 50)
        offset: row offset for pagination (default 0)

    Returns:
        {"data": list[dict], "next_cursor": str | None, "total": int}
        next_cursor is the stringified next offset when more rows remain, else None.
    """
    # ── count query (chapter + status scoped; other filters applied too) ──────
    count_qb = (
        sb.table("payment_submissions")
        .select("*", count="exact")
        .eq("chapter_id", chapter_id)
        .eq("status", status)
    )
    if member_id is not None:
        count_qb = count_qb.eq("member_id", member_id)
    if invoice_id is not None:
        count_qb = count_qb.eq("invoice_id", invoice_id)
    if method is not None:
        count_qb = count_qb.eq("method", method)
    if min_amount_cents is not None:
        count_qb = count_qb.gte("claimed_amount_cents", min_amount_cents)
    if max_amount_cents is not None:
        count_qb = count_qb.lte("claimed_amount_cents", max_amount_cents)

    count_result = count_qb.execute()
    total = int(count_result.count) if count_result.count is not None else len(count_result.data or [])

    # ── data query (same filters + pagination) ────────────────────────────────
    qb = (
        sb.table("payment_submissions")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("status", status)
    )
    if member_id is not None:
        qb = qb.eq("member_id", member_id)
    if invoice_id is not None:
        qb = qb.eq("invoice_id", invoice_id)
    if method is not None:
        qb = qb.eq("method", method)
    if min_amount_cents is not None:
        qb = qb.gte("claimed_amount_cents", min_amount_cents)
    if max_amount_cents is not None:
        qb = qb.lte("claimed_amount_cents", max_amount_cents)

    qb = qb.order("created_at", desc=True).limit(limit).range(offset, offset + limit - 1)
    result = qb.execute()
    data = result.data or []

    # Evidence metadata (never the bytes) so a reviewer can open the proof from
    # the queue row. One extra query for the whole page.
    if data:
        evidence_rows = (
            sb.table("payment_evidence")
            .select("id, submission_id, content_type, size_bytes, created_at")
            .eq("chapter_id", chapter_id)
            .in_("submission_id", [str(row["id"]) for row in data])
            .execute()
        ).data or []
        by_submission: dict[str, list[dict]] = {}
        for ev in evidence_rows:
            by_submission.setdefault(str(ev["submission_id"]), []).append(ev)
        data = [{**row, "evidence": by_submission.get(str(row["id"]), [])} for row in data]

    # next_cursor: stringify the next offset if more rows remain
    next_offset = offset + len(data)
    next_cursor: str | None = str(next_offset) if next_offset < total else None

    return {
        "data": data,
        "next_cursor": next_cursor,
        "total": total,
    }


# ════════════════════════════════════════════════════════════════════════════
# Chunk F-complete — Dashboard
# ════════════════════════════════════════════════════════════════════════════
def dashboard_summary(sb, *, chapter_id: str, recent_limit: int = 10) -> dict:
    """Single treasurer aggregate for a chapter (all integer cents).

    Returns:
        {
            "chapter_balance_cents": int,        # BalanceEngine.chapter_balance
            "total_outstanding_cents": int,      # Σ member outstanding > 0
            "pending_proof_count": int,          # payment_submissions status=pending
            "overdue_invoice_count": int,        # unpaid|partially_paid invoices
            "members_with_balance_count": int,   # member accounts outstanding > 0
            "recent_payments": list[dict],       # newest verified_payments
            "recent_expenses": list[dict],       # newest active chapter_expenses
        }
    """
    engine = BalanceEngine(sb)
    chapter_balance_cents = engine.chapter_balance(chapter_id).cents

    # Member finance accounts (the cache) — sum outstanding, count those > 0.
    accounts = (
        sb.table("member_finance_accounts")
        .select("outstanding_balance_cents")
        .eq("chapter_id", chapter_id)
        .execute()
    ).data or []
    outstanding_values = [int(r["outstanding_balance_cents"]) for r in accounts]
    total_outstanding_cents = sum(v for v in outstanding_values if v > 0)
    members_with_balance_count = sum(1 for v in outstanding_values if v > 0)

    # Pending proofs awaiting review.
    pending = (
        sb.table("payment_submissions")
        .select("id", count="exact")
        .eq("chapter_id", chapter_id)
        .eq("status", "pending")
        .execute()
    )
    pending_proof_count = (
        int(pending.count) if pending.count is not None else len(pending.data or [])
    )

    # Overdue invoices = not yet fully paid and not cancelled.
    overdue = 0
    for status in ("unpaid", "partially_paid"):
        res = (
            sb.table("unpaid_invoices")
            .select("id", count="exact")
            .eq("chapter_id", chapter_id)
            .eq("status", status)
            .execute()
        )
        overdue += int(res.count) if res.count is not None else len(res.data or [])

    recent_payments = (
        sb.table("verified_payments")
        .select("*")
        .eq("chapter_id", chapter_id)
        .order("created_at", desc=True)
        .limit(recent_limit)
        .execute()
    ).data or []
    submission_ids = [r["submission_id"] for r in recent_payments if r.get("submission_id")]
    submissions = []
    if submission_ids:
        submissions = (
            sb.table("payment_submissions")
            .select("id, method")
            .eq("chapter_id", chapter_id)
            .in_("id", submission_ids)
            .execute()
        ).data or []
    methods = {r["id"]: r["method"] for r in submissions}
    recent_payments = [
        {**r, "method": methods.get(r.get("submission_id"))} for r in recent_payments
    ]
    recent_expenses = (
        sb.table("chapter_expenses")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(recent_limit)
        .execute()
    ).data or []

    return {
        "chapter_balance_cents": chapter_balance_cents,
        "total_outstanding_cents": total_outstanding_cents,
        "pending_proof_count": pending_proof_count,
        "overdue_invoice_count": overdue,
        "members_with_balance_count": members_with_balance_count,
        "recent_payments": recent_payments,
        "recent_expenses": recent_expenses,
    }


# ════════════════════════════════════════════════════════════════════════════
# Chunk F-complete — Member statement
# ════════════════════════════════════════════════════════════════════════════
def member_statement(sb, *, member_id: str) -> dict:
    """A member's chronological financial events + current owed/credit.

    Entries are tagged with a `type` (invoice|payment|adjustment|refund), the
    source row `id`, a signed `amount_cents`, and `occurred_at` (created_at).
    Only ACTIVE financial events are shown: cancelled invoices, pending
    adjustments (deviation #12), and invalidated refunds do not move a balance
    and are excluded so the statement reconciles with the BalanceEngine.

    The reported `current_balance_cents` is computed by the SAME BalanceEngine
    the rest of Treasury uses, so the statement and the cache never disagree.
    """
    entries: list[dict] = []

    invoices = (
        sb.table("unpaid_invoices")
        .select("*")
        .eq("member_id", member_id)
        .execute()
    ).data or []
    for row in invoices:
        if row["status"] == "cancelled":
            continue
        entries.append(
            {
                "type": "invoice",
                "id": row["id"],
                "amount_cents": int(row["amount_cents"]),  # positive = owed
                "occurred_at": row["created_at"],
                "detail": {"kind": row["kind"], "status": row["status"],
                           "description": row.get("description")},
            }
        )

    payments = (
        sb.table("verified_payments")
        .select("*")
        .eq("member_id", member_id)
        .execute()
    ).data or []
    for row in payments:
        entries.append(
            {
                "type": "payment",
                "id": row["id"],
                "amount_cents": -int(row["amount_cents"]),  # money in reduces what is owed
                "occurred_at": row["created_at"],
                "detail": {},
            }
        )

    adjustments = (
        sb.table("finance_adjustments")
        .select("*")
        .eq("member_id", member_id)
        .eq("status", "active")  # pending adjustments have no balance effect (#12)
        .execute()
    ).data or []
    for row in adjustments:
        entries.append(
            {
                "type": "adjustment",
                "id": row["id"],
                "amount_cents": int(row["delta_cents"]),  # signed
                "occurred_at": row["created_at"],
                "detail": {"kind": row["kind"], "reason": row["reason"]},
            }
        )

    refunds = (
        sb.table("refunds")
        .select("*")
        .eq("member_id", member_id)
        .eq("status", "active")
        .execute()
    ).data or []
    for row in refunds:
        entries.append(
            {
                "type": "refund",
                "id": row["id"],
                # A refund returns paid-in money, raising the net position (deviation #11).
                "amount_cents": int(row["amount_cents"]),
                "occurred_at": row["created_at"],
                "detail": {"verified_payment_id": row["verified_payment_id"],
                           "reason": row["reason"]},
            }
        )

    entries.sort(key=lambda e: (e["occurred_at"], e["type"], e["id"]))

    figures = BalanceEngine(sb)._member_figures(member_id)
    return {
        "member_id": member_id,
        "entries": entries,
        "total_owed_cents": figures["total_owed_cents"],
        "total_paid_cents": figures["total_paid_cents"],
        "outstanding_balance_cents": figures["outstanding_balance_cents"],
        "current_balance_cents": figures["current_balance_cents"],
    }


# ════════════════════════════════════════════════════════════════════════════
# Chunk F-complete — Period CSV exports
# ════════════════════════════════════════════════════════════════════════════
_REPORT_DATASETS = {"payments", "invoices", "expenses", "member_balances", "ledger"}


def _period_bounds(period: str) -> tuple[str, str]:
    """Parse a 'YYYY-MM' period into [start, next_month_start) ISO UTC bounds.

    Raises ValueError on a malformed period (e.g. '2026-13' or 'not-a-period').
    """
    try:
        year_s, month_s = period.split("-")
        year, month = int(year_s), int(month_s)
        start = datetime(year, month, 1, tzinfo=timezone.utc)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid period (expected YYYY-MM): {period!r}") from exc
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start.isoformat(), end.isoformat()


def _csv_from_rows(rows: list[dict], columns: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: ("" if row.get(c) is None else row.get(c)) for c in columns})
    return buf.getvalue()


def period_report_csv(sb, *, chapter_id: str, period: str, dataset: str) -> str:
    """Return a CSV string for one chapter's `dataset` over `period` (YYYY-MM).

    Datasets: payments | invoices | expenses | member_balances | ledger.
    All datasets are chapter-scoped. The period bounds the `created_at` of the
    period-bound datasets; `member_balances` is a current snapshot (not period
    bound) but still requires a valid period argument for a uniform API.
    Raises ValueError on an unknown dataset or malformed period.
    """
    if dataset not in _REPORT_DATASETS:
        raise ValueError(f"Unknown report dataset: {dataset!r}")
    start, end = _period_bounds(period)

    if dataset == "member_balances":
        rows = (
            sb.table("member_finance_accounts")
            .select("*")
            .eq("chapter_id", chapter_id)
            .order("member_id")
            .execute()
        ).data or []
        columns = [
            "chapter_id", "member_id", "total_owed_cents", "total_paid_cents",
            "outstanding_balance_cents", "current_balance_cents", "recomputed_at",
        ]
        return _csv_from_rows(rows, columns)

    table, columns = {
        "payments": (
            "verified_payments",
            ["id", "chapter_id", "member_id", "invoice_id", "submission_id",
             "amount_cents", "verified_by", "verified_at", "created_at"],
        ),
        "invoices": (
            "unpaid_invoices",
            ["id", "chapter_id", "member_id", "kind", "amount_cents", "status",
             "description", "created_at"],
        ),
        "expenses": (
            "chapter_expenses",
            ["id", "chapter_id", "category", "amount_cents", "status",
             "description", "created_by", "created_at"],
        ),
        "ledger": (
            "big_ledger",
            ["id", "chapter_id", "created_at", "entry_type", "amount_cents",
             "member_id", "source_table", "source_id", "status"],
        ),
    }[dataset]

    rows = (
        sb.table(table)
        .select("*")
        .eq("chapter_id", chapter_id)
        .gte("created_at", start)
        .lte("created_at", end)
        .order("created_at")
        .execute()
    ).data or []
    # Half-open interval [start, end): drop any row exactly at the next-month boundary.
    rows = [r for r in rows if str(r["created_at"]) < end]
    return _csv_from_rows(rows, columns)

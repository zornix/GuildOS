"""Payment review service — verify / reject submissions, receipts, orphan sweep.

Verification is the highest-stakes operation in Treasury: it is delegated to the
`tr_verify_payment` RPC (one atomic txn) which is the ONLY path that creates a
verified payment, its immutable receipt, and the PAYMENT_RECEIVED ledger entry.
The service refreshes the member's cached balance afterwards and fires exactly one
approval notification (never on an idempotent replay).
"""

from __future__ import annotations

from api.treasury.core.balance import BalanceEngine
from api.treasury.db.rpc import call_rpc
from api.treasury.notifications import notify_payment_approved, notify_payment_rejected


def _strip_internal(row: dict) -> dict:
    """Drop RPC-internal fields (prefixed with '_') before returning to callers."""
    return {k: v for k, v in row.items() if not k.startswith("_")}


def verify_payment(
    sb,
    *,
    chapter_id: str,
    submission_id: str,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tr_verify_payment",
        {
            "p_chapter_id": chapter_id,
            "p_submission_id": submission_id,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    vp = result.data
    created = bool(vp.get("_created"))
    clean = _strip_internal(vp)

    # Refresh the member's cached balance from operational tables (Python, not RPC).
    BalanceEngine(sb).recompute_member(clean["member_id"])

    # Exactly one approval notification — only on first creation, never on replay.
    if created:
        notify_payment_approved(
            chapter_id=chapter_id,
            member_id=clean["member_id"],
            submission_id=submission_id,
            sb=sb,
        )
    return clean


def reject_payment(
    sb,
    *,
    chapter_id: str,
    submission_id: str,
    actor_id: str,
    reason: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tr_reject_payment",
        {
            "p_chapter_id": chapter_id,
            "p_submission_id": submission_id,
            "p_actor_id": actor_id,
            "p_reason": reason,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    submission = result.data
    # No money moves on rejection — no recompute, no ledger.
    notify_payment_rejected(
        chapter_id=chapter_id,
        member_id=submission["member_id"],
        submission_id=submission_id,
        sb=sb,
    )
    return submission


def get_receipt(sb, *, chapter_id: str, receipt_id: str) -> dict | None:
    row = (
        sb.table("receipts")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("id", receipt_id)
        .maybe_single()
        .execute()
    ).data
    return row or None


def select_orphaned_proofs(sb, *, chapter_id: str, retention_days: int) -> list[dict]:
    """Select rejected submissions whose proof has aged past the retention window.

    This is the SELECTION step of the cron orphan-sweep — it deletes NOTHING. The
    caller decides what to do with stale proof references.
    """
    rows = (
        sb.table("payment_submissions")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("status", "rejected")
        .execute()
    ).data or []

    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    orphaned: list[dict] = []
    for row in rows:
        reviewed_at = row.get("reviewed_at")
        if reviewed_at is None:
            continue
        ts = _as_datetime(reviewed_at)
        if ts is not None and ts < cutoff:
            orphaned.append(row)
    return orphaned


def _as_datetime(value):
    from datetime import datetime, timezone

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None

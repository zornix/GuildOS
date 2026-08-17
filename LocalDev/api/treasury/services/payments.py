"""Payment review service — verify / reject submissions, receipts, orphan sweep.

Verification is the highest-stakes operation in Treasury: it is delegated to the
`tr_verify_payment` RPC (one atomic txn) which is the ONLY path that creates a
verified payment, its immutable receipt, and the PAYMENT_RECEIVED ledger entry.
The service refreshes the member's cached balance afterwards and fires exactly one
approval notification (never on an idempotent replay).
"""

from __future__ import annotations

from api.treasury.core.balance import BalanceEngine
from api.platform.rpc import call_rpc
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


# ── TREASURY V1: balance-level submissions, allocation, evidence ──────────────

MAX_EVIDENCE_BYTES = 2 * 1024 * 1024  # spec: evidence uploads capped at 2 MiB


def submit_balance_payment(
    sb,
    *,
    chapter_id: str,
    member_id: str,
    claimed_amount_cents: int,
    method: str,
    proof_ref: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Member submits a payment against their OVERALL balance (invoice_id NULL).

    Enters 'pending' — no money moves, no ledger (spec §5 Payments).
    """
    result = call_rpc(
        "tr_submit_balance_payment",
        {
            "p_chapter_id": chapter_id,
            "p_member_id": member_id,
            "p_claimed_amount_cents": claimed_amount_cents,
            "p_method": method,
            "p_proof_ref": proof_ref,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data


def verify_payment_v2(
    sb,
    *,
    chapter_id: str,
    submission_id: str,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    """Verify an invoice-targeted OR balance-level submission, then allocate
    the amount across the member's open invoices oldest-first (decision #2 path).
    Leftover stays as member credit (balance is computed, never stored)."""
    result = call_rpc(
        "tr_verify_payment_v2",
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

    BalanceEngine(sb).recompute_member(clean["member_id"])

    if created:
        notify_payment_approved(
            chapter_id=chapter_id,
            member_id=clean["member_id"],
            submission_id=submission_id,
            sb=sb,
        )
    return clean


def reallocate_payment(
    sb,
    *,
    chapter_id: str,
    verified_payment_id: str,
    allocations: list[dict],
    actor_id: str,
    reason: str,
    idempotency_key: str | None = None,
) -> dict:
    """Treasurer override of a verified payment's allocation (append-only:
    reversal rows + a new allocation set; reason REQUIRED, audit-logged)."""
    if reason is None or not str(reason).strip():
        raise ValueError("a reason is required to reallocate a payment")
    result = call_rpc(
        "tr_reallocate_payment",
        {
            "p_chapter_id": chapter_id,
            "p_verified_payment_id": verified_payment_id,
            "p_allocations": allocations,
            "p_actor_id": actor_id,
            "p_reason": reason,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    payload = result.data
    # Allocation moves coverage between invoices of ONE member; refresh their cache.
    vp = (
        sb.table("verified_payments")
        .select("member_id")
        .eq("chapter_id", chapter_id)
        .eq("id", verified_payment_id)
        .maybe_single()
        .execute()
    ).data
    if vp:
        BalanceEngine(sb).recompute_member(vp["member_id"])
    return payload


def list_allocations(sb, *, chapter_id: str, verified_payment_id: str) -> list[dict]:
    return (
        sb.table("payment_allocations")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("verified_payment_id", verified_payment_id)
        .order("created_at")
        .execute()
    ).data or []


def get_submission(sb, *, chapter_id: str, submission_id: str) -> dict | None:
    row = (
        sb.table("payment_submissions")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("id", submission_id)
        .maybe_single()
        .execute()
    ).data
    return row or None


def add_evidence(
    sb, *, chapter_id: str, submission_id: str, content_type: str, data: bytes
) -> dict:
    """Attach evidence bytes to a submission (append-only; ≤ 2 MiB).

    Single-row insert — no RPC needed; the DB CHECK + append-only triggers
    enforce the invariants.
    """
    if not data:
        raise ValueError("evidence payload is empty")
    if len(data) > MAX_EVIDENCE_BYTES:
        raise ValueError(f"evidence exceeds the {MAX_EVIDENCE_BYTES} byte limit")
    inserted = (
        sb.table("payment_evidence")
        .insert(
            {
                "chapter_id": chapter_id,
                "submission_id": submission_id,
                "content_type": content_type,
                "data": data,
                "size_bytes": len(data),
            }
        )
        .execute()
    ).data
    row = inserted[0] if isinstance(inserted, list) else inserted
    return {k: v for k, v in row.items() if k != "data"}


def get_evidence(sb, *, chapter_id: str, evidence_id: str) -> dict | None:
    """Fetch one evidence row, data returned base64-encoded."""
    import base64

    row = (
        sb.table("payment_evidence")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("id", evidence_id)
        .maybe_single()
        .execute()
    ).data
    if not row:
        return None
    raw = row.pop("data")
    if isinstance(raw, memoryview):
        raw = bytes(raw)
    elif isinstance(raw, str):  # psycopg2 may surface bytea as hex text via some paths
        raw = bytes.fromhex(raw[2:]) if raw.startswith("\\x") else raw.encode()
    row["data_base64"] = base64.b64encode(raw).decode()
    return row


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

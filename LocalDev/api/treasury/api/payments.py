"""Payment review HTTP surface: verify, reject, fetch receipt.

Mounted on the Treasury router under `/api/treasury`. Verification and rejection
require the `payment:review` capability; reading a receipt requires `treasury:read`.
"""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_current_user
from api.rbac.auth import require_permission
from api.rbac.services.permissions import has_permission
from api.treasury.auth import PAYMENT_REVIEW, TREASURY_READ, require_capability
from api.treasury.db.session import get_treasury_db
from api.treasury.services import payments as svc

router = APIRouter()


class RejectBody(BaseModel):
    reason: str | None = None


class RejectV1Body(BaseModel):
    reason: str = Field(min_length=1)


class BalanceSubmissionCreate(BaseModel):
    amount_cents: int = Field(gt=0)
    method: str = Field(pattern="^(venmo|zelle|cash|bank_transfer|check)$")
    proof_ref: str | None = None


class EvidenceCreate(BaseModel):
    content_type: str = Field(min_length=1)
    data_base64: str = Field(min_length=1)


class AllocationItem(BaseModel):
    invoice_id: str
    amount_cents: int = Field(gt=0)


class ReallocateBody(BaseModel):
    allocations: list[AllocationItem] = Field(min_length=1)
    reason: str = Field(min_length=1)


@router.post("/payments/submissions/{submission_id}/verify")
async def verify_payment(
    submission_id: str,
    user=Depends(require_capability(PAYMENT_REVIEW)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_treasury_db()
    return svc.verify_payment(
        sb,
        chapter_id=user["chapter_id"],
        submission_id=submission_id,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )


@router.post("/payments/submissions/{submission_id}/reject")
async def reject_payment(
    submission_id: str,
    body: RejectBody | None = None,
    user=Depends(require_capability(PAYMENT_REVIEW)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_treasury_db()
    return svc.reject_payment(
        sb,
        chapter_id=user["chapter_id"],
        submission_id=submission_id,
        actor_id=user["id"],
        reason=body.reason if body else None,
        idempotency_key=idempotency_key,
    )


# ── TREASURY V1 surface ───────────────────────────────────────────────────────
# New routes; the legacy /payments/submissions/{id}/verify|reject above stay
# capability-gated and untouched.


@router.post("/payments/balance-submissions")
async def submit_balance_payment(
    body: BalanceSubmissionCreate,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Any member submits a payment against their OWN overall balance (self only)."""
    sb = get_treasury_db()
    return svc.submit_balance_payment(
        sb,
        chapter_id=user["chapter_id"],
        member_id=user["id"],
        claimed_amount_cents=body.amount_cents,
        method=body.method,
        proof_ref=body.proof_ref,
        idempotency_key=idempotency_key,
    )


@router.post("/payments/submissions/{submission_id}/evidence")
async def add_submission_evidence(
    submission_id: str,
    body: EvidenceCreate,
    user=Depends(get_current_user),
):
    """Attach evidence (base64 JSON) to a submission the caller owns."""
    sb = get_treasury_db()
    submission = svc.get_submission(
        sb, chapter_id=user["chapter_id"], submission_id=submission_id
    )
    if submission is None:
        raise HTTPException(404, "Submission not found")
    if str(submission["member_id"]) != str(user["id"]):
        raise HTTPException(403, "Only the submitting member may attach evidence")

    try:
        data = base64.b64decode(body.data_base64, validate=True)
    except Exception:
        raise HTTPException(422, "data_base64 is not valid base64")
    if not data:
        raise HTTPException(422, "evidence payload is empty")
    if len(data) > svc.MAX_EVIDENCE_BYTES:
        raise HTTPException(413, f"evidence exceeds the {svc.MAX_EVIDENCE_BYTES} byte limit")

    return svc.add_evidence(
        sb,
        chapter_id=user["chapter_id"],
        submission_id=submission_id,
        content_type=body.content_type,
        data=data,
    )


@router.get("/payments/evidence/{evidence_id}")
async def get_submission_evidence(
    evidence_id: str,
    user=Depends(get_current_user),
):
    """Evidence read: reviewers (treasury:payment:verify) or the submitting member."""
    sb = get_treasury_db()
    evidence = svc.get_evidence(sb, chapter_id=user["chapter_id"], evidence_id=evidence_id)
    if evidence is None:
        raise HTTPException(404, "Evidence not found")

    submission = svc.get_submission(
        sb, chapter_id=user["chapter_id"], submission_id=evidence["submission_id"]
    )
    is_owner = submission is not None and str(submission["member_id"]) == str(user["id"])
    if not is_owner and not has_permission(user, "treasury:payment:verify"):
        raise HTTPException(403, "Missing permission: treasury:payment:verify")
    return evidence


@router.post("/payments/submissions/{submission_id}/verify-v1")
async def verify_payment_v1(
    submission_id: str,
    user=Depends(require_permission("treasury:payment:verify")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Verify + allocate oldest-first. Verifiers = full Finance Board (decision #2)."""
    sb = get_treasury_db()
    return svc.verify_payment_v2(
        sb,
        chapter_id=user["chapter_id"],
        submission_id=submission_id,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )


@router.post("/payments/submissions/{submission_id}/reject-v1")
async def reject_payment_v1(
    submission_id: str,
    body: RejectV1Body,
    user=Depends(require_permission("treasury:payment:verify")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Reject a submission — reason is MANDATORY and audit-logged (spec §5)."""
    if not body.reason.strip():
        raise HTTPException(422, "a non-empty reason is required to reject a submission")
    sb = get_treasury_db()
    return svc.reject_payment(
        sb,
        chapter_id=user["chapter_id"],
        submission_id=submission_id,
        actor_id=user["id"],
        reason=body.reason.strip(),
        idempotency_key=idempotency_key,
    )


@router.post("/payments/{verified_payment_id}/reallocate")
async def reallocate_payment(
    verified_payment_id: str,
    body: ReallocateBody,
    user=Depends(require_permission("treasury:invoice:void")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Treasurer-only allocation override (spec: 'Treasurer can override allocation')."""
    if not body.reason.strip():
        raise HTTPException(422, "a non-empty reason is required to reallocate")
    sb = get_treasury_db()
    try:
        return svc.reallocate_payment(
            sb,
            chapter_id=user["chapter_id"],
            verified_payment_id=verified_payment_id,
            allocations=[a.model_dump() for a in body.allocations],
            actor_id=user["id"],
            reason=body.reason.strip(),
            idempotency_key=idempotency_key,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(409, f"Reallocation failed: {exc}")


@router.get("/payments/{verified_payment_id}/allocations")
async def get_payment_allocations(
    verified_payment_id: str,
    user=Depends(get_current_user),
):
    """Allocation transparency: reviewers, or the member the payment belongs to."""
    sb = get_treasury_db()
    vp = (
        sb.table("verified_payments")
        .select("member_id")
        .eq("chapter_id", user["chapter_id"])
        .eq("id", verified_payment_id)
        .maybe_single()
        .execute()
    ).data
    if not vp:
        raise HTTPException(404, "Verified payment not found")
    is_owner = str(vp["member_id"]) == str(user["id"])
    if not is_owner and not has_permission(user, "treasury:payment:verify"):
        raise HTTPException(403, "Missing permission: treasury:payment:verify")
    return svc.list_allocations(
        sb, chapter_id=user["chapter_id"], verified_payment_id=verified_payment_id
    )


@router.get("/payments/receipts/{receipt_id}")
async def get_receipt(
    receipt_id: str,
    user=Depends(require_capability(TREASURY_READ)),
):
    sb = get_treasury_db()
    receipt = svc.get_receipt(sb, chapter_id=user["chapter_id"], receipt_id=receipt_id)
    if receipt is None:
        raise HTTPException(404, "Receipt not found")
    return receipt

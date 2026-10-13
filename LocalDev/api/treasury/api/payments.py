"""Payment review HTTP surface: verify, reject, fetch receipt.

Mounted on the Treasury router under `/api/treasury`. Verification and rejection
require `treasury:payment:verify`; reading a receipt (a row-level financial
record) requires `treasury:audit:view`.
"""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_current_user
from api.rbac.auth import require_permission
from api.rbac.services.permissions import has_permission
from api.platform.db import get_db
from api.platform.errors import public_message
from api.treasury.services import payments as svc

# Catalog permission keys gating this surface (ADR-0001; 0147).
PAYMENT_REVIEW = "treasury:payment:verify"
RECEIPT_VIEW = "treasury:audit:view"

# tr_reallocate_payment's RAISE EXCEPTION texts, as regexes (\S+ = an id).
REALLOCATE_KNOWN_ERRORS = {
    r"a reason is required to reallocate a payment": "A reason is required to reallocate a payment",
    r"p_allocations must be a JSON array": "Allocations must be a JSON array",
    r"verified payment \S+ not found in chapter": "Verified payment not found",
    r"allocations total \(\S+\) exceeds the verified amount": "Allocations total exceeds verified payment amount",
    r"invoice \S+ does not belong to the paying member": "Invoice does not belong to the paying member",
    r"cannot allocate to a cancelled invoice": "Cannot allocate to a cancelled invoice",
    r"invoice \S+ not found in chapter": "Invoice not found",
}

router = APIRouter()


class RejectBody(BaseModel):
    reason: str | None = None


class RejectV1Body(BaseModel):
    reason: str = Field(min_length=1)


class BalanceSubmissionCreate(BaseModel):
    amount_cents: int = Field(gt=0)
    method: str = Field(pattern="^(venmo|zelle|cash|bank_transfer|check)$")
    proof_ref: str | None = None


class RecordPaymentBody(BaseModel):
    member_id: str
    amount_cents: int = Field(gt=0)
    method: str = Field(pattern="^(venmo|zelle|cash|bank_transfer|check)$")
    invoice_id: str | None = None
    reference: str | None = None


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
def verify_payment(
    submission_id: str,
    user=Depends(require_permission(PAYMENT_REVIEW)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    # Frozen URL; same behaviour as /verify-v1 (coverage only via allocations, F-029).
    sb = get_db()
    return svc.verify_payment_v2(
        sb,
        chapter_id=user["chapter_id"],
        submission_id=submission_id,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )


@router.post("/payments/submissions/{submission_id}/reject")
def reject_payment(
    submission_id: str,
    body: RejectBody | None = None,
    user=Depends(require_permission(PAYMENT_REVIEW)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_db()
    return svc.reject_payment(
        sb,
        chapter_id=user["chapter_id"],
        submission_id=submission_id,
        actor_id=user["id"],
        reason=body.reason if body else None,
        idempotency_key=idempotency_key,
    )


# ── TREASURY V1 surface ───────────────────────────────────────────────────────
# New routes; the legacy /payments/submissions/{id}/verify|reject above resolve
# to the same catalog key (treasury:payment:verify) since 0147.


@router.post("/payments/balance-submissions")
def submit_balance_payment(
    body: BalanceSubmissionCreate,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Any member submits a payment against their OWN overall balance (self only)."""
    sb = get_db()
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
def add_submission_evidence(
    submission_id: str,
    body: EvidenceCreate,
    user=Depends(get_current_user),
):
    """Attach evidence (base64 JSON) to a submission the caller owns."""
    sb = get_db()
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

    try:
        return svc.add_evidence(
            sb,
            chapter_id=user["chapter_id"],
            submission_id=submission_id,
            data=data,
        )
    except svc.UnsupportedEvidenceType as exc:
        raise HTTPException(415, str(exc))
    except svc.EvidenceConflict as exc:
        raise HTTPException(409, str(exc))


@router.get("/payments/evidence/{evidence_id}")
def get_submission_evidence(
    evidence_id: str,
    user=Depends(get_current_user),
):
    """Evidence read: reviewers (treasury:payment:verify) or the submitting member."""
    sb = get_db()
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
def verify_payment_v1(
    submission_id: str,
    user=Depends(require_permission("treasury:payment:verify")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Verify + allocate oldest-first. Verifiers = full Finance Board."""
    sb = get_db()
    return svc.verify_payment_v2(
        sb,
        chapter_id=user["chapter_id"],
        submission_id=submission_id,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )


@router.post("/payments/record")
def record_payment(
    body: RecordPaymentBody,
    user=Depends(require_permission(PAYMENT_REVIEW)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Officer records a payment for a member: submit + verify in one step."""
    sb = get_db()
    try:
        return svc.record_payment(
            sb,
            chapter_id=user["chapter_id"],
            member_id=body.member_id,
            amount_cents=body.amount_cents,
            method=body.method,
            actor_id=user["id"],
            invoice_id=body.invoice_id,
            reference=body.reference,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        msg = str(exc)
        if "idempotency_key_reused" in msg:
            raise HTTPException(409, "Idempotency key was already used with a different request")
        if "not in chapter" in msg or "not found in chapter" in msg or "does not belong" in msg:
            raise HTTPException(404, "Member or invoice not found in this chapter")
        if "cancelled invoice" in msg or "already fully paid" in msg:
            raise HTTPException(409, "That invoice is cancelled or already paid")
        raise


@router.post("/payments/submissions/{submission_id}/reject-v1")
def reject_payment_v1(
    submission_id: str,
    body: RejectV1Body,
    user=Depends(require_permission("treasury:payment:verify")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Reject a submission — reason is MANDATORY and audit-logged."""
    if not body.reason.strip():
        raise HTTPException(422, "a non-empty reason is required to reject a submission")
    sb = get_db()
    return svc.reject_payment(
        sb,
        chapter_id=user["chapter_id"],
        submission_id=submission_id,
        actor_id=user["id"],
        reason=body.reason.strip(),
        idempotency_key=idempotency_key,
    )


@router.post("/payments/{verified_payment_id}/reallocate")
def reallocate_payment(
    verified_payment_id: str,
    body: ReallocateBody,
    user=Depends(require_permission("treasury:invoice:void")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Treasurer-only allocation override."""
    if not body.reason.strip():
        raise HTTPException(422, "a non-empty reason is required to reallocate")
    sb = get_db()
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
        raise HTTPException(
            409,
            public_message(exc, REALLOCATE_KNOWN_ERRORS, "Reallocation could not be applied"),
        )


@router.get("/payments/{verified_payment_id}/allocations")
def get_payment_allocations(
    verified_payment_id: str,
    user=Depends(get_current_user),
):
    """Allocation transparency: reviewers, or the member the payment belongs to."""
    sb = get_db()
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
def get_receipt(
    receipt_id: str,
    user=Depends(require_permission(RECEIPT_VIEW)),
):
    sb = get_db()
    receipt = svc.get_receipt(sb, chapter_id=user["chapter_id"], receipt_id=receipt_id)
    if receipt is None:
        raise HTTPException(404, "Receipt not found")
    return receipt

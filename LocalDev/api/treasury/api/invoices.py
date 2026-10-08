"""Receivables HTTP surface: invoices, submissions, cancel, bulk, V1 void.

All amounts cross the wire in cents. Mounted on the Treasury router under
`/api/treasury` by `router.py`.

create accepts due_at + line_items + source ('dues'|'fine'|'manual'
→ kind), issued_by is populated from the actor, and responses map raw statuses to
the vocabulary (open/void + raw_status + overdue). Void is Treasurer-only
(rbac `treasury:invoice:void`) and requires a reason.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException

from api.dependencies import get_current_user
from api.rbac.auth import require_permission
from api.platform.db import get_db
from api.platform.errors import public_message
from api.treasury.services import invoices as svc
from pydantic import BaseModel, Field

# Catalog permission keys gating this surface (ADR-0001; 0147).
INVOICE_CREATE = "treasury:invoice:create"

# tr_void_invoice's RAISE EXCEPTION texts, as regexes (\S+ = an id).
VOID_KNOWN_ERRORS = {
    r"a reason is required to void an invoice": "A reason is required to void an invoice",
    r"only unpaid or partially_paid invoices may be voided": "Only unpaid or partially paid invoices may be voided",
    r"invoice \S+ not found in chapter": "Invoice not found",
}

router = APIRouter()


class LineItem(BaseModel):
    description: str = Field(min_length=1)
    amount_cents: int = Field(gt=0)


class InvoiceCreate(BaseModel):
    member_id: str
    # `source` is the V1 vocabulary; `kind` kept for backward compatibility.
    source: str | None = Field(default=None, pattern="^(dues|fine|manual)$")
    kind: str | None = Field(default=None, pattern="^(dues|rent|utilities|fine|assessment|manual)$")
    amount_cents: int = Field(gt=0)
    description: str | None = None
    due_at: datetime | None = None
    line_items: list[LineItem] | None = None


class BulkInvoiceItem(BaseModel):
    member_id: str
    kind: str = Field(pattern="^(dues|rent|utilities|fine|assessment|manual)$")
    amount_cents: int = Field(gt=0)
    description: str | None = None
    # A dues run has one due date for the whole batch; the RPC reads it per item
    # so a caller can still vary it (0158).
    due_at: datetime | None = None


class BulkInvoiceCreate(BaseModel):
    invoices: list[BulkInvoiceItem] = Field(min_length=1)


class SubmissionCreate(BaseModel):
    invoice_id: str
    claimed_amount_cents: int = Field(gt=0)
    method: str = Field(pattern="^(venmo|zelle|cash|bank_transfer|check)$")
    proof_ref: str | None = None


class VoidBody(BaseModel):
    reason: str


@router.post("/invoices")
def create_invoice(
    body: InvoiceCreate,
    user=Depends(require_permission(INVOICE_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    kind = body.source or body.kind
    if not kind:
        raise HTTPException(422, "one of `source` (dues|fine|manual) or `kind` is required")
    sb = get_db()
    invoice = svc.create_invoice_v2(
        sb,
        chapter_id=user["chapter_id"],
        member_id=body.member_id,
        kind=kind,
        amount_cents=body.amount_cents,
        description=body.description,
        actor_id=user["id"],
        due_at=body.due_at.isoformat() if body.due_at else None,
        issued_by=user["id"],
        line_items=[li.model_dump() for li in body.line_items] if body.line_items else None,
        idempotency_key=idempotency_key,
    )
    return svc.present_invoice_v1(invoice)


@router.post("/invoices/{invoice_id}/void")
def void_invoice(
    invoice_id: str,
    body: VoidBody,
    user=Depends(require_permission("treasury:invoice:void")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Void/waive an invoice — Treasurer only, reason required, logged."""
    if not body.reason.strip():
        raise HTTPException(422, "a non-empty reason is required to void an invoice")
    sb = get_db()
    try:
        invoice = svc.void_invoice(
            sb,
            chapter_id=user["chapter_id"],
            invoice_id=invoice_id,
            actor_id=user["id"],
            reason=body.reason.strip(),
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise HTTPException(
            409,
            public_message(exc, VOID_KNOWN_ERRORS, "Invoice cannot be voided"),
        )
    return svc.present_invoice_v1(invoice)


@router.post("/invoices/bulk")
def bulk_create_invoices(
    body: BulkInvoiceCreate,
    user=Depends(require_permission(INVOICE_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_db()
    try:
        return svc.bulk_create_invoices(
            sb,
            chapter_id=user["chapter_id"],
            # mode="json" so due_at reaches the RPC as an ISO string, not a datetime
            # the JSON encoder would choke on.
            invoices=[i.model_dump(mode="json") for i in body.invoices],
            actor_id=user["id"],
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        if "idempotency_key_reused" in str(exc):
            raise HTTPException(
                409, "This request was already submitted with different details. Start a new one."
            )
        raise


@router.post("/invoices/{invoice_id}/cancel")
def cancel_invoice(
    invoice_id: str,
    user=Depends(require_permission(INVOICE_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_db()
    invoice = svc.cancel_invoice(
        sb,
        chapter_id=user["chapter_id"],
        invoice_id=invoice_id,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )
    return svc.present_invoice_v1(invoice)


@router.post("/payments/submissions")
def submit_payment(
    body: SubmissionCreate,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_db()
    return svc.submit_payment(
        sb,
        chapter_id=user["chapter_id"],
        member_id=user["id"],
        invoice_id=body.invoice_id,
        claimed_amount_cents=body.claimed_amount_cents,
        method=body.method,
        proof_ref=body.proof_ref,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )

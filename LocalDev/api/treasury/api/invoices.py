"""Receivables HTTP surface: invoices, submissions, cancel, bulk.

All amounts cross the wire in cents. Mounted on the Treasury router under
`/api/treasury` by `router.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from api.dependencies import get_current_user
from api.treasury.api.schemas import TreasuryMessage  # noqa: F401  (contract anchor)
from api.treasury.auth import INVOICE_CREATE, require_capability
from api.treasury.db.session import get_treasury_db
from api.treasury.services import invoices as svc
from pydantic import BaseModel, Field

router = APIRouter()


class InvoiceCreate(BaseModel):
    member_id: str
    kind: str = Field(pattern="^(dues|rent|utilities|fine|assessment)$")
    amount_cents: int = Field(gt=0)
    description: str | None = None


class BulkInvoiceItem(BaseModel):
    member_id: str
    kind: str = Field(pattern="^(dues|rent|utilities|fine|assessment)$")
    amount_cents: int = Field(gt=0)
    description: str | None = None


class BulkInvoiceCreate(BaseModel):
    invoices: list[BulkInvoiceItem] = Field(min_length=1)


class SubmissionCreate(BaseModel):
    invoice_id: str
    claimed_amount_cents: int = Field(gt=0)
    method: str = Field(pattern="^(venmo|zelle|cash|bank_transfer)$")
    proof_ref: str | None = None


@router.post("/invoices")
async def create_invoice(
    body: InvoiceCreate,
    user=Depends(require_capability(INVOICE_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_treasury_db()
    return svc.create_invoice(
        sb,
        chapter_id=user["chapter_id"],
        member_id=body.member_id,
        kind=body.kind,
        amount_cents=body.amount_cents,
        description=body.description,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )


@router.post("/invoices/bulk")
async def bulk_create_invoices(
    body: BulkInvoiceCreate,
    user=Depends(require_capability(INVOICE_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_treasury_db()
    return svc.bulk_create_invoices(
        sb,
        chapter_id=user["chapter_id"],
        invoices=[i.model_dump() for i in body.invoices],
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )


@router.post("/invoices/{invoice_id}/cancel")
async def cancel_invoice(
    invoice_id: str,
    user=Depends(require_capability(INVOICE_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_treasury_db()
    return svc.cancel_invoice(
        sb,
        chapter_id=user["chapter_id"],
        invoice_id=invoice_id,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )


@router.post("/payments/submissions")
async def submit_payment(
    body: SubmissionCreate,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_treasury_db()
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

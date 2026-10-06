"""Base Treasury API schemas.

Domain-specific DTOs live in per-domain modules as chunks are implemented.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class TreasuryMessage(BaseModel):
    message: str = Field(min_length=1)

class FineSummary(BaseModel):
    total_unpaid: float
    total_paid: float
    total_waived: float
    count_unpaid: int


class FineToInvoice(BaseModel):
    """Float→cents boundary for fines entering Treasury.

    `fine_amount` arrives as a NUMERIC-serialized float from the legacy events/fines
    surface. This is the ONLY sanctioned conversion point; downstream Treasury code
    works in integer cents exclusively. The validator routes through Money.from_numeric
    (Decimal(str(v)) * 100, ROUND_HALF_UP) so no float math ever touches a money value.
    """

    fine_amount: float
    fine_amount_cents: int = 0

    @model_validator(mode="after")
    def _derive_cents(self) -> "FineToInvoice":
        from api.treasury.core.money import Money

        # Stringify the legacy float so Decimal sees the decimal literal, not the
        # binary-float artifact — Money.from_numeric rejects raw float by design.
        object.__setattr__(self, "fine_amount_cents", Money.from_numeric(str(self.fine_amount)).cents)
        return self


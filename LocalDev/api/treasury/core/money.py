"""Money — integer minor-units (cents) value object. No floats, ever.

Frozen contract: treasury-v1-orchestration-plan.md §2.3. Money is the single
representation of currency across Treasury. Floats are rejected at construction
so a stray float can never silently corrupt a balance; the only sanctioned way a
legacy NUMERIC/Decimal value enters Treasury is `from_numeric`, which converts
through Decimal (never binary float) with banker-free ROUND_HALF_UP.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

_CENTS_PER_DOLLAR = Decimal(100)


class Money:
    __slots__ = ("cents",)

    def __init__(self, cents: int):
        # bool is an int subclass — reject it explicitly so Money(True) can't mean 1¢.
        if isinstance(cents, bool) or not isinstance(cents, int):
            raise TypeError(
                f"Money requires integer cents, got {type(cents).__name__}: {cents!r}. "
                "Use Money.from_numeric() to convert dollars/Decimal/str."
            )
        self.cents = cents

    @classmethod
    def from_cents(cls, c: int) -> "Money":
        return cls(c)

    @classmethod
    def from_numeric(cls, v) -> "Money":
        """NUMERIC/Decimal/str/int dollars -> cents, via Decimal(str(v)) * 100, ROUND_HALF_UP.

        The float->cents boundary helper. `float` is rejected; convert at the source
        with Decimal/str so binary-float error never reaches the ledger.
        """
        if isinstance(v, float):
            raise TypeError(
                "Money.from_numeric rejects float; pass a str/Decimal/int "
                f"(got float {v!r}) to avoid binary-float error."
            )
        dollars = Decimal(str(v))
        cents = (dollars * _CENTS_PER_DOLLAR).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return cls(int(cents))

    # ── exact integer arithmetic ─────────────────────────────────────────────

    def _require_money(self, other) -> "Money":
        if not isinstance(other, Money):
            raise TypeError(f"Money arithmetic requires Money, got {type(other).__name__}")
        return other

    def __add__(self, other) -> "Money":
        return Money(self.cents + self._require_money(other).cents)

    def __sub__(self, other) -> "Money":
        return Money(self.cents - self._require_money(other).cents)

    def __neg__(self) -> "Money":
        return Money(-self.cents)

    def __eq__(self, other) -> bool:
        return isinstance(other, Money) and self.cents == other.cents

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __lt__(self, other) -> bool:
        return self.cents < self._require_money(other).cents

    def __le__(self, other) -> bool:
        return self.cents <= self._require_money(other).cents

    def __gt__(self, other) -> bool:
        return self.cents > self._require_money(other).cents

    def __ge__(self, other) -> bool:
        return self.cents >= self._require_money(other).cents

    def __hash__(self) -> int:
        return hash(self.cents)

    # ── presentation ─────────────────────────────────────────────────────────

    def to_dollars_str(self) -> str:
        sign = "-" if self.cents < 0 else ""
        whole, frac = divmod(abs(self.cents), 100)
        return f"{sign}${whole}.{frac:02d}"

    def __repr__(self) -> str:
        return f"Money(cents={self.cents})"

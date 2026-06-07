"""Treasury balance engine.

Reads ONLY operational tables; writes ONLY the cache; NEVER reads big_ledger
(invariant 3 — balances are independent of the ledger).

Method ownership (disjoint):
- __init__ + chapter_balance ............ Chunk D
- member_outstanding/recompute_member/recompute_all ... Chunk B
- chapter-level adjustments term + member adjustment folding ... Chunk E
"""

from __future__ import annotations

from api.treasury.core.money import Money


class BalanceEngine:
    def __init__(self, sb=None, clock=None):
        self._sb = sb
        self._clock = clock

    # ── Chunk D: chapter treasury balance ────────────────────────────────────
    def chapter_balance(self, chapter_id: str) -> Money:
        """verified payments in − active expenses out + chapter-level adjustments.

        Expenses move ONLY this balance, never any member's balance.
        """
        vp = (
            self._sb.table("verified_payments")
            .select("amount_cents")
            .eq("chapter_id", chapter_id)
            .execute()
        ).data or []
        ex = (
            self._sb.table("chapter_expenses")
            .select("amount_cents")
            .eq("chapter_id", chapter_id)
            .eq("status", "active")
            .execute()
        ).data or []

        total_in = sum(int(r["amount_cents"]) for r in vp)
        total_out = sum(int(r["amount_cents"]) for r in ex)
        chapter_adjustments = self._chapter_adjustments_cents(chapter_id)
        refunds_out = self._chapter_refunds_cents(chapter_id)
        return Money.from_cents(total_in - total_out + chapter_adjustments - refunds_out)

    def _chapter_refunds_cents(self, chapter_id: str) -> int:
        """Total ACTIVE refunds paid out of the chapter (Chunk E) — money leaving."""
        rows = (
            self._sb.table("refunds")
            .select("amount_cents")
            .eq("chapter_id", chapter_id)
            .eq("status", "active")
            .execute()
        ).data or []
        return sum(int(r["amount_cents"]) for r in rows)

    def _chapter_adjustments_cents(self, chapter_id: str) -> int:
        """Chapter-level adjustments term (Chunk E).

        Sum delta_cents of ACTIVE, chapter-scoped (member_id IS NULL) adjustments.
        Pending adjustments awaiting sign-off have no balance effect.
        """
        rows = (
            self._sb.table("finance_adjustments")
            .select("delta_cents,member_id")
            .eq("chapter_id", chapter_id)
            .eq("status", "active")
            .execute()
        ).data or []
        return sum(int(r["delta_cents"]) for r in rows if r["member_id"] is None)

    # ── Chunk B: member balance ──────────────────────────────────────────────
    def _member_figures(self, member_id: str) -> dict:
        """Compute a member's balance from OPERATIONAL tables only (never the ledger).

        owed     = non-cancelled invoice amounts
        paid     = verified payments
        current  = owed − paid + member adjustments (signed; negative = credit)
        outstanding = max(0, current)
        """
        invoices = (
            self._sb.table("unpaid_invoices")
            .select("amount_cents,status,chapter_id")
            .eq("member_id", member_id)
            .execute()
        ).data or []
        vps = (
            self._sb.table("verified_payments")
            .select("amount_cents,chapter_id")
            .eq("member_id", member_id)
            .execute()
        ).data or []

        owed = sum(int(r["amount_cents"]) for r in invoices if r["status"] != "cancelled")
        paid = sum(int(r["amount_cents"]) for r in vps)
        adjustments = self._member_adjustments_cents(member_id)
        # A refund returns money the member paid in, so it raises their net position
        # back toward zero (reduces an overpayment credit).
        refunds = self._member_refunds_cents(member_id)
        current = owed - paid + adjustments + refunds
        outstanding = max(0, current)

        chapter_id = None
        if invoices:
            chapter_id = invoices[0]["chapter_id"]
        elif vps:
            chapter_id = vps[0]["chapter_id"]
        return {
            "chapter_id": chapter_id,
            "total_owed_cents": owed,
            "total_paid_cents": paid,
            "current_balance_cents": current,
            "outstanding_balance_cents": outstanding,
        }

    def _member_adjustments_cents(self, member_id: str) -> int:
        """Member-scoped adjustments term (Chunk E).

        Sum delta_cents of ACTIVE finance_adjustments for the member. Pending
        adjustments (awaiting a second officer's sign-off) have no balance effect.
        """
        rows = (
            self._sb.table("finance_adjustments")
            .select("delta_cents")
            .eq("member_id", member_id)
            .eq("status", "active")
            .execute()
        ).data or []
        return sum(int(r["delta_cents"]) for r in rows)

    def _member_refunds_cents(self, member_id: str) -> int:
        """Total ACTIVE refunds returned to the member (Chunk E)."""
        rows = (
            self._sb.table("refunds")
            .select("amount_cents")
            .eq("member_id", member_id)
            .eq("status", "active")
            .execute()
        ).data or []
        return sum(int(r["amount_cents"]) for r in rows)

    def member_outstanding(self, member_id: str) -> Money:
        return Money.from_cents(self._member_figures(member_id)["outstanding_balance_cents"])

    def _resolve_chapter_id(self, member_id: str, figures: dict) -> str | None:
        if figures.get("chapter_id"):
            return figures["chapter_id"]
        row = (
            self._sb.table("members").select("chapter_id").eq("id", member_id).maybe_single().execute()
        ).data
        return row["chapter_id"] if row else None

    def recompute_member(self, member_id: str) -> None:
        figures = self._member_figures(member_id)
        chapter_id = self._resolve_chapter_id(member_id, figures)
        if chapter_id is None:
            return  # nothing to cache for a member with no finance footprint yet
        self._sb.table("member_finance_accounts").upsert(
            {
                "chapter_id": chapter_id,
                "member_id": member_id,
                "total_owed_cents": figures["total_owed_cents"],
                "total_paid_cents": figures["total_paid_cents"],
                "outstanding_balance_cents": figures["outstanding_balance_cents"],
                "current_balance_cents": figures["current_balance_cents"],
                "recomputed_at": (self._clock.now().isoformat() if self._clock else _utcnow_iso()),
            },
            on_conflict="member_id",
        ).execute()

    def recompute_all(self, chapter_id: str) -> None:
        members = (
            self._sb.table("members").select("id").eq("chapter_id", chapter_id).execute()
        ).data or []
        for m in members:
            self.recompute_member(m["id"])


def _utcnow_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()

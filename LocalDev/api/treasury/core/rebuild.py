"""Treasury rebuild engine.

Reconstructs what the ledger and balances *should* be purely from the OPERATIONAL
tables (a shadow reconstruction), diffs the shadow against the live `big_ledger`
and the live `member_finance_accounts` cache, and returns a drift report.

Guarantees:
- It NEVER deletes or updates `big_ledger` (invariant 1 — the ledger is append-only
  and is the audit source of truth; drift there is *reported*, never silently
  rewritten).
- The only thing it may write is the balance cache, and only when asked
  (`apply_repairs=True`), via `BalanceEngine.recompute_all` — which overwrites only
  `member_finance_accounts`.

Reconstruction mirrors exactly how the RPCs append ledger rows:
- INVOICE_CREATED  — one per invoice (+amount); CANCEL_INVOICE (−amount) if cancelled.
- PAYMENT_RECEIVED — one per verified payment (+amount).
- EXPENSE_APPROVED — one per expense (−amount); EXPENSE_REVERSED (+amount) if invalidated.
- ADJUSTMENT_CREATED — one per ACTIVE adjustment (signed delta). A pending,
  over-threshold adjustment has NO ledger row (deviation #12) and is excluded.
- REFUND_ISSUED — one per ACTIVE refund (−amount).

Deviation #3: migrated historical fines (0012) wrote PAYMENT_RECEIVED with
`source_table='unpaid_invoices'` and the invoice id instead of the payment id.
Every entry type, PAYMENT_RECEIVED included, is matched on its source id (F-058);
such a live row is read as an alias of the verified payment whose 0165-migrated
allocation covers that invoice, and nothing else is aliased.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from api.treasury.core.balance import BalanceEngine

# Note 0165 put on the allocation it made from verified_payments.invoice_id.
_MIGRATED_0165_NOTE = "migrated from verified_payments.invoice_id (0165)"

_BALANCE_FIELDS = (
    "total_owed_cents",
    "total_paid_cents",
    "outstanding_balance_cents",
    "current_balance_cents",
)


@dataclass(frozen=True)
class RebuildReport:
    chapter_id: str
    reconstructed_ledger: list[dict] = field(default_factory=list)
    ledger_drift: list[dict] = field(default_factory=list)
    balance_drift: list[dict] = field(default_factory=list)
    reconstructed_chapter_balance_cents: int = 0
    repaired: bool = False

    @property
    def is_clean(self) -> bool:
        return not self.ledger_drift and not self.balance_drift


def _norm(value):
    return None if value is None else str(value)


class RebuildEngine:
    def __init__(self, sb=None, clock=None):
        self._sb = sb
        self._clock = clock
        self._engine = BalanceEngine(sb, clock)

    # ── shadow reconstruction ────────────────────────────────────────────────
    def reconstruct_ledger(self, chapter_id: str) -> list[dict]:
        """Build the multiset of ledger entries the operational tables imply."""
        sb = self._sb
        entries: list[dict] = []

        def add(entry_type, amount_cents, member_id, source_table, source_id):
            entries.append(
                {
                    "entry_type": entry_type,
                    "amount_cents": int(amount_cents),
                    "member_id": _norm(member_id),
                    "source_table": source_table,
                    "source_id": _norm(source_id),
                }
            )

        invoices = (
            sb.table("unpaid_invoices").select("*").eq("chapter_id", chapter_id).execute()
        ).data or []
        for inv in invoices:
            add("INVOICE_CREATED", inv["amount_cents"], inv["member_id"], "unpaid_invoices", inv["id"])
            if inv["status"] == "cancelled":
                add("CANCEL_INVOICE", -int(inv["amount_cents"]), inv["member_id"], "unpaid_invoices", inv["id"])

        payments = (
            sb.table("verified_payments").select("*").eq("chapter_id", chapter_id).execute()
        ).data or []
        for vp in payments:
            add("PAYMENT_RECEIVED", vp["amount_cents"], vp["member_id"], "verified_payments", vp["id"])

        expenses = (
            sb.table("chapter_expenses").select("*").eq("chapter_id", chapter_id).execute()
        ).data or []
        for ex in expenses:
            add("EXPENSE_APPROVED", -int(ex["amount_cents"]), None, "chapter_expenses", ex["id"])
            if ex["status"] == "invalidated":
                add("EXPENSE_REVERSED", int(ex["amount_cents"]), None, "chapter_expenses", ex["id"])

        adjustments = (
            sb.table("finance_adjustments").select("*").eq("chapter_id", chapter_id)
            .eq("status", "active").execute()
        ).data or []
        for adj in adjustments:
            add("ADJUSTMENT_CREATED", adj["delta_cents"], adj["member_id"], "finance_adjustments", adj["id"])

        refunds = (
            sb.table("refunds").select("*").eq("chapter_id", chapter_id)
            .eq("status", "active").execute()
        ).data or []
        for ref in refunds:
            add("REFUND_ISSUED", -int(ref["amount_cents"]), ref["member_id"], "refunds", ref["id"])

        entries.sort(key=lambda e: (e["entry_type"], e["amount_cents"], e["member_id"] or "", e["source_id"] or ""))
        return entries

    # ── diff helpers ─────────────────────────────────────────────────────────
    def _alias_0012_payments(self, chapter_id: str, live: list[dict]) -> list[dict]:
        """Point 0012-shaped PAYMENT_RECEIVED rows (source = invoice) at their payment."""
        rows = (
            self._sb.table("payment_allocations")
            .select("verified_payment_id,invoice_id,reverses_allocation_id")
            .eq("chapter_id", chapter_id).eq("note", _MIGRATED_0165_NOTE).execute()
        ).data or []
        payment_for = {
            _norm(r["invoice_id"]): _norm(r["verified_payment_id"])
            for r in rows
            if r["reverses_allocation_id"] is None
        }
        out = []
        for e in live:
            if e["entry_type"] == "PAYMENT_RECEIVED" and e.get("source_table") == "unpaid_invoices":
                src = _norm(e.get("source_id"))
                e = {**e, "source_id": payment_for.get(src, src)}
            out.append(e)
        return out

    @staticmethod
    def _ledger_key(entry: dict):
        # Every entry is matched to its originating operational row (F-058).
        return (
            entry["entry_type"],
            int(entry["amount_cents"]),
            _norm(entry.get("member_id")),
            _norm(entry.get("source_id")),
        )

    def _diff_ledger(self, reconstructed: list[dict], live: list[dict]) -> list[dict]:
        recon = Counter(self._ledger_key(e) for e in reconstructed)
        live_c = Counter(self._ledger_key(e) for e in live)

        drift: list[dict] = []
        for key in set(recon) | set(live_c):
            r, l = recon[key], live_c[key]
            if r == l:
                continue
            entry_type, amount_cents, member_id, source_id = key
            kind = "missing" if r > l else "extra"
            drift.append(
                {
                    "kind": kind,
                    "entry_type": entry_type,
                    "amount_cents": amount_cents,
                    "member_id": member_id,
                    "source_id": source_id,
                    "count_reconstructed": r,
                    "count_live": l,
                }
            )
        drift.sort(key=lambda d: (d["kind"], d["entry_type"], d["amount_cents"], d["member_id"] or "", d["source_id"] or ""))
        return drift

    def _diff_balances(self, chapter_id: str) -> list[dict]:
        sb = self._sb
        members = (
            sb.table("members").select("id").eq("chapter_id", chapter_id).execute()
        ).data or []
        cache_rows = (
            sb.table("member_finance_accounts").select("*").eq("chapter_id", chapter_id).execute()
        ).data or []
        cache = {str(r["member_id"]): r for r in cache_rows}

        drift: list[dict] = []
        for m in sorted((str(m["id"]) for m in members)):
            figures = self._engine._member_figures(m)
            has_footprint = figures["chapter_id"] is not None
            live = cache.get(m)

            if not has_footprint:
                continue  # no finance activity → no cache row expected
            if live is None:
                drift.append({"member_id": m, "field": "*", "reconstructed": "present", "live": "missing"})
                continue
            for fld in _BALANCE_FIELDS:
                recon_val = int(figures[fld])
                live_val = int(live[fld])
                if recon_val != live_val:
                    drift.append(
                        {"member_id": m, "field": fld, "reconstructed": recon_val, "live": live_val}
                    )
        drift.sort(key=lambda d: (d["member_id"], d["field"]))
        return drift

    # ── public entrypoint ────────────────────────────────────────────────────
    def rebuild(self, chapter_id: str, *, apply_repairs: bool = False) -> RebuildReport:
        reconstructed = self.reconstruct_ledger(chapter_id)
        live = (
            self._sb.table("big_ledger").select("*").eq("chapter_id", chapter_id)
            .eq("status", "active").execute()
        ).data or []

        live = self._alias_0012_payments(chapter_id, live)
        ledger_drift = self._diff_ledger(reconstructed, live)
        balance_drift = self._diff_balances(chapter_id)
        chapter_balance_cents = self._engine.chapter_balance(chapter_id).cents

        if apply_repairs:
            # Overwrites ONLY member_finance_accounts; never touches big_ledger.
            self._engine.recompute_all(chapter_id)

        return RebuildReport(
            chapter_id=chapter_id,
            reconstructed_ledger=reconstructed,
            ledger_drift=ledger_drift,
            balance_drift=balance_drift,
            reconstructed_chapter_balance_cents=chapter_balance_cents,
            repaired=apply_repairs,
        )

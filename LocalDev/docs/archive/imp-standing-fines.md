# Implementation plan — standing reads real fines (unpaid_invoices, cents)

Date: 2026-07-11
Order: step 2 of 7. No dependencies (can land before or after `imp-hygiene`).
Scope: `api/memberadmin/` + the standing DTO consumers in `fratos/`. One
correctness bug fix; no schema changes, no new migration.

Contract: decisions settled here; implementer executes as written, reports
drift.

## The bug

`api/memberadmin/core/engagement.py:88-94` computes unpaid fines from the
legacy `fines` table, which migration `0012_fines_to_invoices_migration.sql`
froze read-only after copying every fine into `unpaid_invoices`
(`kind='fine'`, integer `amount_cents`, deduped by `legacy_fine_id`). Every
fine issued since lives only in `unpaid_invoices`, so standing and the
engagement score see $0 owed for members who genuinely owe fines. Reading
`unpaid_invoices` drops nothing — the migration imported all legacy rows.

## Settled decisions

- **D1 — Standing counts unpaid *fine* invoices only** (product decision,
  2026-07-11, recorded in `CONTEXT.md` → **Standing**): filter
  `kind = 'fine'`. Dues, rent, utilities, and assessments never affect
  standing or the engagement score; that money is visible only in treasury.
- **D2 — The value is integer cents end-to-end** (backend hard rule). The
  dataclass field, service dicts, and API responses all carry
  `unpaid_amount_cents: int`. The old float-dollars `unpaid_amount` field is
  renamed, not kept alongside — no dual fields.
- **D3 — Thresholds convert, semantics don't.** Every dollar-denominated
  constant that compared against the old float becomes the same value in
  cents (×100). The score/standing cutoffs must be numerically identical for
  the same real-world debt.

## Steps

1. `api/memberadmin/core/engagement.py`:
   - Replace the fines query (lines 88-94) with:
     `sb.table("unpaid_invoices").select("member_id, amount_cents")
     .eq("chapter_id", chapter_id).eq("kind", "fine").eq("status", "unpaid")`.
   - `MemberEngagement.unpaid_amount: float` → `unpaid_amount_cents: int`;
     sum `amount_cents`. `unpaid_fines` (the count) keeps its meaning.
   - Note: the local client has no `unpaid_invoices` entry in `FK_MAP`, but
     this query uses no joins — nothing to register.
2. `api/memberadmin/services/scoring.py`: penalty becomes
   `min(row.unpaid_amount_cents / 20000, 0.10)` (was `/ 200` in dollars —
   same $200 cap). Response dict field renames to `unpaid_amount_cents`.
3. `api/memberadmin/services/standing.py`: pass
   `unpaid_total=row.unpaid_amount_cents` and rename the response field to
   `unpaid_amount_cents`.
4. `api/memberadmin/core/standing_rules.py`: read it; any threshold compared
   against `unpaid_total` converts per D3 (×100). Rename the parameter to
   `unpaid_total_cents` so the unit is in the signature.
5. Frontend consumers (grep `unpaid_amount` across `fratos/`): the known site
   is `views/standing.tsx:71` rendering `${m.unpaid_amount}` — becomes
   `formatMoney(m.unpaid_amount_cents)` (`lib/formatters/money.ts`). Update
   the corresponding TS type. Check the scores/reminders surface for the same
   field.
6. Tests (`tests/`, pattern of `tests/treasury/test_v1_fines.py`):
   - A member with an unpaid fine invoice (create via the existing fine RPC
     path) shows that amount in `unpaid_amount_cents` via the engagement
     loader / standings endpoint.
   - A member with only an unpaid **dues** invoice shows
     `unpaid_amount_cents == 0` and no fine-related reason codes (pins D1).
   - A scoring case pinning the ×100 threshold conversion (e.g. a $50 fine
     → penalty 0.025, not 0.10-capped).
   - Update any existing test asserting the old `unpaid_amount` field.

## Verification

`python3 -m pytest` green (full suite — memberadmin, treasury untouched
elsewhere). From `fratos/`: `npm run lint`, `npm run test:unit`,
`npm run build`; `npm run test:e2e` (members/standing flows).

One commit: `fix(standing): compute unpaid fines from unpaid_invoices in cents; dues/rent never affect standing`

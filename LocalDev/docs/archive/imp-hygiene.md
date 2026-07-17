# Implementation plan — dead-weight deletions & doc truth-up

Date: 2026-07-11
Order: step 1 of 7 (see `architecture-review-2026-07-10.md` → plans). No dependencies.
Scope: deletions only, plus doc corrections. No behavior changes anywhere.

This doc follows the same contract as `docs/imp-fe-remediation.md`: decisions
are settled here; an implementer executes as written and reports drift instead
of improvising. Every item below was re-verified dead on 2026-07-11 with
file:line evidence; if a grep at execution time finds a *new* importer, stop
and report — do not delete anyway.

## Settled decisions

- **D1 — Deletion means deletion.** No shims, no re-exports, no commented-out
  code, no "deprecated" markers left behind.
- **D2 — CLAUDE.md tells the truth but stays minimal.** Only the claims proven
  false are corrected here; the db-access and domain-layout rewrites belong to
  `imp-platform-module.md`, not this plan.
- **D3 — `Prod/fratos` is out of scope.** Known consolidation task, tracked
  elsewhere. Never touch `Prod/`.

## Steps

### Backend (`LocalDev/`)

1. Delete `api/routes/` (contains only `__pycache__/`), `api/services/`
   (only an empty `__init__.py`), and `api/models/` (only an imports-only
   `schemas.py` stub + `__init__.py`). Pre-check each: grep for
   `from api.routes`, `from api.services`, `api.models.schemas` — must be
   zero hits outside the dirs themselves.
2. Delete the orphan `EventResponse` class from `api/events/api/schemas.py:102`
   (defined, never imported, never used as a `response_model`).
3. Delete `api/events/CONFORM_TODO.md` — its own status line says
   "conformed"; the work it tracked is done. Keep
   `api/attendance/CONFORM_TODO.md` (still open: legacy handlers not yet
   relocated).

### Frontend (`LocalDev/fratos/`)

4. Delete `components/ui/data-table.tsx` (zero importers; treasury hand-rolled
   its own table).
5. Delete `mocks/data/treasury.ts` (zero importers). If that leaves
   `mocks/data/` empty, remove the directory too.
6. Delete `getFineSummary()` from `lib/api-client.ts:283-284`, the
   `FineSummary` import at `lib/api-client.ts:7`, and the `FineSummary`
   interface at `lib/types.ts:71` (zero callers; the type is stale anyway —
   `total_unpaid` vs the backend's `total_unpaid_cents`).
7. Remove the empty directory `app/treasury-preview/`.
8. Delete the test `"member can pay a fine"` at `e2e/fines.spec.ts:30-38`.
   There is no pay endpoint and no pay button; the test is conditional on a
   button that never renders, so it exercises nothing. (If online fine payment
   ships later, it gets a real test then.)

### Docs

9. `LocalDev/CLAUDE.md`: remove the "Legacy flat modules" paragraph (the
   `api/routes/` / `api/services/` / `api/models/schemas.py` era is over once
   step 1 lands) and reword the conform-shell sentence so it names only
   `api/attendance/` as still carrying a `CONFORM_TODO.md`.

## Verification

From `LocalDev/`: `python3 -m pytest` green.
From `LocalDev/fratos/`: `npm run lint`, `npm run test:unit`, `npm run build`,
`npm run test:e2e` all green (e2e minus the deleted test).
Greps that must return zero after: `getFineSummary`, `FineSummary`,
`data-table`, `mocks/data/treasury`, `from api.routes`, `from api.services`,
`api.models.schemas`, `EventResponse`.

One commit: `chore: delete dead weight flagged by architecture review; truth up CLAUDE.md`

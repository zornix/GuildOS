# Plan 01 — Frontend shell Implementation Plan

> **For agentic workers:** read `00-README.md` (rules, decisions, report block) first. Execute task by task, test first.

**Goal:** every roster/sync/outbox/finance UI behaviour matches the server truth; no fake success, no sticky error state.
**Spec:** `LocalDev/docs/audit/remediation-review.md` §06, §05, §15, §14 (Retry button only).
**Tech:** Vite + React + TypeScript, `node:test` for `lib/*.test.ts`. Run everything from `LocalDev/greekos/`: `npm test`, `npm run lint`, `npm run build`.

**Allowed files:** anything under `LocalDev/greekos/src/`, `LocalDev/greekos/tsconfig*.json`, existing `*.test.ts` files. Nothing outside `greekos/`.

## Task 1 — RV-06-1 (P1, F-045): remove the fake roster mutations

Decision D-R4: the backend has **no** add-member or set-standing endpoint by design (members join by invite `POST /api/auth/invite` or CSV import; standing is derived server-side). `handleAddMember` and `handleUpdateStanding` in `src/hooks/useRoster.ts:24-42` mutate local state, invent an id/dues balance, and toast success. Remove the lie.

- [ ] Find every consumer: `grep -rn "handleAddMember\|handleUpdateStanding\|onAddMember\|onUpdateStanding" src/`.
- [ ] Delete both handlers from `useRoster.ts` and remove them from its return object.
- [ ] Remove the UI entry points that called them (the add-member form/button and the standing editor control in the roster components). If the add-member button is the roster's only way in, repoint it at the existing invite or CSV-import flow already in the app; otherwise delete it. Do not leave a disabled dead button.
- [ ] If any pure logic worth keeping moves to `lib/`, give it a test; otherwise this task is pure deletion.
- [ ] Checkpoint: `npm test && npm run lint && npm run build` all pass; `grep -rn "handleAddMember\|handleUpdateStanding" src/` finds nothing.

## Task 2 — RV-06-2 (P2): `backendDown` sticks forever after one failed startup load

`src/lib/sync.ts:25` and `src/hooks/useBackend.ts:37-51`: after a failed startup load, every later write — even one the server accepted — is toasted "Not saved: the server is unreachable", inviting a duplicate retry (e.g. a second SMS blast). `sync.test.ts` currently asserts this wrong behaviour.

- [ ] Write the failing test in `src/lib/sync.test.ts`: a write that resolves OK after `backendDown` was set must be reported as saved (and clear the down state). Run it; it must fail on the current code.
- [ ] Fix: a successful response clears the down flag / the result classification; the flag only reflects the latest actual outcome.
- [ ] Update the existing wrong assertion in `sync.test.ts` (report it under EXISTING TESTS CHANGED).
- [ ] Checkpoint: `npm test` passes.

## Task 3 — RV-06-3 (P3): mid-session network failure reported as "server refused"

`src/lib/sync.ts:37-39`: a rejected `fetch` (network down, `TypeError`) is reported as "the server refused the change". Distinguish: no response at all → "the server is unreachable"; an HTTP error response → "refused".

- [ ] Failing test first (fetch rejection vs HTTP 4xx produce different messages), then fix, then `npm test`.

## Task 4 — RV-15-1 (P3): one failed refresh throws away the fresh task list

`src/lib/app-data.ts:25-31` uses `Promise.all`; if the event-details refresh rejects (event just cancelled) the fresh task list is discarded too.

- [ ] Failing test first, then switch to `Promise.allSettled` and keep every fulfilled part; a rejected part keeps its previous value. `npm test`.

## Task 5 — RV-14-3 (P3): Retry button shown on rows that always 409

`src/lib/consent.ts:37`, `src/components/OutboxModule.tsx:189`: SETUP_CODE / RESET_CODE outbox rows show Retry, which the server always answers 409 (D21: failed code rows don't keep their code).

- [ ] Put the "is retryable" rule in `lib/` (e.g. extend consent.ts) with a failing test: SETUP_CODE/RESET_CODE → not retryable, other kinds → retryable. Fix the component to use it. `npm test && npm run lint`.

## Task 6 — RV-05-1 (P3): unused `Fragment` import, lint can't see it

`src/App.tsx:1`; `noUnusedLocals` is off so `npm run lint` (tsc) misses it.

- [ ] Remove the import. Turn on `"noUnusedLocals": true` in the tsconfig used by lint; run `npm run lint`. If that surfaces only a handful of trivial unused locals, fix them and keep the flag. If it cascades (>10 errors), revert the flag, keep the import removal, and say so in your report.

## Task 7 — RV-05-2 (P3): event-fine dropdown offers events the server will refuse

`src/lib/transaction.ts:179-180`: the dropdown lists events less than 24h after start; the server 422s them (shown inline, but the option shouldn't be offered).

- [ ] Failing test on the filter (event started <24h ago excluded; ≥24h included), then filter the list with the same 24h rule. `npm test`.

## Task 8 — RV-05-3 (P3): Payments reference column always "N/A"

`src/adapters.ts:264` maps `invoice_id` (always NULL); the officer's `proof_ref` is never shown.

- [ ] Failing test on the adapter (payment with `proof_ref` → reference shows it), then map `proof_ref`. `npm test`.

## Final checkpoint

- [ ] `npm test && npm run lint && npm run build` from `greekos/` — paste the counts in your report.

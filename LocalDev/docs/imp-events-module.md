# Implementation plan — collapse the events relay (module owns the workflow)

Date: 2026-07-11
Order: step 7 of 7. Depends on: `imp-mutation-seam.md` (the workflow hook
builds on `useMutation` + `useApiClient`) and `imp-one-gate.md` (events view
gates are already key-based by then).
Scope: `fratos/` only — `views/events.tsx` and `components/modules/events/`.

Contract: decisions settled here; implementer executes as written, reports
drift. Authority on layering: `../FrontendConventions.md` (modules own
product workflows; pages compose).

## The problem being solved

The events extraction split by markup, not behavior: `views/events.tsx`
(237 lines) kept all 9 state cells, 4 effects (polling, two focus-refetches,
link fetch) and 5 mutation handlers, while `EventDetail` has the widest
interface in the frontend — 27 props, all forwarded, zero behavior. "Set
attendance status" currently spans 6 files.

## Settled decisions

- **D1 — The events module owns the workflow.** A hook
  `components/modules/events/use-event-workflow.ts` owns: attendance
  fetching + polling + focus-refetch for the selected event, active
  check-in-link state, manual-attendance modal state, and the five mutations
  (generate link, kill link, delete event, manual status confirm, process
  fines) built on `useMutation`/`useApiClient`.
- **D2 — `EventDetail` composes; it does not forward.** It calls the
  workflow hook itself. Target interface ≤ 6 props: the selected event (or
  id), `onBack`/`onDeleted` style page-level callbacks, and an optional slot
  or two. `AttendanceRoster` / `AttendanceRow` / `ManualAttendanceModal`
  become module-internal consumers of the hook's returned handlers — no
  handler passes through a component that doesn't use it.
- **D3 — The page shrinks to selection.** `views/events.tsx` keeps: the
  events list fetch, selected-event state, tab/view-mode UI state, and the
  create-event slot. Everything attendance/link/fines moves into the module.
- **D4 — No behavior changes.** Polling cadence, focus refetch, toasts,
  permission gating — identical. This plan moves code, not product behavior.
- **D5 — Deletion test must pass afterwards**: deleting `EventDetail` would
  now lose real behavior (the workflow hook wiring), not just markup.

## Steps

1. Write `use-event-workflow.ts` (D1) by *moving* the state, effects, and
   handlers out of `views/events.tsx` — copy the existing logic verbatim
   where possible (polling interval, focus listeners) so D4 is trivially
   true.
2. Rework `event-detail.tsx` to call the hook (D2); collapse its props
   interface; update `attendance-roster.tsx`, `attendance-row.tsx`,
   `manual-attendance-modal.tsx` to take only what they render with.
3. Shrink `views/events.tsx` to D3. Toast state: if the module needs to
   surface toasts, expose them from the hook rather than lifting state back
   to the page.
4. Vitest: one fake-client spec for the workflow hook (mutation updates
   roster state; link generate/kill transitions) — the mutation-seam plan
   made this possible.
5. Acceptance: `EventDetailProps` ≤ 6 members; `views/events.tsx` well under
   ~100 lines with zero attendance/link/fines handlers; "set attendance
   status" touches ≤ 3 files.

## Verification

From `fratos/`: `npm run lint`, `npm run test:unit`, `npm run build`, and
`npm run test:e2e` — the events, checkin, and excuses Playwright flows are
the guarantee that D4 held.

One commit: `refactor(fratos/events): workflow hook in the events module; EventDetail stops forwarding 27 props`

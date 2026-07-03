# Frontend Audit & Remediation Plan (`fratos/`)

Date: 2026-07-03
Scope: `LocalDev/fratos/` only. Backend (`api/`, `migrations/`, `tests/`) is untouched by this plan.
Status: Part 1 (audit) complete, read-only — no code was changed. Part 2 is the executable plan.

This doc follows the same contract as `docs/imp-ev-ph2.md`: decisions are settled
here; an implementer executes the phases as written and reports drift instead of
improvising. Authority on conventions: `../FrontendConventions.md` and
`LocalDev/CLAUDE.md` (frontend architecture section). Next.js 16 diverges from
training data — read `fratos/node_modules/next/dist/docs/` before writing any
routing code (see `fratos/AGENTS.md`).

---

## Part 1 — Audit findings

### Overall assessment

The layered architecture from `FrontendConventions.md` is real, not aspirational:
`config/theme/tokens.ts`, UI primitives, `hooks/use-permissions.ts`,
capability-gated `config/navigation.ts`, and the adapter→contract pipeline all
exist, and the old monolith `fraternity-os-frontend.tsx` is an 11-line shim.
Adoption is uneven in a load-bearing way:

- Only **treasury** has the adapter/contract data boundary. Every other domain
  flows raw snake_case DTOs from a single `return data as T`
  (`lib/api-client.ts:141`) straight into views and module components.
- The entire app is **one client-side route** inside the App Router.
- One user-visible money bug (verified by reading the code, not just reported).

Migration state: 4 domains have `components/modules/` (auth, dashboard, events,
treasury); 13 legacy views remain (~1,465 lines; largest `views/events.tsx` at
237). No duplicated half-migrations — views act as thin-ish shells, which is the
right transitional shape. `mocks/data/` has zero importers (dead code). 11 of 13
views use `LoadingState`/`EmptyState` consistently.

### Findings by severity

| # | Sev | Finding | Where |
|---|-----|---------|-------|
| F1 | HIGH | 100× money display bug: officer dashboard sums `f.amount` (integer cents) and renders `` `$${unpaidTotal}` `` raw. `views/fines.tsx:60` treats the same field correctly via `formatMoney`. **Verified.** | `views/dashboard.tsx:32-39` |
| F2 | HIGH | `return data as T` cast at the API boundary; adapters/contracts cover treasury only. Backend field names leak into components: `fine_amount`, `member_id`, `created_at`. | `lib/api-client.ts:141`; `components/modules/events/event-row.tsx:22`, `event-detail.tsx:114`; `components/modules/attendance/attendance-roster.tsx:53-56`; `views/command.tsx:108`; `views/bylaws.tsx:111` |
| F3 | HIGH | Single-route SPA: `app/page.tsx` → client shim → `AppShell` switching 13 client views on a client-side `PageId`. No URLs, no per-route code-splitting, no server components. Next 16 docs do not legitimize this pattern. | `app/page.tsx`, `components/layout/app-shell.tsx`, `views/*` |
| F4 | MED | Events module renders `${event.fine_amount}` raw (legacy float-dollars field). Only 3 files in the app import `formatMoney` at all. | `components/modules/events/event-row.tsx:22`, `event-detail.tsx:114` |
| F5 | MED | 19 raw `role ===` checks across 8 files, despite `use-permissions` (only 7 consumers) and `requiredPermission` in `config/navigation.ts`. Mirrors the exact pattern the backend bans. | `views/dashboard.tsx:19,38,43,68`, `views/members.tsx`, `views/fines.tsx`, `views/standing.tsx`, `views/events.tsx`, `components/layout/app-shell.tsx`, `components/layout/page-header.tsx`, `components/layout/sidebar.tsx` |
| F6 | MED | Dual theme systems: 7 files still import legacy `lib/theme.ts` (e.g. `T.ac` at `views/dashboard.tsx:45`) alongside `config/theme/tokens.ts` (54 files). Hardcoded hex outside `components/ui/` is otherwise near zero. | 7 importers of `lib/theme.ts` |
| F7 | MED | `Badge` takes raw color names (`color="red"`, `color="purple"`) with hexes hardcoded in the primitive instead of semantic `tone` variants over tokens. | `components/ui/badge.tsx`; call sites e.g. `components/modules/events/event-row.tsx:21-22` |
| F8 | MED | Module component imports `api-client` directly — modules must not know data provenance. | `components/modules/dashboard/pending-excuses-widget.tsx` |
| F9 | LOW | Ad-hoc `(e as Error).message` narrowing repeated in ~6 views instead of centralized in `use-api`. | `views/recruitment.tsx:68,80`, `views/bylaws.tsx:34,50`, `views/command.tsx:66`, `views/tasks.tsx:42` |
| F10 | LOW | `mocks/data/` has zero importers — dead code. | `mocks/data/` |
| F11 | INFO | LocalDev ↔ Prod `fratos` drift (`diff -rq`, excl. `node_modules`/`.next`): 32 files only in LocalDev, 3 only in Prod, 33 differ. Consolidation is not a pure copy-forward; the 3 Prod-only files need triage. | `LocalDev/fratos` vs `Prod/fratos` |

---

## Part 2 — Implementation plan

### Ground rules

- **Branching:** do NOT build on `feat/events-v1-phase1` (backend Phase 2 work is
  landing there). Branch each phase off `main` after Phase 2 merges, or off the
  then-current integration branch: `fix/fe-money-display` (Phase A),
  `feat/fe-remediation-<phase>` (B–E). One commit per phase minimum; conventional
  messages as given per phase.
- **Scope:** `LocalDev/fratos/` only. Never touch `api/`, `migrations/`,
  `tests/` (backend), or `Prod/`.
- **Verification per phase** (from `LocalDev/fratos/`): `npm run lint`,
  `npm run test:unit`, `npm run build` — all green before commit. Run
  `npm run test:e2e` for phases C and D (they touch role gating and routing,
  which the Playwright role flows exercise).
- **No behavior invention.** Where a capability key or contract field doesn't
  exist yet, add it in the designated config/contract file per the phase spec —
  never inline in a component.

### Settled decisions (do not revisit)

- **D1 — `Fine.amount` is integer cents.** Backend hard rule (money is always
  `BIGINT` cents). All fine amounts render through `formatMoney(cents)`
  (`lib/formatters/money.ts`). The dashboard bug is fixed by formatting, not by
  changing the field.
- **D2 — `Event.fine_amount` is legacy float dollars.** The events adapter is
  the single place that converts it: `fineAmountCents = Math.round(fine_amount * 100)`.
  The events contract carries cents; components format with `formatMoney`. No
  other float→cents conversion may be added anywhere in the frontend.
- **D3 — Role checks are replaced by capabilities, not by prettier role checks.**
  Missing capability keys are added to the existing permission map consumed by
  `hooks/use-permissions.ts` / `config/navigation.ts`. Grepping for
  `role ===`/`role !==` in `views/`, `components/` must return zero after
  Phase C (the auth layer itself may keep its own role handling).
- **D4 — Router split keeps client components.** Each nav entry becomes a thin
  server `app/<segment>/page.tsx` that renders the existing client view. No
  data-fetching rewrite, no server-component conversion in this pass — that is a
  later phase, not this plan.
- **D5 — `lib/theme.ts` is deleted at the end of Phase E.** No shim, no
  re-export. All 7 importers move to `config/theme/tokens.ts`.

### Phase A — Money display hotfix (S; ship immediately)

Fix F1 and F4 without waiting for the adapter work.

1. `views/dashboard.tsx`: import `formatMoney` from `../lib/formatters/money`;
   replace `` `$${unpaidTotal}` `` (line 39) with `formatMoney(unpaidTotal)`.
2. `components/modules/events/event-row.tsx:22` and
   `components/modules/events/event-detail.tsx:114`: replace the raw
   `${event.fine_amount}` interpolation with
   `formatMoney(Math.round(event.fine_amount * 100))`, with a
   `// legacy float-dollars field; adapter takes over in Phase B` marker so
   Phase B knows to remove the inline conversion.
3. Unit test: add a vitest case pinning `formatMoney(12345) === "$123.45"`-style
   behavior if not already covered, plus a regression test for the dashboard
   stat computation if the stat logic is extractable without refactor (if not,
   note it and move on — do not restructure the view in this phase).

Acceptance: officer dashboard "Unpaid Fines" shows dollars.cents; events list
and detail show formatted fine amounts. Commit:
`fix(frontend): format fine amounts as money (100x dashboard display bug)`.

### Phase B — Data boundary: adapters + contracts per domain (M/L)

Goal: `lib/api-client.ts:141`'s `as T` is only ever consumed by adapters.
Treasury (`lib/adapters/`, `lib/contracts/` treasury files) is the canonical
pattern — copy its shape exactly.

1. **Events first**: `lib/contracts/events.ts` (camelCase, `fineAmountCents`,
   ISO-parsed dates), `lib/adapters/events.ts` (snake→camel, D2 conversion,
   status labels, date formatting via `lib/formatters/`). Rewire
   `views/events.tsx` and `components/modules/events/*` to the contract; remove
   the Phase A inline conversions.
2. Then per domain in this order (highest leak first): **attendance**
   (`member_id` leak, `attendance-roster.tsx:53-56`), **fines**, **excuses**,
   **command/announcements** (`created_at` leak, `views/command.tsx:108`),
   **bylaws** (`views/bylaws.tsx:111`), remaining domains mechanically.
3. Fix F8: `pending-excuses-widget.tsx` stops importing `api-client`; data comes
   in as props from its page/view, already adapted.
4. Fix F9 while touching these views: move error-message narrowing into
   `hooks/use-api.ts` (expose `error: string | null` already narrowed); delete
   the ad-hoc `(e as Error).message` sites.
5. Each domain conversion is its own commit:
   `refactor(frontend): <domain> adapter + contract boundary`.

Acceptance: no module/UI component references a snake_case backend field;
`grep -rn "as T" fratos/lib/api-client.ts` still exists but every call site's
result passes through `lib/adapters/` before reaching a component.

### Phase C — Permission gating cleanup (M)

Goal: zero raw `role ===` / `role !==` in `views/` and `components/` (D3).

1. Inventory the 19 checks (F5 file list). For each, identify the capability it
   actually gates (e.g. "see pending excuses" → the same permission that gates
   the excuses officer flows in `config/navigation.ts`).
2. Extend the permission map consumed by `use-permissions` where a key is
   missing; replace each check with the hook (components) or `requiredPermission`
   (nav/layout).
3. `components/layout/app-shell.tsx`, `page-header.tsx`, `sidebar.tsx` must gate
   purely off `config/navigation.ts` entries.
4. Run `npm run test:e2e` (role flows: auth, events, fines, excuses, checkin,
   members) — these are the tests most likely to catch a gating regression.

Acceptance: `grep -rnE "role\s*(===|!==)" fratos/views fratos/components`
returns nothing. Commit:
`refactor(frontend): replace raw role checks with capability gating`.

### Phase D — App Router segment split (L; last, after C)

Goal: one URL per nav entry, per-route code-splitting. D4 applies — thin server
pages wrapping existing client views; no data rewrite.

1. Read `node_modules/next/dist/docs/` routing guide first (Next 16 diverges
   from training data — `fratos/AGENTS.md`).
2. For each entry in `config/navigation.ts`: create `app/<segment>/page.tsx`
   (server component) rendering the corresponding client view. Derive segment
   names from the existing `PageId`s.
3. Replace `AppShell`'s client-side `PageId` switching with layout + `<Link>`
   navigation: `app/layout.tsx` (or a route group layout) owns the shell;
   sidebar items become links. Active-state comes from the pathname, not state.
4. Preserve auth gating behavior exactly (whatever currently guards the SPA
   shell must guard the layout).
5. Update Playwright e2e for real URLs; `npm run test:e2e` green is the
   acceptance gate. Keep `app/page.tsx` as a redirect to the default segment
   (dashboard).

Commit: `refactor(frontend): split SPA into App Router segments`.

### Phase E — Theme, Badge, dead code (S/M; can run before D)

1. F6: migrate the 7 `lib/theme.ts` importers to `config/theme/tokens.ts`
   equivalents; delete `lib/theme.ts` (D5).
2. F7: `components/ui/badge.tsx` gets semantic `tone` variants
   (`neutral | info | success | warning | danger | accent`) mapped to tokens;
   migrate all call sites; remove the raw `color` prop entirely.
3. F10: delete `mocks/data/`.
4. Acceptance: `grep -rn "lib/theme" fratos/` returns nothing;
   `grep -rn 'color="' fratos/components fratos/views | grep -i badge` returns
   nothing; build green. Commit:
   `refactor(frontend): finish token migration, semantic Badge tones, drop dead mocks`.

### Out of scope (tracked, not done here)

- Server-component/data-fetching rewrite of views (follow-up after D).
- LocalDev ↔ Prod `fratos` consolidation (F11) — needs triage of the 3
  Prod-only files first; separate plan.
- Backend changes of any kind, including migrating `events.fine_amount` to
  integer cents at the source (worth a backend ticket; D2 contains it until then).

### Suggested execution

Phase A now (one small PR). B, C, E are independent of each other; D depends on
C (gating must be capability-driven before the shell is rebuilt). Each phase is
sized for a single `implementer` agent run against this doc.

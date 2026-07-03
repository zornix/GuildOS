# Frontend Audit & Remediation Plan (`fratos/`)

Date: 2026-07-03
Scope: `LocalDev/fratos/` only. Backend (`api/`, `migrations/`, `tests/`) is untouched by this plan.
Status: Part 1 (audit) complete. Phase A shipped in `dff39d4` (all three call
sites); its step-3 vitest pin did not land and is carried into Phase B step 1.
Phases B–E remain.

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

- **Branching:** branch each phase off then-current `main` as
  `feat/fe-remediation-<phase>` (B–E). The old feat/events-v1-phase1 caution is
  obsolete (backend Phase 2 merged; Phase A shipped as `dff39d4`). One commit
  per phase minimum; conventional messages as given per phase.
- **Scope:** `LocalDev/fratos/` only, with one sanctioned exception: Phase C
  may add a backend RBAC **seed migration** (0130 pattern, plus pytest
  coverage) when the check inventory finds no existing permission key — see
  D3. No other backend change of any kind; never touch `Prod/`.
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
- **D3 — Role checks are replaced by permission keys, not by prettier role
  checks.** Permission keys are **backend-owned**: `hooks/use-permissions.ts`
  fetches the actor's effective keys from `GET /api/rbac/me/permissions`;
  there is no frontend permission map. Phase C first maps every check onto the
  seeded backend catalog; a genuine gap is filled by a backend RBAC seed
  migration (the one sanctioned backend touch — see Scope). **Why keys, not
  roles:** officer authority will later be split per exec office (e.g.
  announcements → president/VP/secretary only); with `can(key)` gating, that
  split is a backend re-seed with zero frontend changes. Verified safe today:
  the RBAC compatibility resolver maps `members.role = 'officer'` onto the
  seeded `officer` role, so officers keep access through the swap. Grepping for
  `role ===`/`role !==` in `views/`, `components/` must return zero after
  Phase C (the auth layer itself may keep its own role handling).
- **D4 — Router split keeps client components.** Each nav entry becomes a thin
  server `app/<segment>/page.tsx` that renders the existing client view. No
  data-fetching rewrite, no server-component conversion in this pass — that is a
  later phase, not this plan.
- **D5 — `lib/theme.ts` is deleted at the end of Phase E.** No shim, no
  re-export. All 7 importers move to `config/theme/tokens.ts`.
- **D6 — Contracts carry data, not presentation.** Integer cents, ISO-8601
  date/time strings, status enums (adapter-mapped labels where useful) — never
  pre-formatted money/date strings, never presentation fields (tone/color).
  Components render numbers and dates exclusively through `lib/formatters/`
  (the D1 `formatMoney` precedent, generalized). Backend row shapes (`*ApiRow`)
  live in `lib/dto/<domain>.ts`, consumed only by `api-client` call sites and
  adapters; `lib/contracts/` holds frontend-facing shapes only.

### Phase A — Money display hotfix (S; ship immediately)

**Status: shipped in `dff39d4`** (all three call sites). The step-3 vitest pin
did not land — carried into Phase B step 1.

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
pattern — copy its shape exactly *after step 0 brings it up to D6*.

0. **Harden the treasury canon**: rename `TreasuryDashboardMock` →
   `TreasuryDashboard`; move the `*ApiRow` types out of `lib/contracts/` into
   `lib/dto/treasury.ts`; drop the `tone` field from the treasury contracts
   (the stat-card module assigns visuals locally); convert pre-formatted date
   fields to ISO strings rendered via `lib/formatters/` (D6). Align the
   formatting bullet in `../FrontendConventions.md` with D6. Own commit:
   `refactor(frontend): harden treasury contract canon (D6)`.
1. **Events first**: `lib/contracts/events.ts` (camelCase, `fineAmountCents`,
   ISO date strings per D6), `lib/adapters/events.ts` (snake→camel, D2 conversion,
   status labels, date formatting via `lib/formatters/`). Rewire
   `views/events.tsx` and `components/modules/events/*` to the contract; remove
   the Phase A inline conversions. Add the vitest money pin Phase A deferred
   (`formatMoney(12345) === "$123.45"`).
2. Then per domain in this order (highest leak first): **attendance**
   (`member_id` leak, `attendance-roster.tsx:53-56`), **fines**, **excuses**,
   **command/announcements** (`created_at` leak, `views/command.tsx:108`),
   **bylaws** (`views/bylaws.tsx:111`), **members** (contract carries
   `isOfficer: boolean` so the roster badge + Promote/Demote label stop
   comparing role strings — closes Phase C's subject-state leftovers),
   remaining domains mechanically.
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

1. Inventory the 19 checks (F5 file list). For each, identify the permission
   key it actually gates (e.g. "see pending excuses" → the same key that gates
   the excuses officer flows in `config/navigation.ts`), matching against the
   seeded backend catalog (grep the permission seeds in `migrations/`).
2. Where no existing key fits, seed the key + role grants in a backend RBAC
   migration (0130 pattern; the one sanctioned backend change — see Scope).
   Then replace each check with the hook (components) or `requiredPermission`
   (nav/layout). One gap is already known: seed `members:exec:promote`
   (officer + admin) and gate the members-roster Promote/Demote control on it —
   behavior-preserving today; the future president-only tightening is a
   re-seed.
3. `views/members.tsx` lines 21/49/52 compare the **target** member's role
   (badge + Promote/Demote label) — that is subject state, not actor
   authority; no permission key applies. Those move to the members contract's
   `isOfficer: boolean` during Phase B's members conversion. Phase C's own
   acceptance therefore covers **actor** checks (`user.role`); the broad grep
   below is the joint B+C end state.
4. `components/layout/app-shell.tsx`, `page-header.tsx`, `sidebar.tsx` must gate
   purely off `config/navigation.ts` entries. Delete `OFFICER_ONLY`: each of
   its two pages gains a `requiredPermission` instead (`standing` →
   `standing:view_all`; `active-checkins` → the attendance key the inventory
   maps, seeded if missing).
5. Run `npm run test:e2e` (role flows: auth, events, fines, excuses, checkin,
   members) — these are the tests most likely to catch a gating regression.

Acceptance (Phase C alone): zero comparisons on the **actor's** role —
`grep -rnE "user\.role\s*(===|!==)" fratos/views fratos/components` returns
nothing. End state once B's members conversion also lands:
`grep -rnE "role\s*(===|!==)" fratos/views fratos/components` returns nothing.
Commit:
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
4. Preserve auth gating behavior exactly: `AuthProvider` wraps the route-group
   layout, so the login form renders in place at any URL (there is no login
   route today, and the token persists in `localStorage`, so deep links keep
   sessions). Permission-gated segments **redirect unauthorized visitors to
   `/dashboard`** client-side, driven by the same `requiredPermission`
   entries — this is why D depends on C.
5. Update Playwright e2e for real URLs; `npm run test:e2e` green is the
   acceptance gate. Keep `app/page.tsx` as a redirect to the default segment
   (dashboard).

Commit: `refactor(frontend): split SPA into App Router segments`.

### Phase E — Theme, Badge, dead code (S/M; can run before D)

1. F6: migrate the 7 `lib/theme.ts` importers to `config/theme/tokens.ts`
   equivalents; delete `lib/theme.ts` (D5).
2. F7: `components/ui/badge.tsx` gets semantic `tone` variants
   (`neutral | success | warning | danger | accent`) mapped to tokens — these
   are the slots `config/theme/tokens.ts` actually has; there is no `info`
   token, so add one (CSS var included) only if a call site genuinely needs a
   distinct hue. Migrate all call sites; remove the raw `color` prop entirely.
3. F10: delete `mocks/data/`.
4. Acceptance: `grep -rn "lib/theme" fratos/` returns nothing;
   `grep -rn 'color="' fratos/components fratos/views | grep -i badge` returns
   nothing; build green. Commit:
   `refactor(frontend): finish token migration, semantic Badge tones, drop dead mocks`.

### Out of scope (tracked, not done here)

- Server-component/data-fetching rewrite of views (follow-up after D).
- LocalDev ↔ Prod `fratos` consolidation (F11) — needs triage of the 3
  Prod-only files first; separate plan.
- Backend changes of any kind (beyond Phase C's sanctioned seed migrations),
  including migrating `events.fine_amount` to integer cents at the source
  (worth a backend ticket; D2 contains it until then).
- `PUT /members/{member_id}/role` still authorizes via legacy
  `require_officer`; moving it to
  `require_permission("members:exec:promote")` is a backend ticket — Phase C
  only seeds the key and gates the UI.

### Suggested execution

Phase A shipped (`dff39d4`). B (step 0 first), C, E are independent of each
other, except `views/members.tsx`'s subject-state cleanup lands with B (see
Phase C step 3); D depends on C (gating must be permission-key-driven before
the shell is rebuilt). Each phase is sized for a single `implementer` agent run
against this doc.

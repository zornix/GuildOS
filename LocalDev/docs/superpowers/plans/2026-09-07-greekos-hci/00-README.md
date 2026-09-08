# GreekOS HCI slice — implementer guide

> **For agentic workers:** This directory is a set of implementation plans. Each numbered plan is executed by a **fresh Opus 5 subagent** with this README plus its own plan file as its only context. REQUIRED SUB-SKILL for the orchestrator: `superpowers:subagent-driven-development`. Steps use checkbox (`- [ ]`) syntax.

**Spec:** `LocalDev/docs/greekos-hci-handoff.md` (read its "Grill decisions" table first; it overrides the older text below it).
**Domain glossary:** `CONTEXT.md` at repo root. **Firewall:** `docs/adr/0004-standing-contribution-firewall.md`.
**Target:** `LocalDev/greekos` only. Never touch `fratos`, `Prod/`, `api/`, or `migrations/`.

## Execution order

Plans depend on each other in this order. Do not reorder.

| # | Plan | Delivers | Depends on |
|---|---|---|---|
| 01 | `01-foundation.md` | test runner, session permissions, contribution hook, member balance, upcoming-event detail load | — |
| 02 | `02-events-chrome.md` | calendar default, one filter bar shared by both views, lifted create/selection state | 01 |
| 03 | `03-home.md` | welcome + 2×2 Home, upcoming counts, balance status line, inline door-code check-in, Schedule Event opens the form | 01, 02 |
| 04 | `04-treasury.md` | Add transaction (Payment / Fine / Invoice / Adjustment) with preview → confirm, pay modal prefill, honest copy | 01 |
| 05 | `05-safety.md` | roll call with explicit unmarked, confirm dialogs, command chips fill not run, persistent `aria-live` toast, Demo view-as | 01 |
| 06 | `06-language-a11y.md` | jobs = jobs (tags, claim), "Door code" phrase, quieter copy, Modal a11y, labeled ✕ / search | 02, 04, 05 |
| 07 | `07-verify.md` | browser pass (officer + member, desktop + phone), lint, build, tests, impeccable critique, handoff checklist | all |

## Run

```bash
# Terminal A — backend on :8001 (also starts fratos on :3000; stop that or use another port for greekos)
cd LocalDev && npm run dev

# Terminal B
cd LocalDev/greekos && npm run dev -- --port 3002
```

`DEV_AUTH_BYPASS=1` must be in `LocalDev/.env`. Dev login is Jake Martinez, `jake@tke.org`, an officer. Token lives in `localStorage` key `g_token`.

```bash
cd LocalDev/greekos
npm test             # node:test via tsx — added in plan 01
npm run lint         # tsc --noEmit
npm run build        # vite build
```

## TDD rules for this slice

greekos has no DOM test runner and **no new npm dependencies are allowed**. The test runner is Node's built-in `node:test` executed through the already-installed `tsx` (`npm test`, plan 01 task 1).

- **Every branch, loop, parser, money path, or counting rule lives in a pure function in `src/lib/<name>.ts` with a sibling `src/lib/<name>.test.ts`.** Write the failing test first, run it, watch it fail, then implement.
- **Components stay dumb.** They call the pure function and render. A component is verified by `npm run lint` (tsc) and the browser pass in plan 07, not by unit tests.
- **Hooks own API calls. Adapters own DTO → UI.** Money is integer cents in hooks/adapters/lib; dollars only inside form inputs; `formatMoney(cents)` for display.
- Tests use `import { test } from 'node:test'` and `import assert from 'node:assert/strict'`. No mocking libraries. Pure functions take `today`/`now` as a parameter so tests never depend on the clock.
- Run `npm test && npm run lint` before every commit.

## Conventions the implementer must keep

- **No new npm deps. No new prod tables. No backend changes.** If a plan step seems to need one, stop and report; do not improvise.
- Keep: notify gate (1 supervisor / 1 organizer / 3 jobs), 36-hour unclaim lock, door-code `maxLength={6}`, job reject requires a reason, DemoGate, backend-down banner, Mandatory / organizers-needed / open-jobs badges.
- Do not render a ranked roster. Do not put contribution counts anywhere near standing. Personal counts on the member's own Home are fine.
- Use existing helpers before writing new ones: `formatMoney`, `isoDay`, `monthCells`, `Modal`, `Card`, `DemoGate`, `optionalOfficerCall`, `syncApi`.
- Deliberate shortcuts with a known ceiling get a `// ponytail: <ceiling>, <upgrade path>` comment.
- Files that grow past ~400 lines from this work get split by responsibility (new component file next to the old one). Do not restructure files you are not editing.
- Copy rules: **Balance owed** (never "dues balance"), **Unpaid fines** for the standing-derived per-member number, **Door code** (never "Live Door Mode" / "Live Door Check-In"), **Chapter ledger** (never `big_ledger`), **Announcements** (never "Executive Chapter Broadcasts"), **Save roll call** (never "Commit Attendance to Roster"), **Payment / Fine / Invoice / Adjustment** as the transaction kinds, **chaired** (never "led"). No "house jobs".

## Git rules

- Work on branch `feat/greekos-hci` off `main`. Create it in plan 01 task 0; every later plan continues on it.
- **One commit per task**, message in imperative mood with a scope, e.g. `feat(greekos): derive isOfficer from RBAC permissions`.
- **No `Co-Authored-By`, no "Generated with" trailers, no session links** in commits or PRs. This is a standing user rule.
- Never `git add -A`. Stage the files the task names.
- The orchestrator merges with `git merge --no-ff feat/greekos-hci` after plan 07 passes.

## Design decisions (record)

These were decided in the 2026-09-07 grill and while writing these plans. They are not up for relitigation by an implementer. If one turns out to be impossible, report it; do not pick a different design.

| # | Decision | Why |
|---|---|---|
| D1 | greekos is a **design lab**, not a fratos replacement. Client-local prototypes are fine when labeled Demo. | The question this slice answers is "does the UX work", not "does it persist". |
| D2 | Treasury Add Transaction is **client-local for all four kinds**. Kinds use backend words: **Payment, Fine, Invoice, Adjustment**. | Backend endpoints exist (`/treasury/payments/balance-submissions` + `/verify`, `/treasury/adjustments` + `/approve`) but wiring them is a later slice. Same words as the real ledger keeps treasurers oriented. |
| D3 | Home welcome counts are **upcoming only**: organizing N · supervising N · chairing N. Word is **chaired**. They come from one `useContribution` hook whose return shape is the contract the future `GET /api/contribution/me` will fill (issue #40). | Event list rows carry no organizer/supervisor names; only per-event detail does. Upcoming events already get a per-event fetch loop, so counting them is honest and free. Lifetime résumé numbers need the server. |
| D4 | **Every verified job counts toward contribution**, standalone or attached. No "house jobs" copy. Jobs tab lists every job with an event/initiative tag. | User decision; `CONTEXT.md` updated. |
| D5 | **Pay stays on Treasury.** Home shows a status line "Balance owed $X · N open invoices" linking to Treasury. Pay modal prefills from the real balance, not `$150`. Source: `GET /api/treasury/members/{me}/dashboard`. | The number greekos called "dues balance" was unpaid fines from the officer-only standing list, so members always saw $0. |
| D6 | **Check-in happens on Home.** When an upcoming event has a live door link, Home renders the 6-digit code field inline for members. Attendance keeps the door-code tab as the member default. | One input, one existing call, the single most time-sensitive member action. |
| D7 | Roll call: **unmarked stays unmarked.** Save sends only rows a human set and shows "48 present · 3 absent · 9 unmarked". A separate **Mark remaining present** button sets the rest explicitly. | Officers mark absentees and expect the rest present, but a silent default is what the critique flagged. Two taps, nothing invisible. |
| D8 | `isOfficer` derives from `GET /api/rbac/me/permissions` (exists; fratos uses it). Officer view = holds `standing:view_all`. Nav `officerOnly` flags become permission keys. Modules keep their `isOfficer` prop this slice. | Glossary rule: code never branches on a role's name. Per-module permission gating is a later slice. |
| D9 | Sidebar switcher stays, labeled **Demo: view as**, warning styling; header chip says "Viewing as" while active. | Needed to flip views without a second login. |
| D10 | Operate floor trimmed to the a11y floor: `role="dialog"`, `aria-modal`, Escape, overlay dismiss, `aria-label` on every ✕ and search. **Skip** sidebar regroup and Events collapsed sections. | Design-lab polish budget. |
| D11 | Test runner is `node:test` via `tsx`. Logic under test lives in `src/lib/*.ts`. | Zero new deps; matches the existing `selfcheck.ts` / `*.check.ts` pattern but with named, individually-failing tests. |
| D12 | `Member.duesBalanceCents` keeps its field name but every UI label that shows it says **Unpaid fines**. The Treasury prototype uses it as the demo running balance. | Renaming the field is churn across seven files for no user-visible gain in a design lab. `ponytail:` comment marks it. |
| D13 | Command console: Execute and template chips go through a confirm dialog that shows the raw command text. Chips only fill the input. Seeded fake history removed. | A full parse-then-confirm refactor of the 200-line parser is out of budget; the raw text already carries who and amount. |
| D14 | Toast persists until the next toast or explicit dismiss, `role="status" aria-live="polite"`. | 3.5-second toasts with no live region are invisible to screen readers and gone before anyone reads them. |
| D15 | Confirm dialogs for: issue fine, Mark Paid, standing change, announcement delete, bid extend, command run. One `ConfirmDialog` primitive built on `Modal`. | Consequence-bearing actions need who/amount/consequence shown once. |

## Contracts shared across plans

Every implementer sees only their own plan. These are the names and shapes neighbouring plans rely on. Match them exactly.

```ts
// src/lib/session.ts (plan 01)
export const OFFICER_VIEW_KEY = 'standing:view_all';
export function isOfficerView(permissions: Iterable<string>): boolean;
export function can(permissions: Iterable<string>, key: string): boolean;

// src/lib/contribution.ts (plan 01)
export interface ContributionSummary {
  scope: 'upcoming' | 'lifetime';
  eventsOrganized: number;
  eventsSupervised: number;
  initiativesChaired: number;
}
export function upcomingContribution(
  memberName: string, events: ChapterEvent[], initiatives: Initiative[], today: string
): ContributionSummary;

// src/hooks/useContribution.ts (plan 01)
export function useContribution(memberName: string, events: ChapterEvent[], initiatives: Initiative[]): ContributionSummary;

// src/lib/balance.ts (plan 01)
export interface MemberBalance {
  outstandingCents: number;
  openInvoiceCount: number;
  overdueInvoiceCount: number;
}
export function adaptMemberBalance(dto: MemberTreasuryDashboardDto): MemberBalance;

// useAppData() return additions (plan 01)
//   permissions: Set<string>; sessionIsOfficer: boolean; sessionName: string;
//   myBalance: MemberBalance | null; contribution: ContributionSummary

// src/lib/events.ts (plan 02)
export const EVENT_FILTER_TYPES: readonly ['All', 'Chapter Meeting', 'Philanthropy', 'Brotherhood', 'Social', 'Pledge Education'];
export function filterEventsByType(events: ChapterEvent[], type: string): ChapterEvent[];
export function liveDoorEvent(events: ChapterEvent[], today: string): ChapterEvent | undefined;

// App.tsx state after plan 02
//   eventsView: 'calendar' | 'list'; eventsCreateOpen: boolean; selectedEventId: string | null

// src/lib/transaction.ts (plan 04)
export type TransactionKind = 'Payment' | 'Fine' | 'Invoice' | 'Adjustment';
export function dollarsToCents(input: string): number | null;
export function previewTransaction(draft: TransactionDraft, balanceBeforeCents: number): TransactionPreview;

// src/lib/rollCall.ts (plan 05)
export function rollCallSummary(members: Member[], records: Record<string, RollStatus>): RollCallSummary;
export function markRemainingPresent(members: Member[], records: Record<string, RollStatus>): Record<string, RollStatus>;

// src/components/ui/ConfirmDialog.tsx (plan 05)
export default function ConfirmDialog(props: { title: string; body: React.ReactNode; confirmLabel: string; tone?: 'default' | 'danger'; onConfirm: () => void; onCancel: () => void }): JSX.Element;

// src/components/ui/Modal.tsx after plan 06
//   props add: title?: string; onClose?: () => void  (renders header + labeled close, Esc, overlay click)
```

## Skills every implementer must load first

Before touching code, in this order:

1. `ponytail:ponytail` — full level. The ladder applies to every task here: reuse what exists, shortest diff that works, `ponytail:` comments on deliberate ceilings. The plans are already written lazy; do not add abstractions they do not name.
2. `superpowers:test-driven-development` — the red → green loop the plan steps spell out.
3. `superpowers:verification-before-completion` — before claiming a task done.

Then scan the rest of the skill list and invoke anything else that clearly fits (e.g. `superpowers:systematic-debugging` when a test fails for a reason the plan did not predict).

## Reporting back

When a plan is done, the subagent reports: the commits made (hash + message), the output of `npm test` and `npm run lint` (last lines), anything skipped and why, and anything it found that contradicts the spec. No self-praise, no summaries of the plan.

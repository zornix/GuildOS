# GreekOS HCI evaluation + implementation handoff

> **Status:** plan written, **not implemented**. Source of truth for the next agent that picks this up. Cursor plan file (same content, thinner): `~/.cursor/plans/greekos_hci_critique_0ecffd5a.plan.md`.
>
> **Target:** `LocalDev/greekos` only. Do not port to `fratos` unless asked.
>
> **Mode:** Operate (task UI). Skills that applied: impeccable `critique`, then this handoff. Re-run `/impeccable critique LocalDev/greekos` after the slice.

**Date:** 2026-09-07
**Conversation decisions:** useful but not usable → full HCI sequence → Home as 2×2 dashboard (not extra KPI chrome) → Events calendar-first → Treasury add-transaction prototype.

## Grill decisions (2026-09-07, supersede anything below that conflicts)

| # | Decision |
|---|---|
| 1 | greekos is a **design lab**, not a fratos replacement. Client-local prototypes are fine when labeled Demo. |
| 2 | Treasury Add Transaction is **client-local for all kinds** this slice. Kinds use backend words: **Payment, Fine, Invoice, Adjustment**. Real wiring (`/treasury/payments/balance-submissions` + `/verify`, `/treasury/adjustments` + `/approve`) is a later slice. |
| 3 | Home welcome counts are **upcoming only**: organizing N, supervising N, chairing N. Say **chaired**, never "led". Counts come from one `useContribution` hook whose return shape matches the future `GET /api/contribution/me` (issue #40). Lifetime résumé numbers live there, not here. |
| 4 | Every verified job counts toward contribution, standalone or attached. **No "house jobs"** copy. Jobs tab lists all jobs; event/initiative-attached ones carry a tag. `CONTEXT.md` updated. |
| 5 | **Pay stays on Treasury.** Home shows only a status line: "Balance owed $X · N open invoices" → Treasury. Source: `GET /api/treasury/members/{me}/dashboard` (member-readable). Pay modal on Treasury prefills from that balance, not `$150`. Word is **Balance owed**, never "dues balance" — the current number is unpaid fines from the officer-only standing list, which is wrong on both counts. |
| 6 | **Check-in happens on Home.** If an upcoming event has a live door link, Home renders the 6-digit code field inline. Attendance keeps `self_pin` as the member default tab. |
| 7 | Roll call: **unmarked stays unmarked**. Save sends only rows a human set and shows "48 present · 3 absent · 9 unmarked". A separate **Mark remaining present** button sets the rest explicitly. Never a silent Present default. |
| 8 | `isOfficer` derives from `GET /api/rbac/me/permissions` (exists, fratos uses it). Nav `officerOnly` flags become permission keys. Modules keep their `isOfficer` prop this slice. |
| 9 | Sidebar switcher stays, labeled **Demo: view as**, warning styling. |
| 10 | Step 6 trimmed to the a11y floor: `role="dialog"`, Esc, overlay dismiss, `aria-label` on every ✕ and search. **Skip** sidebar regroup and Events collapsed sections. |

---

## For the next agent

0. **Implementation plans live in `LocalDev/docs/superpowers/plans/2026-09-07-greekos-hci/`.** Start with `00-README.md` there; it directs one implementer subagent per numbered plan, with TDD and the full design-decision record.
1. Read this file, then `LocalDev/greekos/README.md` and `PRODUCT.md` at repo root.
2. Do not relitigate ADR-0004 (standing/contribution firewall) or invent prod tables.
3. Implement in the order under [Implementation](#implementation). Each step names files and a done-when.
4. Verify in a browser (officer + member). greekos has no Playwright suite.

### Run

```bash
# Terminal A — backend only. LocalDev/npm run dev also starts fratos on :3000; stop that or give greekos another port.
cd LocalDev && npm run dev

# Terminal B
cd LocalDev/greekos && npm run dev          # Vite :3000, proxies /api → :8001
```

Requires `DEV_AUTH_BYPASS=1` in `LocalDev/.env`. Dev-login is Jake Martinez (`jake@tke.org`), token in `localStorage` key `g_token`.

```bash
cd LocalDev/greekos && npm run lint && npm run build
```

---

## Verdict

**Useful: yes. Usable: not yet.**

Utility is high (events, attendance, treasury, jobs, roster, recruitment exist). Usability is poor: Nielsen **15/40**, cognitive-load checklist **7/8 failed**. Critique method: dual-agent design review + detector. Live `localhost:3000` was down during critique; judgments are from source. Detector CLI on `LocalDev/greekos/src` returned `[]` (Inter ignored in `.impeccable/config.json`). Grep found unlabeled search fields, 12 unlabeled ✕, no `aria-live`.

---

## Locked product decisions

| Decision | Choice |
|---|---|
| Surface | `LocalDev/greekos` (Vite SPA). Not `fratos`. |
| Home layout | Welcome, then 2×2 **content** panels: Upcoming events, Announcements, Jobs, Initiatives. |
| Home stats | Personal **upcoming** counts in welcome: organizing, supervising (officers only), chairing. Not chapter KPIs (roster / attendance % / receivables). Not a ranked roster. Lifetime record → issue #40. |
| Events | Calendar default. One horizontal bar: type filter + list/calendar toggle + Create. Filter applies to both views. |
| Treasury | Prototype **Add transaction** (who, kind, dollars, memo, preview/confirm). Client-local for every kind this slice, labeled Demo. Kinds: Payment, Fine, Invoice, Adjustment. |
| Sequence | Home → Events chrome → Treasury prototype → safety/truth → conceptual model → Operate floor → verify. |
| Money | Integer cents in hooks/adapters. UI amounts in dollars. `formatMoney(cents)`. |
| Contribution vs standing | Personal counts only. Never mix into standing. Never render a full ranking (ADR-0004, `docs/adr/0004-standing-contribution-firewall.md`). Organizer/supervisor counts on Home are **facts of assignment**, not contribution credit toward standing. |

**Out of scope:** visual redesign, port to `fratos`, Bylaws/Outbox backends, contribution leaderboard, create-from-calendar (unless Home Schedule Event already opens the create form).

**Keep (do not polish away):** notify gate (1 supervisor / 1 organizer / 3 jobs), 36-hour unclaim lock, door-code check-in (`maxLength={6}`), job reject requires a reason, DemoGate, backend-down banner, Mandatory / organizers-needed / open-jobs status on events.

---

## Evaluation (why this work exists)

### Gulf of execution

Users know the goal. The UI does not offer a short labeled path.

- **Check in:** Home has none. Attendance default tab is `roster_check`, not `self_pin`. Door code is created under Events → Live Door Mode.
- **Pay:** Home `onPayDuesQuick` is `() => setActiveTab('finance')`. Pay modal prefills `$150`, not the shown balance.
- **Schedule:** Home Schedule Event does not open the create modal. `eventsView` defaults to `'list'`.
- **Jobs:** nav Jobs → `TasksModule`. Event jobs live inside Events. `onClaimTask` is passed into `TasksModule` and never rendered.
- **Command:** template chips call `handleRunCommand(t)` immediately, including `fine Cody Jenkins $25…`.

Mapping mismatches: Jobs vs `tasks` vs event jobs; Home vs `dashboard`; Treasury vs `finance`; Enable door link vs Live Door Check-In. Footer Officer/Member + View as looks like identity. `isOfficer` defaults `true` and is never set from `api.getMe()`.

### Gulf of evaluation

- Toast: 3.5s, Sparkles, no `aria-live`, no undo (`src/hooks/useToast.ts`).
- Attendance save: `attendanceRecords[m.id] || 'Present'` — unmarked = present (`AttendanceModule.tsx` `handleSaveAttendance`).
- Command history pre-seeded with fake Executed fines.
- Ledger emptied on load (`useAppData.ts`: `finance.setLedger([])`) while copy says immutable `big_ledger`.
- `Modal.tsx`: no `role="dialog"`, no Esc, no overlay dismiss, close is unlabeled ✕ (12 call sites).

### Nielsen (Operate, /40)

Visibility 2, Match real world 2, Control 2, Consistency 1, Error prevention 1, Recognition 2, Flexibility 1, Aesthetic 2, Recovery 1, Help 1. **Total 15 — Poor.**

### Usability goals

Effectiveness fails on the member path. Efficiency: 9 nav items, Events stacks plan+jobs+security+door. Safety fails. Utility is strong. Learnability/memorability fail on the Jobs split and roll-call-first Attendance.

---

## Exact bugs / code pins

| Issue | Where |
|---|---|
| Unmarked attendance → Present | `src/components/AttendanceModule.tsx` ~line 73 |
| Attendance default tab roll call | same file, `useState('roster_check')` |
| Events default list | `src/App.tsx` `useState('list')` |
| Filter only on list, not calendar | `EventsModule.tsx` `filterType`; `CalendarModule` has no type filter |
| Orphan list/calendar toggle | `App.tsx` above the Events header |
| Pay CTA only switches tab | `App.tsx` `onPayDuesQuick` |
| Pay default $150 | `FinanceModule.tsx` `useState('150')` |
| `isOfficer` default true, not from session | `src/hooks/useAppData.ts` |
| `getMe()` updates name only | `useAppData.ts` load path |
| Command templates execute | `CommandModule.tsx` ~line 357 `handleRunCommand(t)` |
| Seeded fake command history | `CommandModule.tsx` initial `commandHistory` |
| Dead `onClaimTask` | `App.tsx` → `TasksModule` |
| Ledger cleared after load | `useAppData.ts` comment + `setLedger([])` |
| Officer record-payment is client-local | `useFinance.ts` `handleRecordPayment` |
| No `aria-live` anywhere | grep: none |
| Unlabeled ✕ | Attendance, Events, Finance, Initiatives, Recruitment, Roster, Tasks |

List endpoint often has empty `supervisors` / `organizers` until `onSelectEvent` loads detail (`adapters.ts`). Home “events supervised/organized” counts may undercount until detail is fetched — count from names when present, else skip or trigger detail loads; do not invent numbers.

---

## Implementation

Work in `LocalDev/greekos`. Pages/modules stay dumb about fetch: hooks own API, adapters own DTO→UI, `formatMoney` for money. No new npm deps. No new prod tables.

### 1. Home dashboard

**Files:** `src/components/DashboardOverview.tsx`, `src/App.tsx` (CTA props: open pay modal / events create / attendance `self_pin`), `src/components/AttendanceModule.tsx` (`initialTab`).

**Layout:**

```
Welcome
[Upcoming events]  [Announcements]
[Jobs]             [Initiatives]
```

- Drop officer chapter-KPI row (active roster, avg attendance, receivables, open jobs) and the 2+1 dump.
- Welcome: name, role, standing. Compact personal counts: events supervised (hide for members), events organized, initiatives led. Match `currentMemberName` against `event.supervisors`, `event.organizers`, `initiative.leadChairs`.
- CTAs: member check-in → inline door-code field on Home when a door link is live; Balance owed → status line linking to Treasury (no modal on Home); Schedule Event → Events create form (lift `showAddForm` to `App.tsx`).
- Each 2×2 tile drills into its tab (`events`, announcements live on Home/Calendar — `onNavigateTab` as today). Keep Mandatory / organizers-needed on event rows. Do not put contribution counts on standing.
- Member Attendance default tab = `self_pin`. Mobile: if a door link is live, check-in in the thumb zone.

**Done when:** officer and member Home match the ASCII layout; welcome counts are personal; Pay/Schedule/Check-in do not merely switch tabs.

### 2. Events chrome

**Files:** `src/App.tsx`, `src/components/EventsModule.tsx`, `src/components/CalendarModule.tsx`. Optional small wrapper instead of stuffing chrome into `App.tsx`.

- Default `eventsView` to `'calendar'`.
- One horizontal bar: type chips (`All`, `Chapter Meeting`, `Philanthropy`, `Brotherhood`, `Social`, `Pledge Education`) + list/calendar segmented control + officer Create.
- Lift `filterType` so calendar and list share it. Remove the filter card from the list column.
- Calendar day click still opens list/detail for that event.

**Done when:** opening Events shows the calendar; changing a type chip filters both views; Create still works.

### 3. Treasury Add Transaction prototype

**Files:** `src/components/FinanceModule.tsx`, `src/hooks/useFinance.ts` if a dues-charge kind needs a local ledger append. `src/components/ui/Modal.tsx` after step 6, or use the existing modal until then.

- Primary officer CTA becomes **Add transaction**, not Issue Fine Citation.
- Fields: member, kind (`Payment` / `Fine` / `Invoice` / `Adjustment`), amount in dollars, memo.
- Preview then confirm: “Credit $X to Name → new balance $Y”.
- All four kinds client-local this slice through the existing local handlers. Honest demo copy (same spirit as DemoGate), not “Venmo Gateway”.
- Prefill amount from the selected member’s displayed balance when kind is payment.
- Ledger heading: “Chapter ledger”, not ``big_ledger``. Amounts in the form are dollars; cents only at the hook.

**Done when:** a treasurer can record a payment and a fine from one form with a confirm step; `npm run lint` is clean; no new migration.

### 4. Safety / truth

**Files:** `AttendanceModule.tsx`, `CommandModule.tsx`, `FinanceModule.tsx`, `RosterModule.tsx` (standing `onChange`), `DashboardOverview.tsx` (announcement delete), `useAppData.ts`, `Sidebar.tsx`, `useToast.ts`, `AppShell.tsx`.

- Unmarked ≠ Present. Save sends only marked rows and shows the present/absent/unmarked summary. Add **Mark remaining present** as an explicit button.
- Confirm who/amount/consequence: fines, Mark Paid, standing, announcement/job delete, bid blast, command run.
- Command templates **fill the input**; they do not run. Drop seeded fake history.
- Set `isOfficer` from `GET /api/rbac/me/permissions`, never from the role string. Label sidebar switcher **Demo: view as** (warning chrome).
- Toast: `role="status"` `aria-live="polite"`; persist until next toast or dismiss.

**Done when:** committing a blank roll sheet is impossible; clicking a command chip does not issue a fine; impersonation is visibly demo.

### 5. Conceptual model

- Nav label stays **Jobs**. A job is a job: the Jobs tab lists every job, with an event or initiative tag when attached. Events detail still shows its own jobs. No “house jobs”.
- Wire `onClaimTask` or remove the dead prop.
- One phrase: **Door code** in Events and Attendance (retire Live Door Mode / Live Door Check-In as primary labels).
- Quieter copy: Broadcasts, Chapter ledger. Cut NLP Engine / Venmo Gateway / `big_ledger` / Commit Attendance to Roster.

**Done when:** a new member can tell house jobs from event jobs without reading code.

### 6. Operate floor

**Files:** `src/components/ui/Modal.tsx`, search inputs in Roster/Recruitment/Finance/Outbox/Command, `src/config/navigation.ts`, `Sidebar.tsx`, `EventsModule.tsx` canvas.

- Modal: `role="dialog"`, `aria-modal`, focus trap, Escape, overlay dismiss, named close (`aria-label="Close"`).
- `htmlFor` / `aria-label` on search fields and every ✕.
- Events detail: plan first; jobs / security / door as collapsed sections, not one endless canvas.
- ~~Sidebar groups~~ and ~~Events collapsed sections~~ — cut (grill decision 10).

**Done when:** Esc closes every modal; keyboard users can name every icon button; Events list/detail is not one unscrolled wall on desktop.

### 7. Verify

Browser, desktop and a phone viewport:

- Home officer + member (2×2 + welcome counts)
- Events calendar + type filter + Create from Home
- Attendance member check-in + officer commit (unmarked blocked)
- Treasury add-transaction preview/confirm
- Jobs tab shows all jobs with attachment tags

Then `npm run lint` + `npm run build` in `greekos`, and `/impeccable critique` on `LocalDev/greekos`.

---

## File map (start here)

| Path | Why |
|---|---|
| `greekos/src/App.tsx` | Tab shell, eventsView, CTA wiring |
| `greekos/src/config/navigation.ts` | Nav labels, officerOnly, demo |
| `greekos/src/components/DashboardOverview.tsx` | Home |
| `greekos/src/components/EventsModule.tsx` | List/detail, filter, create, notify gate |
| `greekos/src/components/CalendarModule.tsx` | Month grid |
| `greekos/src/components/AttendanceModule.tsx` | Roll call + door code |
| `greekos/src/components/FinanceModule.tsx` | Treasury |
| `greekos/src/components/TasksModule.tsx` | House jobs |
| `greekos/src/components/CommandModule.tsx` | NLP console |
| `greekos/src/components/layout/AppShell.tsx` | Toast, drawer |
| `greekos/src/components/Sidebar.tsx` | Impersonation |
| `greekos/src/components/ui/Modal.tsx` | Dialog primitive |
| `greekos/src/hooks/useAppData.ts` | Load, isOfficer, ledger clear |
| `greekos/src/hooks/useFinance.ts` | Payments/fines/ledger |
| `greekos/src/hooks/useToast.ts` | Ephemeral toast |
| `PRODUCT.md` | Brand + purpose |
| `CONTEXT.md` | Domain words (job, standing, contribution, chair) |
| `docs/adr/0004-standing-contribution-firewall.md` | Do not rank, do not mix standing |

Layering reminder: `LocalDev/CLAUDE.md` frontend section + `FrontendConventions.md`.

---

## Checklist

- [ ] 1. Home dashboard (welcome + 2×2 + personal counts + finishing CTAs)
- [ ] 2. Events calendar-first + shared horizontal filter
- [ ] 3. Treasury Add Transaction prototype
- [ ] 4. Safety/truth (attendance, confirms, command, session, toast)
- [ ] 5. Conceptual model (jobs = jobs, door code, dead handler, copy)
- [ ] 6. Operate floor (modal a11y + labels only)
- [ ] 7. Browser verify + lint/build + impeccable critique

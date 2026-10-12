# Frontend feature modules audit (greekos/src)

Read-only audit, 2026-10-11. All paths relative to `LocalDev/greekos/src/` unless prefixed `api/`.
Tags: **FACT** = read in code at the cited line. **INFERENCE** = my reading of behaviour (not run in a browser).

## 0. Shared plumbing (applies to every module)

- **Wiring.** No router. `App.tsx:42` holds `activeTab`; each module is rendered by `App.tsx:76-250` with booleans from `can(app.permissions, key)` (`lib/session.ts:8`). Nav entries: `config/navigation.ts:22-32`. Only Outbox (`announcements:send`) and Command (`nl_controller:execute`) are hidden from the nav by permission. FACT
- **Data load.** One big startup load in `hooks/useAppData.ts:118-193`. It fetches members/standing/scores, events, excuses, fines, treasury dashboard, tasks, announcements, initiatives, contribution and my-treasury, then `/api/events/upcoming-details`. Nothing is paginated. FACT
- **Mutations.** `hooks/useBackend.ts:29-55` `syncApi(call, refetch, toast)`. Local state is changed optimistically *before* the call. The toast only shows after the server answers, and a failure refetches to roll back. FACT. Optimistic rows carry made-up ids such as `'e_'+random` (`useEvents.ts:121`), `job_` (`useEvents.ts:283`), `t_` (`useTasks.ts:296`), `init_`, `ex_`, `a_`. INFERENCE: this conflicts with the rule "Nothing on screen that the server did not return" (CLAUDE.md, Frontend rules), at least for a moment.
- **Errors.** `api.ts:155-187` throws ``Error(`${method} ${path} failed (${status}): ${detail}`)``. The hooks then substring-match tokens out of that message (`useEvents.ts:35-39`, `useAttendance.ts:73-74`). FACT. This is brittle but works.
- **Global states.** `components/layout/AppShell.tsx:99-103` renders the app-wide loading and backend-down banners. Few modules have their own empty or error states (see each module below). FACT
- **Identity by name.** Every module finds "me" by matching the display name, `members.find(m => m.name === currentMemberName)`: `EventsModule.tsx:132`, `AttendanceModule.tsx:66`, `TasksModule.tsx:46`, `InitiativesModule.tsx:62`. Event supervisor sign-off is gated on a name match, `(selectedEvent.supervisors||[]).includes(currentMemberName)` (`EventsModule.tsx:623`). Initiative chair sign-off works the same way (`InitiativesModule.tsx:278`). `currentMemberId` is available in `App.tsx:46` but is not passed down. FACT. INFERENCE: two members with the same name would break claim, approve and swap visibility.
- **Timezone.** The frontend has no idea of the chapter timezone. `formatters.ts:17-18` `eventStart` parses `${date}T${time}` in the browser's local zone. `isWithin36Hours` and `hasStarted` (`formatters.ts:23,28`) and `parseWhen` (`lib/parseWhen.ts`) all use browser-local time. The only chapter-tz-aware read is fine eligibility (`api.getFineEligibility`, `FinanceModule.tsx:149-163`). FACT

---

## 1. Events: EventsBar + CalendarModule + EventsModule (+ useEvents, useEventsChrome, lib/events)

### Structure
- The Events tab is three components. `EventsBar` has the type chips, a Calendar/List toggle and the Create button. Under it sits **either** `CalendarModule` (view `'calendar'`) **or** `EventsModule` (view `'list'`) (`App.tsx:99-158`). FACT
- **The default view is calendar** (`hooks/useEventsChrome.ts:9`). `openCreate` and `openEvent` force the view to `'list'` (`useEventsChrome.ts:15-25`). FACT

### EventsBar.tsx
- Type chips come from `EVENT_FILTER_TYPES` (`lib/events.ts:5-7`: All, Chapter Meeting, Philanthropy, Brotherhood, Social; there is no "Community Service" chip even though the adapter knows the type, `adapters.ts:94-100`). The view toggle is at `:36-49` and Create (gated `calendar:event:create`) at `:51-60`. FACT
- Phone: `flex-col sm:flex-row`, chips `flex-wrap`. FACT

### CalendarModule.tsx (the calendar grid that exists today)
- A month grid built with `monthCells` (`:44`), with prev/today/next buttons (`:102-123`). Each cell shows the titles of that day's events, an "N open jobs" pill and announcement pills (`:139-213`). A red dot marks events with zero organizers (`:144,169`). FACT
- Clicking a day sets a right-hand "Agenda" panel (`:218-312`). Each event in it has an **"Open →"** button that calls `chrome.openEvent`, which switches to list view with that event selected (`:251-257`). It also has a "Volunteer" button when there are no organizers (`:266-279`). FACT
- **Prop `initiatives` is accepted but never used** (`:17,27`), yet the legend advertises purple "Initiatives" (`:81-83`) and the subtitle says "Events, initiatives, and announcements on one calendar" (`:72`). FACT. The legend promises something the grid does not show.
- Announcement priority badge `{a.priority}` (`:302-304`) is always `'Normal'`, hard-coded in `adapters.ts:365`. FACT (fabricated display value)
- Endpoints: none directly. Data comes from the startup load. FACT
- Phone: `grid-cols-7`, cells `min-h-16`, titles `text-xs truncate` (`:150,179`). INFERENCE: at 375px each cell is about 45px wide, so titles are unreadable. The agenda panel stacks below the grid (`grid-cols-1 lg:grid-cols-3`, `:91`), so on a phone you tap a day and then scroll down.
- Empty states: per-day "No chapter events scheduled" / "No announcements" (`:233-234,292-293`). There is no loading or error state. FACT

### EventsModule.tsx (the list/detail screen, 1266 lines)
**Renders.** A left card list (`:276-353`) and a right detail canvas (`:356-913`) with:
1. A banner with type, "Attendance required" badge, title, description, date, time, location and audience (`:359-434`).
2. Supervisors ("Supervisors (Officers)") and Organizers ("Chairs") chips, plus a "Volunteer as Organizer" button for anyone not listed (`:437-503`).
3. A "Notify Members Gate" panel with a checklist: ≥1 supervisor, ≥1 organizer, ≥3 jobs (`:233-238`, `:506-571`). FACT
4. "Claimable Jobs & Shifts": job cards with status, claimed/needed, claimants, rejection reason, and the actions Claim, Unclaim, Report Completed, Edit, Delete, Approve and Reject (`:575-780`). FACT
5. "Security & Risk Shifts": a table of assignee, standing and swap status with Request Swap, Cancel, Accept and Decline (`:783-907`). FACT
6. Six modals:
   - Create event (`:917-1036`)
   - Add/Edit job (`:1039-1087`)
   - Delete confirm (`:1090-1113`)
   - Reject job (`:1116-1147`)
   - Assign security (`:1150-1180`)
   - Swap (`:1183-1216`)
   - Door code / QR (`:1219-1263`)

**Endpoints** (through `hooks/useEvents.ts` → `api.ts`), FACT:

| Action | Hook | api.ts | HTTP |
|---|---|---|---|
| list | `refetchEvents` :57 | `getEvents` :595 | GET /api/events/ |
| detail on select | `refetchEventDetail` :80 | `getEvent` :596 + `getCheckInLink` :617 | GET /api/events/{id}, GET …/checkin-link |
| create | `handleAddEvent` :118 | `createEvent` :598 | POST /api/events/ |
| update | `handleUpdateEvent` :132 | `updateEvent` :599 | PUT /api/events/{id} — **no UI calls it** |
| delete/cancel | `handleDeleteEvent` :138 | `deleteEvent` :602 | DELETE /api/events/{id} |
| volunteer organizer | :143 | `addOrganizer` :606 | POST …/organizers |
| claim/unclaim job | :161/:187 | `commitTask`/`uncommitTask` :754-756 | POST /api/tasks/{id}/commit\|uncommit |
| report/approve/reject | :210/:233/:256 | :768-771 | POST /api/tasks/{id}/report-done\|approve\|reject |
| add/edit/delete job | :278/:307/:326 | `createJob`/`updateJob`/`deleteJob` :758-767 | POST /api/tasks/, PATCH/DELETE /api/tasks/{id} |
| notify blast | :337 | `notifyPreview` + `notifyEvent` :609-615 | GET notify-preview then POST notify (two-phase) |
| door code | :363 | `open/closeCheckInLink` :619-622 | POST/DELETE …/checkin-link |
| security | :372-472 | `listSecurity`, `assignSecurity`, `requestSwap`, `accept/decline/cancelSwap` :627-643 | /api/events/{id}/security… |

**Permission gates in the UI**, FACT:
- `calendar:event:create`: Create button (EventsBar `:51`, `App.tsx:50`).
- `calendar:event:update`: "Assign Member" to security (`EventsModule.tsx:795`, `App.tsx:126`).
- `calendar:event:delete`: Delete event (`:390`, `App.tsx:138`).
- `attendance:checkin_link:manage`: Open/Close door code (`:400`, `App.tsx:127`).
- `tasks:assign`: Add Job / Edit / Delete job (`:587,733,743`, `App.tsx:51`).
- Ungated (anyone): Show door code, Volunteer, Claim/Unclaim/Report, Request/accept swap, and the Notify blast button (`:518`, gated only by the checklist; the backend enforces). FACT
- Approve/Reject: by supervisor **name match**, no key (`:623,755`). FACT
- INFERENCE mismatch: the backend `POST /api/tasks/` needs `tasks:create` **and** (supervisor/organizer **or** `tasks:assign`) (`api/tasks/api/tasks.py:30-54`). The UI shows Add Job only for `tasks:assign`, so an organizer who could add jobs never sees the button.

**Answers to A**
- Calendar grid: yes, `CalendarModule` (month grid + day agenda). `EventsModule` is the list+detail. They are separate screens toggled by `EventsBar`. FACT
- Sort/filter: type filter only (`lib/events.ts:9-11`). **No client sort.** The backend `list_events` orders `date` ascending and does **not** filter past events (`api/events/services/events.py:264-273`: the `upcoming` flag only flips the order), so the list mixes past and future with the oldest first. There is no search, no upcoming/past split and no required-only filter. FACT
- Default selection is `events[0]` (`EventsModule.tsx:133`), i.e. the **oldest** event. The selection also falls back to the unfiltered list, so a type filter can hide the selected card while its detail stays shown (`:133` vs `:249`). FACT
- Event detail view: yes, inline right column. Not a sheet or route. On a phone it stacks under the `max-h-[75vh] overflow-y-auto` list (`:273,278`). INFERENCE: tapping a card on a phone gives no visible change unless the user scrolls past up to 75vh of list.
- Create: yes (modal). **Edit event: no UI.** `onUpdateEvent` is destructured but never used (`:47,83`). Delete: yes. Cancel: implicit. The backend cancels instead of deleting when history exists, and the toast says so (`lib/events.ts:22-25`, modal copy `:1093`). There is no "cancelled" display, because cancelled events drop out of the list. FACT
- RSVP: **none** (no "rsvp" anywhere in src). FACT
- Attendance requirement display: a "Mandatory" chip on cards (`:300-304`, Calendar `:245`) and "Attendance required" in the detail (`:366-370`). The create form has a checkbox (`:1015-1026`). FACT
- Organizers/supervisors/security: all shown (see above). Supervisor and organizer names come only from the detail endpoints. The list only carries `organizer_count` (`adapters.ts:125-131`). Create-event can't choose supervisors; the backend decides. FACT
- Jobs attached to events: shown in the detail. They are also in the Jobs tab with a parent chip (`TasksModule.tsx:164-168`). FACT
- **Link event → attendance: none.** There is no button in `EventsModule`. `AttendanceModule` keeps its own `selectedEventId` state (`AttendanceModule.tsx:56`), defaulting to `events[0]`. It is not in `useEventsChrome` and has no prop to preselect. Attendance is keyed by event id at the API (`POST /api/attendance/event/{eventId}/manual/{memberId}`, `api.ts:651-652`). FACT
- Dates/times: displayed raw (`e.date`, `e.time` strings, `:314,420-424`). The notify stamp is a raw ISO substring `notifiedAt.substring(5,16)` (`:532`), which is UTC "MM-DDTHH:MM". FACT. `parseWhen` is used only by the Command console.

**Dead code / fabrication in EventsModule**
- `supervisors: [canCreateEvent ? currentMemberName : 'Alexander Mercer']` (`:154`). The else-branch can't be reached (the form only opens with create permission), and it is a hard-coded fake name. FACT
- The create handler adds a hard-coded default job "Event Prep & Equipment Setup" (`:156-165`). `toEventBody` (`adapters.ts:188-210`) sends **neither** jobs nor supervisors, so the job shows for a moment and then disappears on refetch. FACT
- The security picker shows `GPA: {m.gpa}` and `Sec Hrs: {m.securityHoursServed}` (`:1163`). `adaptMembers` hard-codes `gpa: 0` and `securityHoursServed: 0` (`adapters.ts:79,84`), so it always prints "GPA: 0 … Sec Hrs: 0h". FACT (fabricated)
- The door-code modal shows a lucide `QrCode` icon labelled "QR rendering is demo art" (`:1229-1232`). FACT
- The `'Rejected'` job-status branch (`:642`) is unreachable: `JOB_STATUS` never maps to it (`adapters.ts:309-314`). FACT
- `handleAssignSecurity(..., _station?)` takes an unused parameter (`useEvents.ts:372`). `api.removeSecurity` is never called (`api.ts:631`). FACT
- The delete confirm hand-rolls a Modal (`:1090-1113`) instead of the existing `ui/ConfirmDialog.tsx`. FACT

**States.** There is no empty state for the event list (it just renders an empty column). The right pane shows "Select an event…" only when `events` is empty (`:910-912`). There are jobs and security empty rows (`:615,898-902`). No per-module loading state. A detail-load failure is only `console.error` (`useEvents.ts:91-93`). FACT
**Phone.** `grid-cols-1 lg:grid-cols-3`; buttons get `min-h-11 sm:min-h-0` (44px tap targets on mobile). The security table is in `overflow-x-auto` (`:811`). The create modal date/time grid is `grid-cols-1 sm:grid-cols-3` (`:943`), but location/category is a fixed `grid-cols-2` (`:976`). FACT

---

## 2. AttendanceModule.tsx (+ useAttendance, lib/rollCall, lib/checkinLink, home/DoorCodeField)

**Renders.** A header with a "Request excuse" button (shown to everyone, `:133-139`) and three sub-tabs (`:144-180`):
- **Roll call** (`:183-304`): an event `<select>` listing **all** events, unsorted (backend order, oldest first) (`:188-198`), and a roster table with a 4-option radiogroup per member (Present/Late/Excused/Absent). "Mark remaining present" and "Save roll call" are gated by `canMarkAttendance` (`:201-225`).
- **Door code** (`:307-323`): `DoorCodeField`.
- **Excuses** (`:326-389`): list plus Approve/Reject.

**Endpoints**, FACT:
- `api.markAttendance`: **one POST per marked member**, `Promise.allSettled` (`useAttendance.ts:29-31`). There is no bulk endpoint, and failed names are listed in the toast (`:32-37`).
- `api.checkInWithCode` POST `/api/attendance/checkin/{code}` (`useAttendance.ts:66-77`).
- `api.submitExcuse` POST `/api/excuses/event/{id}` and `api.reviewExcuse` PUT `/api/excuses/{id}/review` (`:44-62`).
- **Never called:** the backend `GET /api/attendance/event/{event_id}` (`api/attendance/api/attendance.py:49`), `/summary`, `/sessions`. **The roll-call sheet always starts blank** (`AttendanceModule.tsx:70-71`), even after a previous save or after door-code check-ins. An officer can't see who already checked in.

**Permissions**, FACT:
- `attendance:override`: roll-call controls; the radios are `disabled` otherwise (`:276`). It also picks the default sub-tab (`App.tsx:185`).
- `attendance:excuse:review`: Approve/Reject (`:365`).
- `standing:view_all`: the "Semester rate" column (`:236,250`).

**Answers to B**
- How an officer opens attendance today: nav tab "Attendance" → Roll call → pick the event in the dropdown. There is no deep link from an event (see §1). FACT
- Roll call: client-only marks, then save. 'Late' is silently stored as `present` (`useAttendance.ts:28-30`); the API has no late state. The optimistic `checkedInCount` is written onto the event row (`:25`). FACT
- Excuses: the member submits through a modal (event select + reason, `:392-431`). The fallback `eventDate: '2026-07-16'` is hard-coded (`:107`). Officers approve/reject with no note field. The `Excuse.officerNotes` and `documentationUrl` types exist but are never set (`types.ts:168,171`). FACT
- Check-in links: an officer opens the door code from the event detail (§1). Members type the code on Home or Attendance. The `/?checkin=CODE` deep link is parked in sessionStorage across login and consumed once (`App.tsx:29-32,55-62`; `lib/checkinLink.ts`). The QR is fake (§1). FACT
- What a member sees of their own attendance: **nothing per event.** A member gets the full roster table with disabled radios and no history. The attendance rate exists only on `Member.attendanceRate`, and the column is gated by `standing:view_all`. Home's MyRecord shows `eventsAttendedCount` only (contribution). FACT
- Empty states: excuses empty (`:336-337`). With zero events the roll-call select is just empty. No loading state. FACT
- Phone: the sub-tab bar is `overflow-x-auto` (`:144`). Role and rate columns are `hidden sm:table-cell`. Radio buttons are `min-h-11` on mobile. The table is in `overflow-x-auto` (`:229`). FACT

---

## 3. TasksModule.tsx ("Jobs" tab) (+ useTasks, lib/tasks)

**Renders.** A header with a "N pending" pill, "Add job" (`tasks:create`, `:89-97`), a **Priority** filter ribbon (ALL/Urgent/High/Medium/Low, `:101-114`) and a card grid `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` (`:117`). Each card shows a priority badge, a status button (toggles standalone tasks only), title, parent chip, description, assignee or claimants, spots filled, Claim and due date (`:118-195`). The Add modal has title, instructions, assign-to, priority and due date (`:199-274`).

**Endpoints**, FACT:
- `api.createTask` POST `/api/tasks/` (`useTasks.ts:300-311`).
- `api.setTaskStatus` POST `/api/tasks/{id}/status` with `done`/`open` (`:314-320`).
- `api.commitTask` (`:333`).
- Reads come from the startup `getTasks` plus `refetchJobs`.

**Answers to C**
- **Priority is fabricated.** There is no task priority column. The adapter maps `required ? 'High' : 'Medium'` (`adapters.ts:296`), and create sends `required: priority is High|Urgent` (`useTasks.ts:306`). So the **Urgent and Low filters can never match a server row**, and an Urgent task comes back as High. FACT
- Status values shown: `TASK_STATUS` maps open→To Do, committed→Pending, in_progress→In Progress, done→Completed, done_reported→Done Reported, approved→Approved, cancelled→Cancelled, anything else→'Unknown' (`adapters.ts:267-275`). FACT
- List: **everything.** `adaptTasks` drops only `kind==='security'` (`adapters.ts:283`). Cancelled, Completed and Approved jobs stay in the grid, dimmed and struck through (`TasksModule.tsx:127-130,161`). There is **no status filter, no "active only" default and no history view.** FACT
- Sort: no client sort. The backend orders `created_at DESC` (`api/tasks/services/tasks.py:157`). FACT
- Actions and gates, FACT:
  - Claim: anyone, via `canClaimTask` (`lib/tasks.ts:10-15`).
  - Complete toggle: standalone tasks only, no key in the UI (`:122,146`; backend `/status`).
  - Report done / approve / reject: **not on this screen.** An attached job is read-only with the tooltip "Report and review this job in its event/initiative" (`:147`).
  - Unclaim, cancel/delete: not on this screen.
- The due-date default is the hard-coded `'2026-07-16'` (`:43`), already in the past. FACT
- "N pending" counts `Pending|Done Reported` (`:81`). FACT
- Empty state: **none** (an empty grid). No loading or error. FACT
- Phone: single column, ribbon wraps, filter buttons `min-h-11`. FACT
- Status `Pending` is shown for `committed`; a member reads "Pending" for a claimed job. INFERENCE: confusing next to "In Progress".

---

## 4. InitiativesModule.tsx (+ useInitiatives)

**Renders.** A list of cards with category, target date, title, description and a progress bar (approved/total jobs) (`:141-193`). The detail shows category, status, title, description, timeline, chairs (`:197-245`) and jobs with Claim, Unclaim, Report and **Chair Sign-Off** (`:248-374`). Modals: Launch initiative (`:384-470`) and Add job (`:474-522`).

**Endpoints**, FACT:
- `api.createInitiative` POST `/api/initiatives/` (`useInitiatives.ts:29-41`), with `time: '12:00:00'` hard-coded (`:36`).
- `api.createJob` with `initiative_id` (`:57-67`).
- commit, uncommit, reportJobDone, approveJob (`:90,113,131,149`).
- **No reject, edit, delete or cancel for initiative jobs, and no edit or delete for initiatives.** There is no `api.updateInitiative` or `api.deleteInitiative`. FACT

**Gates**, FACT:
- `calendar:initiative:create`: Launch (`:126`).
- `tasks:assign` **or** a name-matched chair: Add job (`:260`).
- Chair sign-off: name match (`:278,360`).

**Answers to D**
- **Proposals: none.** "proposal" appears only in a hard-coded job title (`:78`). FACT
- Chairs: displayed as names (`adapters.ts:399`). Create **cannot pick chairs**: `leadChairs` is frozen to `[currentMemberName]` in a disabled input (`:52,431-436`), and the create body sends **no** `chair_member_ids` (`useInitiatives.ts:31-38`). FACT
- Category: offered in the form (`:415-426`, including "Rush") but **never sent**. The adapter hard-codes `category: 'Philanthropy', status: 'Active'` (`adapters.ts:401,404`). Every initiative displays "Philanthropy · Active". FACT (fabricated)
- The create handler adds a fake default job "Kickoff Proposal & Project Budget Outline" optimistically (`:75-84`). It is never sent, so it disappears on refetch. Default dates are `'2026-07-15'` and `'2026-10-01'` (`:53-54`). FACT
- Jobs attached: yes. They are shown and also appear in the Jobs tab. FACT
- States: "No initiative selected." (`:377-379`). There is no list empty state and no job-list empty state. FACT
- Phone: `grid-cols-1 lg:grid-cols-3`. The create modal's two `grid-cols-2` rows (`:412,440`) don't collapse. FACT

---

## 5. Treasury: FinanceModule.tsx + components/finance/* (+ useFinance, lib/dues, lib/transaction, lib/balance)

**Renders.** A header with "New dues run" (`treasury:invoice:create`, `:191`) and "Add transaction" (if any kind is allowed, `:202`). Two KPI cards: Recent payments and Unpaid fines (`:216-232`). Tabs: **My invoices** (default), Balances, Fines, Payments, and Proof queue (`treasury:payment:verify`) (`:235-262`).

**Endpoints** (`hooks/useFinance.ts`, `lib/transaction.ts:217-259`), FACT:
- Member self: `getMemberTreasuryDashboard` GET `/api/treasury/members/{id}/dashboard` (open invoices, pending submissions, balance) (`useAppData.ts:149`, `useFinance.ts:51-54`).
- Proof: `submitPaymentProof` POST `/api/treasury/payments/submissions`, then `addPaymentEvidence` POST `…/submissions/{id}/evidence` (`useFinance.ts:84-111`).
- Queue: `listPaymentSubmissions` (pending), `verify-v1` and `reject-v1`, and `getPaymentEvidence` (`:56-149`).
- Officer: `bulkCreateInvoices` with an Idempotency-Key (`:67-80`); `recordPayment`, `issueFines`, `createInvoice` and `createAdjustment` (`lib/transaction.ts:225-245`); `getFineEligibility` (`FinanceModule.tsx:154`); `getFines`; `getTreasuryDashboard` (officer-only; a 403 means empty, `useFinance.ts:155-158`).

**Permission keys** are the exact backend strings (`lib/dues.ts:13-21`): `treasury:invoice:create`, `treasury:payment:verify`, `treasury:fines:issue`, `treasury:adjustment:create`. `transactionAccess` (`lib/dues.ts:32-42`) decides which transaction kinds are offered. FACT

**Answers to E**
- What members see, FACT:
  - **My invoices** lists **open invoices only**: `myInvoices = adaptInvoices(myTreasury?.open_invoices)` (`useFinance.ts:43`; prop doc `FinanceModule.tsx:48`). Each row shows status, due date, remaining of amount and pending proof (`:278-305`).
  - **No paid-invoice history** and **no personal payment history.** The Payments tab reads the officer-only `recent_payments`, which is empty for a member (`useFinance.ts:153-158`).
  - Members also see the Balances, Fines and Payments tabs and the KPIs. For a member, Balances shows every member with `$0` and "Good Standing", because standing is 403 → `adaptMembers` defaults to `'Good Standing'` and `balanceCents 0` (`adapters.ts:69,78`). FACT (fabricated values on screen). The "Class" column is always empty (`memberClass: ''`, `adapters.ts:83`; `FinanceModule.tsx:340,362`). FACT
- What officers see: the same tabs filled in, Mark paid on unpaid fines (`:414-425`), the Proof queue, dues runs and Add transaction. FACT
- Payment recording flow, FACT:
  - Member path: open invoice → `InvoiceView` form (amount, method, note, optional screenshot) → submission → the officer verifies in `ProofQueue`.
  - Officer path: `AddTransactionModal` with kind Payment/Fine/Invoice/Adjustment. It shows a preview sentence and a confirm step (`AddTransactionModal.tsx:92,201-209`). The idempotency key is regenerated on every edit (`:65,71-74`).
  - "Mark paid" on a fine opens the modal prefilled and locked (`FinanceModule.tsx:416-420`).
- **File upload UI**, FACT:
  - `InvoiceView.tsx:195-201` uses `<input type="file" accept="image/*">`. There is **no client size check**, no type check beyond `accept`, no preview and no compression. The file name is shown (`:202-207`).
  - Upload is JSON with base64, not multipart: `toBase64` (`lib/dues.ts:291-295`) runs byte by byte, then `addPaymentEvidence(submissionId, evidence.type || 'image/png', b64)` (`useFinance.ts:97-100`). The content type falls back to a made-up `image/png`.
  - The server caps the upload at 2 MiB → 413 (`api/treasury/api/payments.py:158-159`; `api/treasury/services/payments.py:93`) and accepts **any** non-empty `content_type` (`payments.py:63`). A rejected upload toasts "Payment submitted, but the screenshot did not upload." (`useFinance.ts:104`), and the user can't retry the attachment. INFERENCE: phone camera photos often exceed 2 MiB, so this will fail often.
  - Evidence is viewed in `ProofQueue` as a `data:` URL `<img>` (`ProofQueue.tsx:366-369`; `useFinance.ts:146-149`).
- Receipts: **none.** There is no receipt view or download for a verified payment. FACT
- Reminders UI: **none** in the frontend (no "remind" string in src). FACT
- `PAYMENT_INSTRUCTIONS` is a hard-coded TKE constant (`config/treasury.ts`, marked with a `ponytail:` note). FACT
- States: My invoices has an empty state (`:274-275`). Proof queue has loading and empty states (`ProofQueue.tsx:276-279`). Balances, Fines and Payments have **no** empty state. FACT
- Phone: tabs `overflow-x-auto` (`:235`); tables `overflow-x-auto` with `hidden sm:table-cell` columns; invoice rows `flex-col sm:flex-row`. The AddTransaction kind grid is fixed `grid-cols-2`. FACT
- Quality: the finance code is the most disciplined in the app. Its logic is pure in `lib/dues.ts` and `lib/transaction.ts` with tests (`lib/dues.test.ts`, `lib/transaction.test.ts`, `components/finance/add-transaction.test.ts`, `components/treasury-access.test.ts`). INFERENCE

---

## 6. OutboxModule.tsx (+ hooks/useOutbox.ts)

- Renders: Refresh, status chips (All/Queued/Sent/Failed/Simulated, `:58-64`), channel chips (All/Email/SMS, client-side cut `:54-56`) and message cards (recipient, masked phone, event type, queued/delivered times, channel and status pills, body, error text, Retry) (`:181-255`). FACT
- Endpoints: `getOutbox(status)` GET `/api/announcements/outbox[?status=]` and `retryOutboxMessage` POST `…/outbox/{id}/retry` (`api.ts:785-792`; `useOutbox.ts:12-31`). FACT
- Gate: the nav item requires `announcements:send` (`config/navigation.ts:30`). Nothing inside the module checks permissions; the backend does (`api/announcements/api/announcements.py:95-114`). FACT
- **Compose/send: none.** It is a read-only log plus Retry. FACT
- Statuses: pending/sending/sent/failed/simulated, with labels at `:75-81`. There is no "Sending" filter chip. `no_consent`/`no_email` read as explanations and hide Retry (`lib/consent.ts:31-39`). FACT
- States: full loading, error and empty handling (`:149-164`). The error shows the raw api.ts message ("GET /api/... failed (403): ..."). There is no pagination; the backend returns everything. FACT
- Phone: chips scroll sideways (`:132`), cards stack, Retry is `min-h-11`. FACT

---

## 7. CommandModule.tsx ("Command console")

- **It does not call the NL controller.** The backend has `GET/POST /api/nl-controller/commands` and `/commands/{id}/review` (`api/nl_controller/api/commands.py:16-50`), but `api.ts` has no such method and nothing in `src` references it. The console is a **client-side regex parser** (`CommandModule.tsx:52-251`) that calls the domain hooks through `useAppData.handleExecuteCommand` (`hooks/useAppData.ts:210-252`). FACT
- The nav gate is `nl_controller:execute` (`config/navigation.ts:31`), which does not match what the console actually does: it writes fines, tasks, events and announcements directly with the user's own keys. FACT
- Parsed commands, FACT:
  - `fine NAME $N for REASON` → `finance.handleIssueFine` → createInvoice/issueFines. The default reason is "Bylaws Infraction Citation" (`:62-81`).
  - `assign TITLE to NAME` → createTask with **`dueDate: '2026-07-16'`** hard-coded (`:113`).
  - `schedule TITLE on DATE at TIME` → `parseWhen` (browser-local time). Location `'Fraternity House'`, type `'Brotherhood'` and end = start+2h are hard-coded, plus another fake default job (`:150-176`).
  - Any input **containing** "announcement" → createAnnouncement + sendAnnouncement, with `calendar_date` = today or the payload date (`:195-218`; `useAppData.ts:225-241`). Payload `priority: 'Mandatory', channels: ['Calendar','SMS','Push']` (`:203-204`) is display-only. The summary claims "SMS & Calendar … blast", but `/send` is not the SMS route (`announcements.py:149-153` is `send-sms`). INFERENCE: the summary overstates what happened.
  - `approve excuse for NAME`: matches the first pending excuse by name substring. If none matches it **does nothing silently** (`useAppData.ts:243-247`) while the log says "Approved" (`CommandModule.tsx:233-238`).
  - `extend bid to NAME` is **advertised** in the copy (`:47,266`) and asserted by `components/command-copy.test.ts:13`, but **has no parser**. It falls through to "Not a supported command". FACT. ("Bid" is recruitment-adjacent vocabulary; the project memory bans recruitment terms. The same applies to the dead `'BID_INVITATION'` in `types.ts:243`.)
  - `'ATTENDANCE'` is in the type union (`:20`) but is never produced. FACT
- Results and confirmation: a `ConfirmDialog` before running (`:366-375`). The **command log writes status 'Sent' synchronously, before the server answers** (`:83-88,119-124,181-186,209-214`). Server failures show only as toasts, and the log still says Sent. FACT. This violates "success only after the server answers".
- Autocomplete: none. There are six template chips that fill the input (`:43-50,307-321`). FACT
- Over-engineering: a mock terminal (traffic-light dots, "greekos-terminal" banner, `:273-282`). The log is session-only and not read from `/api/nl-controller/commands`. FACT
- Phone: the input has `pr-24` with an absolutely positioned button. Templates wrap. The log rows are `flex-col sm:flex-row`. FACT

---

## 8. Announcements (H)

- Data: `GET /api/announcements/` at startup (`useAppData.ts:141,178`). `adaptAnnouncements` drops `hidden_from_calendar` rows and hard-codes `priority: 'Normal'` and `channels: ['Calendar']` (`adapters.ts:356-370`). FACT
- Rendered in two places: the **Calendar** grid and agenda (`CalendarModule.tsx:196-207,286-311`) and the **Home** "Announcements" tile (`DashboardOverview.tsx:155-175`), with a remove button and a ConfirmDialog (`:163-170,214-219`). FACT
- Create: **only through the Command console** ("send announcement: …"). The title is always "Chapter announcement" and it is sent immediately (`useAppData.ts:225-241`). **There is no create form, no draft, no edit, no audience selector and no SMS send.** The backend has `sms-preview` and `send-sms` (`announcements.py:133-153`); the frontend never calls them. FACT
- Delete: Home tile, gated on `announcements:create` (`App.tsx:85`), which matches the backend DELETE gate (`announcements.py:64-67`). It calls `DELETE /api/announcements/{id}` (draft → deleted, sent → hidden from calendar). FACT
- Edit: no backend PUT/PATCH route and no UI. FACT

---

## 9. Duplication, dead code, over-engineering (cross-module)

**Duplication** (FACT unless noted)
- The job card UI (status badge colour chain, claimants row, Claim/Unclaim/Report/sign-off) is written twice: `EventsModule.tsx:617-777` and `InitiativesModule.tsx:273-372`. The Jobs tab is a third rendering of the same rows (`TasksModule.tsx:118-195`).
- Optimistic job reducers are written twice, with the same map-in-map shape: claim/unclaim/report/approve in `useEvents.ts:161-276` and in `useInitiatives.ts:70-150`. Claim exists a third time in `useTasks.ts:322-334`.
- The add-job form is in `EventsModule.tsx:1039-1087` and `InitiativesModule.tsx:474-522`. Their max spots differ (10 vs 5).
- "Find me by name" is repeated in four modules (§0).
- The sub-tab bar markup is in `AttendanceModule.tsx:144-180`; FinanceModule extracted `tabClass` (`:89-92`).
- Confirm modals are hand-rolled in EventsModule (`:1090-1147`) even though `ui/ConfirmDialog.tsx` exists.
- Status → colour ternary chains appear in `EventsModule.tsx:635-645` and `InitiativesModule.tsx:286-294`.

**Dead code** (FACT)
- `onUpdateEvent` prop / `handleUpdateEvent`: no UI.
- `CalendarModule` `initiatives` prop.
- `api.get/post/put/patch/del` (`api.ts:569-573`), `api.removeSecurity`.
- Types `AttendanceRecord`, `ChapterRule`, `OutboxNotification` (`types.ts:123,195,239`).
- `JobStatus 'Rejected'`, `ChapterEvent.audience 'Actives Only'`, `Task.category`, `Excuse.documentationUrl/officerNotes`, `Initiative.status 'Completed'|'Archived'`.
- The `'ATTENDANCE'` command type and the `'extend bid'` template.
- The `'Alexander Mercer'` branch.

**AI-generated / prototype residue** (FACT)
- Hard-coded demo dates `2026-07-16`, `2026-07-15`, `2026-10-01`.
- Seeded fake default jobs on event, initiative and command create.
- GPA and security-hours zeros shown as data.
- QR "demo art".
- A mock terminal chrome.
- Flavour copy ("Formal Ritual Chapter Meeting", "Ritual table candles…").
- "Supervisor Rejection Feedback", "Brothers Needed", and dramatic labels ("Security & Risk Shifts", "36-Hour Lock Active").
- `adapters.ts` header comment calls the UI types "prototype type mapping" (`adapters.ts:2`).

**Convention breaks** (FACT)
- `isOfficerView` is still used for presentation (`App.tsx:83`, `Sidebar.tsx:77`). CLAUDE.md's Conventions table lists it as a "Do not".
- Optimistic rows with fake ids conflict with "Nothing on screen that the server did not return".

---

## 10. Gaps vs desired state

| Desired | Today | Gap |
|---|---|---|
| **Calendar-first events page** | The default view is already `'calendar'` (`useEventsChrome.ts:9`). The month grid exists. | Phone cells are unreadable (`CalendarModule.tsx:150,179`). There is no week or agenda-list view for phones. Clicking a cell's event pill does nothing (only the day is selected). Initiatives are advertised but not drawn. Filter chips apply to the calendar, but the past and future are not separated. |
| **Event detail sheet** | An inline right column in list view (`EventsModule.tsx:356-913`), reachable from the calendar "Open →" by switching views. | There is no sheet, overlay or URL. On a phone the detail sits under a 75vh list. There is no edit-event UI (`onUpdateEvent` unused), no explicit cancel, and no RSVP. Times are raw strings with no chapter timezone. The default selection is the oldest event. |
| **Attendance deep-link** | None. `AttendanceModule` owns `selectedEventId` locally (`:56`). | Needs a "Take attendance" action on the event detail that sets the tab plus the event (lift `selectedEventId` the way `useEventsChrome` does). The roll call also needs to load existing marks from `GET /api/attendance/event/{id}`, which exists but is never called. |
| **Job board (active by default, priority sort, history)** | The Jobs tab shows all statuses including Cancelled and Approved, sorted by backend `created_at desc`. Priority is fake (`adapters.ts:296`). | Needs an Active/History split (or a status filter defaulting to open/in-progress). Needs a real priority column on the backend before any priority sort or filter; the current Urgent/Low filters match nothing. Report, approve and reject only exist inside the parent screens. |
| **Paid invoice history** | Members see `open_invoices` only (`useFinance.ts:43`). The Payments tab is officer-only data. | Needs a member-scoped paid/closed invoices and payments read (the member dashboard DTO has no such list) and a "History" sub-tab. |
| **Invoice image upload validation UI** | `accept="image/*"`, no size or type check, base64 JSON, fallback type `image/png`, failure → generic toast, no retry (`InvoiceView.tsx:195-201`; `useFinance.ts:96-107`). | Needs a client check for ≤2 MiB with a clear message (or downscaling before upload), a thumbnail preview, a retry for the evidence upload alone, and a server-side MIME allowlist (it accepts any `content_type` today). |
| **Reminder UI** | None in the frontend. | No officer "send reminder" for invoices or events, and no reminder settings. Whatever the backend does is invisible. |
| **Announcement CRUD** | Create only through the Command console regex (fixed title, immediate send). Delete on the Home tile. No edit. | Needs a create form (title, body, calendar date/time, audience), a draft/send split, an SMS send via the existing `sms-preview`/`send-sms` routes, and an announcements list screen. Edit needs a backend route first. |
| **Communications composer** | The Outbox is read-only with Retry. Event "notify blast" is the only officer-initiated SMS (`useEvents.ts:337-360`). | Needs a composer (audience, channel email/SMS, preview of recipient count with skipped no-phone/no-consent like `notifyPreview`), a link from a sent message to its outbox rows, a "Sending" filter, and pagination. |

# Phase B — Product design (member-first GreekOS)

Status: decided 2026-10-11. Builds on `00-phase-a-audit.md`. Terms follow repo-root `CONTEXT.md`.

## 0. Decision log (user, 2026-10-11 — binding)

| # | Decision | Consequence |
|---|---|---|
| D1 | Path routing with React Router | New dependency (`react-router` 7). `vercel.json` needs an SPA fallback to `greekos/index.html`. `/c/{code}` → `/?checkin=` still lands on `/`. Route-level loading replaces the 15-call startup load. |
| D2 | Officer Cabin visibility = holds any Cabin permission; each tile gated by its own key | No role-name branching. `isOfficerView` retired. Treasurer sees Proof queue only; secretary sees Comms only. |
| D3 | Jobs: keep `tasks:create` holders, plus supervisors/chairs may add jobs to their own event/initiative; approver must not be a claimant; `tasks:review` is a fallback approver on event/initiative jobs | Backend: move the `tasks:create` gate behind `can_create_*`; one guard in `can_approve_job`/`tk_approve_task`; remove `/status`. |
| D4 | Remember me = storage choice only (sessionStorage vs localStorage), 7-day TTL unchanged | Frontend only. Same change fixes the 403-as-outage bug. |
| D5 | Mobile tabs: Home · Calendar · Jobs · Me; Officer Cabin is the top row inside Me | Four tabs for everyone. Roster and Initiatives are two taps. |
| D6 | RSVP deferred; issue #118 | Event detail offers "Request excuse" on required events only. |
| D7 | Class = season + 4-digit year, self-editable, officers with `roles:assign` may edit anyone's | Migration `members.member_class`, validation in Pydantic + SQL + `lib/`, closes #115. |
| D8 | Composer: feed + email + calendar now; **SMS deferred** (Twilio not needed yet) | Backend: `ANNOUNCEMENT_EMAIL` outbox type + `email` flag on send. No SMS UI in this plan. |
| D9 | Sent announcements: title/body editable with audit, never re-send; delete = retract (hide, keep row + outbox history) | `PATCH /api/announcements/{id}`, `UPDATE_ANNOUNCEMENT` + `RETRACT_ANNOUNCEMENT` audit actions. |
| D10 | Email verification: close the signup code leak now; full flow deferred (#119) | `POST /api/chapters` stops returning the setup code. |
| D11 | Role grants: "grant only what you hold" | `rbac_assign_role` refuses a role whose permission set is not a subset of the actor's. Roster import follows the same rule. |
| D12 | Controller: Option A parser in `lib/command.ts`; backend `nl_controller` reused as the attempt log | Every attempt (parsed or failed) → `POST /api/nl-controller/commands`. No LLM. |
| D13 | P0 security fixes = Milestone 0, before any UI work | Self-grant rule, current-password on change, upload type sniff + pending-only + cap, signup code leak, seeded demo password. |
| D14 | Reminders: per-member button + "Remind everyone who owes" with preview; treasurer gets `standing:remind`; no schedule | Small bulk endpoint; chapter-timezone day key. |
| D15 | Treasury mail: detailed receipt queued inside the payment transaction; dues runs email per invoice; rejection reason exposed to the member and in the rejection email | Backend in the treasury milestone. |
| D16 | Initiative proposals out of scope (#120) | — |

Confirmed requirements (from the brief): member-first Home; three experiences (Home / Workspace / Cabin); different mobile and desktop navigation; all authorized features reachable on both; preserve backend APIs; no AI agent without evidence; custom roles deferred.

Assumptions (mine): pilot scale (1–20 chapters, ≤150 members each), so no pagination work beyond what exists; English only; no offline mode; phones are the primary member device, laptops the primary officer device.

---

## 1. Information architecture

### 1.1 Route map

| Route | Screen | Who | Replaces today | Data (existing endpoints) |
|---|---|---|---|---|
| `/` | Home | all | `dashboard` | `/api/auth/me`, `/api/rbac/me/permissions`, `/api/calendar/?start&end` (next 14 d), `/api/treasury/members/{me}/dashboard`, `/api/tasks/`, `/api/announcements/`, `/api/contribution/me`, `/api/standing/me` (new) |
| `/calendar` | Calendar (month/week + agenda) | all | `events` (calendar view) | `/api/calendar/`, `/api/events/types` |
| `/calendar/:eventId` | Event detail (sheet on mobile, panel on desktop) | all (404 if not visible) | `events` (list view, selected) | `/api/events/{id}`, `/{id}/security`, `/{id}/checkin-link`, `/api/tasks/?event_id=` |
| `/initiatives`, `/initiatives/:id` | Initiatives list + detail | all | `initiatives` | `/api/initiatives/`, `/{id}` |
| `/jobs` | Job board (Active default, History tab) | all | `tasks` | `/api/tasks/` |
| `/roster`, `/roster/:memberId` | Roster + member card | all | `roster` | `/api/members/`, standing/scores (officer) |
| `/me` | My Profile (identity, standing, roles, SMS, password, class) | all | — (new) | `/api/auth/me` (+phone, roles, timezone), `PATCH /api/members/me` (new) |
| `/me/attendance` | My attendance + excuses | all | `attendance` (member slice) | `/api/attendance/summary?member_id=me`, `/api/excuses/` |
| `/me/money` | Open invoices, History, Pending submissions | all | `finance` (member slice) | `/members/{me}/dashboard`, `/members/{me}/statement`, submissions + evidence |
| `/me/record` | Contribution record | all | Home `MyRecord` | `/api/contribution/me` |
| `/cabin` | Cabin overview (tiles the member is allowed) | any cabin key | — (new) | counts from the tiles' own endpoints |
| `/cabin/attendance/:eventId?` | Roll call (prefilled), door code, excuse review | attendance keys | `attendance` (officer slice) | `GET /api/attendance/event/{id}`, manual marks, check-in link, excuses review |
| `/cabin/treasury` | Dues runs, Add transaction, Proof queue, Balances, Fines, reminders | treasury keys, `standing:remind` | `finance` (officer slice) | treasury officer endpoints, `/api/memberadmin/remind` |
| `/cabin/comms`, `/cabin/comms/new`, `/cabin/comms/:id` | Announcements list/drafts, Composer, Outbox | `announcements:create` / `:send` | `outbox` + console announcement | `/api/announcements/*`, outbox |
| `/cabin/roster` | Invite, CSV import, reset codes, roles (with legend) | `members:invite`, `roles:assign` | `roster` (officer slice) | invite, roster import, `/api/rbac/*` |
| `/cabin/command` | Command console (Option A parser) | `nl_controller:execute` | `command` | existing domain endpoints + `/api/nl-controller/commands` |
| `/login`, `/start` | Sign in; start a chapter | anon | `LoginScreen`, `OnboardingScreen` | auth endpoints |

Rules: every route is permission-checked in a `RequirePermission` wrapper, not only in the nav. Officer actions on shared screens stay there behind `can()`; the Cabin links to them. The Cabin is a front door, not a copy.

### 1.2 Desktop sidebar (≥ `lg`)

```
Home
Chapter        Calendar · Initiatives · Jobs · Roster
My Activity    Attendance · Money · Record · Profile
Officer Cabin  Overview · Attendance · Treasury · Comms · Roster · Command   (only tiles the member holds)
```

"Treasury" under My Activity is called "Money" (member language). Sidebar collapses to icons at `lg`, labels at `xl`.

### 1.3 Mobile bottom tabs (< `lg`) — D5

Home · Calendar · Jobs · Me. The Me page lists Officer Cabin (when allowed) first, then Attendance · Money · Record · Profile, then Roster · Initiatives. Detail views open as bottom sheets; tables become card lists below `sm`; forms are full-screen sheets; tab bar respects `env(safe-area-inset-bottom)`.

Alternative considered and rejected: Home · Chapter · Me · Cabin (mirrors desktop groups, but Calendar becomes two taps).

### 1.4 Large screens (≥ `xl`)

Fluid container to `max-w-screen-2xl`; two-column where it pays: Calendar (grid + agenda rail), Event detail (detail + jobs/security rail), Cabin overview (tiles + outbox rail). Cards cap at `max-w-prose`; grids add columns rather than stretching cards.

### 1.5 Data loading

Each route loads its own data on entry. A shared `useMe()` (session, permissions, member row, chapter name, timezone) loads once. No cache library: per-route fetch + refetch after mutation is enough at this scale.

---

## 2. Member Home

Tiles, in order, each rendered **only when it has content**:

| Tile | Shows | Source | Hidden when |
|---|---|---|---|
| Banner | name, chapter name, standing, balance line, live door-code entry if a door is open | `useMe`, `/api/standing/me`, member dashboard, calendar | never |
| Needs attention | unpaid invoices due ≤ 7 d, pending excuses, my jobs in review/rejected, security swap requests | member dashboard, excuses, tasks, `/security-swaps/mine` | nothing pending |
| This week | my required events + events with my job/shift, 7 d | `/api/calendar/` | none |
| Open jobs for me | open jobs with spots left, sorted `required desc, due_at asc`, max 3 | `/api/tasks/` | none open |
| Announcements | latest 3 sent, non-retracted | `/api/announcements/` | none |
| My record | 3 counts + résumé line | `/api/contribution/me` | never |
| SMS opt-in | one-line card | member row | already opted in |

Officer additions on Home: none. Officer work lives in the Cabin overview.

Backend needed: `GET /api/standing/me` (additive).

---

## 3. Officer Cabin

`/cabin` overview = tiles with live counts, each shown only with its key: Proof queue (`treasury:payment:verify`), Excuses to review (`attendance:excuse:review`), Jobs awaiting sign-off (supervisor/chair/`tasks:review`), Events needing organizers / incomplete (`calendar:event:update`), Unpaid balances (`treasury:audit:view`), Outbox failures (`announcements:send`), Invited not yet active (`members:invite`). Then the sections in §1.1. The console is one section.

---

## 4. Calendar and events

Desktop: month grid (default) with week toggle; right rail = agenda. Click → `/calendar/:eventId` opens the detail panel. Type chips from `/api/events/types`; colours assigned client-side.

Mobile: agenda feed grouped by day with a compact week strip; tapping opens a bottom sheet at the same route.

Event detail: date/time (chapter tz), location, description, type, required badge, audience, supervisors, organizers, jobs, security shifts, check-in link status. Actions by `can()`: edit (wire the existing `PUT`), cancel/delete, notify, door code, **Take attendance** → `/cabin/attendance/:eventId`, add supervisor. Members: volunteer as organizer, request excuse (required events), claim/report.

RSVP: deferred (D6).

Backend extensions (additive): calendar includes spanning events; items get `location`, `event_type_id`; `timezone` on `/api/auth/me`; `?event_id=` on `GET /api/tasks/`; roster endpoint respects audience and cancellation.

---

## 5. Announcements and the composer (D8, D9)

One **Composer** at `/cabin/comms/new` over the existing `announcements` row: title, body, audience (chapter / officers / members with balance), optional calendar date+time, destinations:

| Destination | Mechanism | Exists | Gate |
|---|---|---|---|
| Member feed (Home + calendar) | `POST /` then `POST /{id}/send` | yes | `announcements:create`, `:send` |
| Email | new `ANNOUNCEMENT_EMAIL` outbox rows, enqueued inside the send transaction | **no** (small BE) | `announcements:send` |
| Calendar entry | announcement's own `calendar_date/time` | yes | — |

SMS: deferred. Preview shows recipient counts. Drafts list at `/cabin/comms`; edit = `PATCH` (drafts: anything; sent: title/body only, audited); delete = retract. **Editing never re-sends.** No scheduling. No real event creation from the composer (would double-email via `EVENT_CREATED`).

---

## 6. Job board (D3)

`/jobs` default **Active** = open, in_progress, done_reported; sort `required desc, due_at asc`. Card: title, parent chip, spots `2/4`, status, due. Actions by rule: Claim, Unclaim (36 h lock), Report done, Approve/Reject (never for a claimant), Edit/Cancel (manage rule). **History** = approved + cancelled. The fake 4-level priority goes away; "Needed" (`required`) is the one flag. One `JobCard` for Events, Initiatives, Jobs.

---

## 7. Profiles and onboarding (D7, D10)

**My Profile** (`/me`): name, email (read-only), phone, class, standing with explanation, roles with legend text, SMS consent, change password (requires current password). Backend: extend `/me`; `PATCH /api/members/me`.

**Class**: `members.member_class` matching `^(Spring|Summer|Fall|Winter) \d{4}$`; self-edit; `roles:assign` holders edit anyone's; affects nothing else.

**Onboarding**: post-login checklist derived from missing data (no new column): set password, add phone, set class, opt in to SMS, read how to pay. "Later" snoozes 7 days in localStorage. Completion: the checklist disappears. Fix: the redeem token must not open the full app before a password is set.

**Email verification**: close the chapter-signup code leak now; full flow deferred (#119).

---

## 8. Treasury workflows (D14, D15)

Member (`/me/money`): Open, History (from `/statement`), Pending (with rejection reason, "Add screenshot"). Receipt = enriched `PAYMENT_APPROVED` email ("Payment receipt") plus a member-readable receipt route.

Officer (`/cabin/treasury`): today's tabs plus Remind per member and "Remind everyone who owes" with preview; proof queue shows sniffed type (HEIC → download link).

Upload hardening: magic-byte sniff PNG/JPEG/HEIC, pending-only, ≤3 files, 2 MiB; client `accept`, size check, retry.

---

## 9. Login (D4)

Password toggle on all three password inputs. Remember me = storage choice. Auth 403 handled like 401 → `/login` with "Your session ended, sign in again".

---

## 10. Deferred

Custom roles, RSVP (#118), full email verification (#119), initiative proposals (#120), SMS composer destination, scheduled reminders, Option B/C controller, real event creation from the composer, cache library.
